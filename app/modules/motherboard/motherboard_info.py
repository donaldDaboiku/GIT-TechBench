"""Motherboard and BIOS inventory.

BIOS-update check looks for a vendor tool already on disk. It never
contacts a network API from Full Diagnostic.
"""

from __future__ import annotations

import ctypes
import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.core.wmi_session import WmiSession
from app.models.diagnostic_result import DiagnosticResult, Status

logger = logging.getLogger("techbench.motherboard")

MODULE = "Motherboard"

_FIRMWARE_LEGACY = 1
_FIRMWARE_UEFI = 2

_VENDOR_TOOLS: tuple[tuple[str, str], ...] = (
    (r"C:\Program Files (x86)\Hewlett-Packard\HP Support Framework\HPSF.exe", "HP Support Assistant"),
    (r"C:\Program Files\HP\HP Support Framework\HPSF.exe", "HP Support Assistant"),
    (r"C:\Program Files (x86)\Dell\CommandUpdate\dcu-cli.exe", "Dell Command | Update"),
    (r"C:\Program Files\Dell\CommandUpdate\dcu-cli.exe", "Dell Command | Update"),
    (r"C:\Program Files (x86)\Lenovo\System Update\tvsu.exe", "Lenovo System Update"),
    (r"C:\Program Files\Lenovo\System Update\tvsu.exe", "Lenovo System Update"),
)


@dataclass
class MotherboardReport:
    board_manufacturer: str
    board_product: str
    board_serial: str
    board_version: str
    bios_version: str
    bios_date: str
    firmware_mode: str
    secure_boot: str
    tpm_present: str
    tpm_version: str
    bios_update: str
    status: Status
    message: str
    notes: list[str] = field(default_factory=list)


class MotherboardInfo:
    """Board model, BIOS/UEFI, Secure Boot, TPM."""

    phase = 4
    title = "Motherboard / BIOS"

    def check(self) -> tuple[MotherboardReport, DiagnosticResult]:
        session = WmiSession()
        session.connect()
        try:
            report = _collect(session)
        finally:
            session.close()
        return report, _to_result(report)

    def check_bios_update(self) -> str:
        """Return a vendor-tool hint or 'Not available.' Never hits the network."""
        return bios_update_availability()


def firmware_mode() -> str:
    """Legacy / UEFI from GetFirmwareType. Unavailable if the API fails."""
    if not hasattr(ctypes, "windll"):
        return "Unavailable"
    try:
        value = ctypes.c_uint(0)
        ok = ctypes.windll.kernel32.GetFirmwareType(ctypes.byref(value))
        if not ok:
            return "Unavailable"
        if value.value == _FIRMWARE_UEFI:
            return "UEFI"
        if value.value == _FIRMWARE_LEGACY:
            return "Legacy"
        return "Unavailable"
    except Exception:
        logger.debug("GetFirmwareType failed", exc_info=True)
        return "Unavailable"


def bios_update_availability() -> str:
    found = [label for path, label in _VENDOR_TOOLS if Path(path).is_file()]
    if found:
        names = ", ".join(dict.fromkeys(found))
        return f"Vendor tool present ({names}). Open it to check for a BIOS update — TechBench does not query vendor APIs."
    return "Not available."


def _collect(session: WmiSession) -> MotherboardReport:
    board = _board(session)
    bios = _bios(session)
    mode = firmware_mode()
    secure = _secure_boot(mode)
    tpm_present, tpm_version = _tpm(session)
    notes: list[str] = []
    if not session.available:
        notes.append(session.error or "WMI unavailable")

    have_identity = board["manufacturer"] != "Unavailable" or board["product"] != "Unavailable"
    have_bios = bios["version"] != "Unavailable"
    if not session.available:
        status = Status.UNKNOWN
        message = "Motherboard/BIOS information unavailable (WMI failed)."
    elif have_identity or have_bios:
        status = Status.PASS
        message = (
            f"{board['manufacturer']} {board['product']} · BIOS {bios['version']} "
            f"({bios['date']}) · {mode}"
        ).strip()
        if mode == "UEFI" and secure == "Disabled":
            status = Status.WARNING
            message += " · Secure Boot is disabled"
    else:
        status = Status.UNKNOWN
        message = "Motherboard/BIOS fields were not returned."

    return MotherboardReport(
        board_manufacturer=board["manufacturer"],
        board_product=board["product"],
        board_serial=board["serial"],
        board_version=board["version"],
        bios_version=bios["version"],
        bios_date=bios["date"],
        firmware_mode=mode,
        secure_boot=secure,
        tpm_present=tpm_present,
        tpm_version=tpm_version,
        bios_update="Not checked (use the BIOS update button — never auto-networked).",
        status=status,
        message=message,
        notes=notes,
    )


def _board(session: WmiSession) -> dict[str, str]:
    rows = session.query("Win32_BaseBoard")
    if not rows:
        return {
            "manufacturer": "Unavailable",
            "product": "Unavailable",
            "serial": "Unavailable",
            "version": "Unavailable",
        }
    row = rows[0]
    return {
        "manufacturer": _text(getattr(row, "Manufacturer", None)),
        "product": _text(getattr(row, "Product", None)),
        "serial": _text(getattr(row, "SerialNumber", None)),
        "version": _text(getattr(row, "Version", None)),
    }


def _bios(session: WmiSession) -> dict[str, str]:
    rows = session.query("Win32_BIOS")
    if not rows:
        return {"version": "Unavailable", "date": "Unavailable"}
    row = rows[0]
    version = _text(getattr(row, "SMBIOSBIOSVersion", None))
    raw = getattr(row, "ReleaseDate", None)
    date = _wmi_date(raw) if raw else "Unavailable"
    return {"version": version, "date": date}


def _secure_boot(mode: str) -> str:
    if mode == "Legacy":
        return "Not applicable (Legacy firmware)"
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\SecureBoot\State",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "UEFISecureBootEnabled")
        if int(value) == 1:
            return "Enabled"
        if int(value) == 0:
            return "Disabled"
        return "Unavailable"
    except FileNotFoundError:
        return "Unavailable"
    except OSError:
        logger.debug("Secure Boot registry read failed", exc_info=True)
        return "Unavailable"


def tpm_from_pnp(device_id: str, name: str) -> tuple[str, str] | None:
    """Map a PnP device to TPM presence. Version only when the ACPI HID implies it."""
    ident = device_id.upper()
    label = name.upper()
    if "MSFT0101" in ident:
        return "Present", "2.0 (ACPI MSFT0101)"
    if "PNP0C31" in ident:
        return "Present", "1.2 (ACPI PNP0C31)"
    if "TRUSTED PLATFORM MODULE" in label or label.startswith("TPM"):
        return "Present", "Unavailable"
    return None


def _tpm(session: WmiSession) -> tuple[str, str]:
    ns = session.ns(r"root\cimv2\Security\MicrosoftTpm")
    if ns is not None:
        try:
            rows = list(ns.Win32_Tpm())
        except Exception:
            logger.debug("Win32_Tpm query failed", exc_info=True)
            rows = []
        if rows:
            row = rows[0]
            enabled = getattr(row, "IsEnabled_InitialValue", None)
            if enabled is True:
                present = "Present (enabled)"
            elif enabled is False:
                present = "Present (disabled)"
            else:
                present = "Present"
            version = _text(getattr(row, "SpecVersion", None))
            return present, version

    for row in session.query("Win32_PnPEntity"):
        mapped = tpm_from_pnp(
            str(getattr(row, "DeviceID", "") or ""),
            str(getattr(row, "Name", "") or ""),
        )
        if mapped:
            return mapped
    return "Unavailable (Win32_Tpm needs administrator)", "Unavailable"


def _wmi_date(raw: object) -> str:
    text = str(raw)
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return "Unavailable"


def _text(value: object) -> str:
    if value is None:
        return "Unavailable"
    text = str(value).strip()
    return text if text else "Unavailable"


def _to_result(report: MotherboardReport) -> DiagnosticResult:
    return DiagnosticResult(
        module=MODULE,
        status=report.status,
        message=report.message,
        details={
            "firmware_mode": report.firmware_mode,
            "secure_boot": report.secure_boot,
            "tpm_present": report.tpm_present,
            "secure_boot_off": "true"
            if report.firmware_mode == "UEFI" and report.secure_boot == "Disabled"
            else "false",
        },
    )
