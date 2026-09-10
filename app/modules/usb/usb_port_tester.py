"""USB controllers, connected devices, and plug/unplug diffs.

Snapshot is automated. Watch/compare is technician-driven on the USB page.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.wmi_session import WmiSession
from app.models.diagnostic_result import DiagnosticResult, Status

logger = logging.getLogger("techbench.usb")

MODULE = "USB"

_USB_FAIL_CODES = {10, 28, 31, 37, 39, 43}


@dataclass
class UsbDevice:
    name: str
    device_id: str
    kind: str
    error_code: int
    error_label: str
    status: Status


@dataclass
class UsbReport:
    controllers: list[UsbDevice]
    hubs: list[UsbDevice]
    devices: list[UsbDevice]
    status: Status
    message: str
    notes: list[str] = field(default_factory=list)

    def all_items(self) -> list[UsbDevice]:
        return [*self.controllers, *self.hubs, *self.devices]


@dataclass
class UsbDiff:
    added: list[UsbDevice]
    removed: list[UsbDevice]


class UsbPortTester:
    """Enumerate ports/devices and guided plug/unplug checks."""

    phase = 4
    title = "USB Ports"

    def snapshot(self) -> tuple[UsbReport, DiagnosticResult]:
        session = WmiSession()
        session.connect()
        try:
            report = _collect(session)
        finally:
            session.close()
        return report, _to_result(report)


def diff_devices(before: UsbReport, after: UsbReport) -> UsbDiff:
    previous = {item.device_id: item for item in before.all_items() if item.device_id != "Unavailable"}
    current = {item.device_id: item for item in after.all_items() if item.device_id != "Unavailable"}
    added = [current[key] for key in current.keys() - previous.keys()]
    removed = [previous[key] for key in previous.keys() - current.keys()]
    return UsbDiff(added=added, removed=removed)


def overall_from_usb(*, controllers: int, error_fail: int, error_warn: int) -> tuple[Status, str]:
    if controllers == 0:
        return Status.UNKNOWN, "No USB controllers enumerated."
    if error_fail:
        return Status.FAIL, f"{error_fail} USB device(s) report enumeration or driver errors."
    if error_warn:
        return Status.WARNING, f"{error_warn} USB device(s) are disabled or not present."
    return Status.PASS, f"{controllers} USB controller(s) present; no Windows USB errors reported."


def _collect(session: WmiSession) -> UsbReport:
    if not session.available:
        return UsbReport(
            controllers=[],
            hubs=[],
            devices=[],
            status=Status.UNKNOWN,
            message=session.error or "WMI unavailable — USB inventory not collected.",
        )

    controllers = _entities(session, "Win32_USBController", "Controller")
    hubs = _entities(session, "Win32_USBHub", "Hub")
    seen = {item.device_id for item in controllers + hubs}
    devices: list[UsbDevice] = []
    for row in session.query("Win32_PnPEntity"):
        device_id = _text(getattr(row, "DeviceID", None))
        pnp = str(getattr(row, "PNPClass", "") or "")
        if device_id in seen or device_id == "Unavailable":
            continue
        if not (device_id.upper().startswith("USB") or pnp.upper() == "USB"):
            continue
        devices.append(_from_row(row, "Device"))

    all_items = controllers + hubs + devices
    fail = sum(1 for item in all_items if item.status == Status.FAIL)
    warn = sum(1 for item in all_items if item.status == Status.WARNING)
    status, message = overall_from_usb(
        controllers=len(controllers),
        error_fail=fail,
        error_warn=warn,
    )
    return UsbReport(
        controllers=controllers,
        hubs=hubs,
        devices=devices,
        status=status,
        message=message,
    )


def _entities(session: WmiSession, class_name: str, kind: str) -> list[UsbDevice]:
    items: list[UsbDevice] = []
    for row in session.query(class_name):
        items.append(_from_row(row, kind))
    return items


def _from_row(row: object, kind: str) -> UsbDevice:
    try:
        code = int(getattr(row, "ConfigManagerErrorCode", 0) or 0)
    except (TypeError, ValueError):
        code = 0
    if code in _USB_FAIL_CODES:
        severity = Status.FAIL
    elif code == 0:
        severity = Status.PASS
    else:
        severity = Status.WARNING
    return UsbDevice(
        name=_text(getattr(row, "Name", None)),
        device_id=_text(getattr(row, "DeviceID", None)),
        kind=kind,
        error_code=code,
        error_label="OK" if code == 0 else f"Code {code}",
        status=severity,
    )


def _text(value: object) -> str:
    if value is None:
        return "Unavailable"
    text = str(value).strip()
    return text if text else "Unavailable"


def _to_result(report: UsbReport) -> DiagnosticResult:
    fail = any(item.status == Status.FAIL for item in report.all_items())
    return DiagnosticResult(
        module=MODULE,
        status=report.status,
        message=report.message,
        details={
            "controller_count": str(len(report.controllers)),
            "device_count": str(len(report.devices)),
            "port_fail": "true" if fail else "false",
        },
    )
