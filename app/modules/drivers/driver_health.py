"""Device Manager status reporter.

Report only — never download or install drivers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.wmi_session import WmiSession
from app.models.diagnostic_result import DiagnosticResult, Status

logger = logging.getLogger("techbench.drivers")

MODULE = "Drivers"

# ConfigManagerErrorCode → technician-facing text.
# https://learn.microsoft.com/windows-hardware/drivers/install/device-manager-error-messages
ERROR_LABELS: dict[int, str] = {
    0: "OK",
    1: "This device is not configured correctly (Code 1)",
    3: "The driver for this device is corrupted (Code 3)",
    10: "This device cannot start (Code 10)",
    12: "This device cannot find enough free resources (Code 12)",
    14: "This device cannot work properly until you restart (Code 14)",
    18: "Reinstall the drivers for this device (Code 18)",
    19: "Windows cannot start this hardware device (Code 19)",
    21: "Windows is removing this device (Code 21)",
    22: "This device is disabled (Code 22)",
    24: "This device is not present, is not working properly, or does not have all its drivers (Code 24)",
    28: "The drivers for this device are not installed (Code 28)",
    29: "This device is disabled because the firmware did not give it the required resources (Code 29)",
    31: "This device is not working properly (Code 31)",
    37: "Windows cannot initialize the device driver (Code 37)",
    39: "Windows cannot load the device driver (Code 39)",
    43: "Windows has stopped this device because it has reported problems (Code 43)",
    45: "This device is not connected (Code 45)",
    47: "Windows cannot use this hardware device because it has been prepared for safe removal (Code 47)",
    52: "Windows cannot verify the digital signature for the drivers (Code 52)",
}

_FAIL_CODES = {1, 3, 10, 12, 14, 18, 19, 28, 29, 31, 37, 39, 43, 52}
_WARN_CODES = {21, 22, 24, 45, 47}


@dataclass
class DriverDevice:
    name: str
    device_id: str
    pnp_class: str
    error_code: int
    error_label: str
    driver_version: str
    driver_date: str
    severity: Status


@dataclass
class DriverReport:
    devices: list[DriverDevice]
    problem_count: int
    missing_count: int
    disabled_count: int
    missing_date_count: int
    status: Status
    message: str
    notes: list[str] = field(default_factory=list)

    @property
    def problems(self) -> list[DriverDevice]:
        return [item for item in self.devices if item.error_code != 0]


class DriverHealth:
    """Device Manager status codes; report only, never auto-install."""

    phase = 4
    title = "Driver Health"

    def check(self) -> tuple[DriverReport, DiagnosticResult]:
        session = WmiSession()
        session.connect()
        try:
            report = _collect(session)
        finally:
            session.close()
        return report, _to_result(report)


def classify_error(code: int) -> Status:
    """Map a Device Manager code to PASS / WARNING / FAIL. Unknown non-zero is WARNING."""
    if code == 0:
        return Status.PASS
    if code in _FAIL_CODES:
        return Status.FAIL
    if code in _WARN_CODES:
        return Status.WARNING
    return Status.WARNING


def error_label(code: int) -> str:
    if code in ERROR_LABELS:
        return ERROR_LABELS[code]
    if code == 0:
        return "OK"
    return f"Device Manager code {code}"


def overall_from_counts(*, fail: int, warn: int, total: int) -> tuple[Status, str]:
    if total == 0:
        return Status.UNKNOWN, "No Plug and Play devices enumerated."
    if fail:
        return Status.FAIL, f"{fail} device(s) have Device Manager error codes."
    if warn:
        return Status.WARNING, f"{warn} device(s) are disabled or not present (not treated as a hardware fail)."
    return Status.PASS, f"{total} device(s) report no Device Manager errors."


def _collect(session: WmiSession) -> DriverReport:
    notes: list[str] = []
    if not session.available:
        return DriverReport(
            devices=[],
            problem_count=0,
            missing_count=0,
            disabled_count=0,
            missing_date_count=0,
            status=Status.UNKNOWN,
            message=session.error or "WMI unavailable — cannot read Device Manager status.",
            notes=[session.error or "WMI unavailable"],
        )

    signed = _signed_index(session)
    devices: list[DriverDevice] = []
    for row in session.query("Win32_PnPEntity"):
        name = _text(getattr(row, "Name", None))
        if name == "Unavailable":
            continue
        try:
            code = int(getattr(row, "ConfigManagerErrorCode", 0) or 0)
        except (TypeError, ValueError):
            code = 0
        device_id = _text(getattr(row, "DeviceID", None))
        pnp_class = _text(getattr(row, "PNPClass", None))
        version, date = signed.get(device_id.upper(), ("Unavailable", "Unavailable"))
        devices.append(
            DriverDevice(
                name=name,
                device_id=device_id,
                pnp_class=pnp_class,
                error_code=code,
                error_label=error_label(code),
                driver_version=version,
                driver_date=date,
                severity=classify_error(code),
            )
        )

    fail = sum(1 for item in devices if item.severity == Status.FAIL)
    warn = sum(1 for item in devices if item.severity == Status.WARNING)
    missing = sum(1 for item in devices if item.error_code == 28)
    disabled = sum(1 for item in devices if item.error_code == 22)
    missing_date = sum(1 for item in devices if item.driver_date == "Unavailable")
    status, message = overall_from_counts(fail=fail, warn=warn, total=len(devices))
    if missing_date and status == Status.PASS:
        notes.append(
            f"{missing_date} driver(s) have no signed date in WMI. That is not treated as a fault."
        )
    return DriverReport(
        devices=devices,
        problem_count=fail + warn,
        missing_count=missing,
        disabled_count=disabled,
        missing_date_count=missing_date,
        status=status,
        message=message,
        notes=notes,
    )


def _signed_index(session: WmiSession) -> dict[str, tuple[str, str]]:
    index: dict[str, tuple[str, str]] = {}
    for row in session.query("Win32_PnPSignedDriver"):
        device_id = _text(getattr(row, "DeviceID", None)).upper()
        if device_id == "UNAVAILABLE":
            continue
        version = _text(getattr(row, "DriverVersion", None))
        date = _wmi_date(getattr(row, "DriverDate", None))
        index[device_id] = (version, date)
    return index


def _wmi_date(raw: object) -> str:
    if raw is None:
        return "Unavailable"
    text = str(raw)
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return "Unavailable"


def _text(value: object) -> str:
    if value is None:
        return "Unavailable"
    text = str(value).strip()
    return text if text else "Unavailable"


def _to_result(report: DriverReport) -> DiagnosticResult:
    return DiagnosticResult(
        module=MODULE,
        status=report.status,
        message=report.message,
        details={
            "problem_count": str(report.problem_count),
            "missing_count": str(report.missing_count),
            "disabled_count": str(report.disabled_count),
            "has_error_code": "true" if report.status == Status.FAIL else "false",
        },
    )
