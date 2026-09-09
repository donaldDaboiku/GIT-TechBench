"""RAM inventory and Windows Memory Diagnostic launcher."""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass

from app.core.system_info import format_bytes
from app.core.windows_commands import is_elevated
from app.core.wmi_session import WmiSession
from app.models.diagnostic_result import DiagnosticResult, Status

logger = logging.getLogger("techbench.memory")

MODULE = "Memory"


@dataclass
class MemorySlot:
    locator: str
    capacity_bytes: int | None
    speed_mhz: str
    manufacturer: str
    part_number: str


@dataclass
class MemoryReport:
    total_bytes: int | None
    available_bytes: int | None
    used_bytes: int | None
    slots: list[MemorySlot]
    slots_used: int
    slots_total: int | None
    status: Status
    message: str


class RamChecker:
    phase = 2
    title = "Memory Info"

    def check(self) -> tuple[MemoryReport, DiagnosticResult]:
        session = WmiSession()
        session.connect()
        try:
            report = _collect(session)
        finally:
            session.close()
        result = DiagnosticResult(
            module=MODULE,
            status=report.status,
            message=report.message,
            details={
                "slots_used": str(report.slots_used),
                "slots_total": str(report.slots_total or ""),
            },
        )
        return report, result


def launch_memory_diagnostic() -> tuple[bool, str]:
    """Start mdsched.exe. Caller must have confirmed a possible reboot."""
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    path = os.path.join(system_root, "System32", "mdsched.exe")
    if not os.path.exists(path):
        return False, "Windows Memory Diagnostic (mdsched.exe) was not found."
    try:
        subprocess.Popen([path])
    except OSError as exc:
        return False, f"Could not start Memory Diagnostic: {exc}"
    extra = ""
    if not is_elevated():
        extra = " Windows may prompt for administrator approval."
    return True, "Windows Memory Diagnostic launched." + extra


def _collect(session: WmiSession) -> MemoryReport:
    total = available = used = None
    try:
        import psutil

        vm = psutil.virtual_memory()
        total = int(vm.total)
        available = int(vm.available)
        used = int(vm.used)
    except Exception:
        logger.exception("psutil.virtual_memory failed")

    slots: list[MemorySlot] = []
    for row in session.query("Win32_PhysicalMemory"):
        cap = getattr(row, "Capacity", None)
        slots.append(
            MemorySlot(
                locator=_clean(getattr(row, "DeviceLocator", None)) or "Slot",
                capacity_bytes=int(cap) if cap not in (None, "") else None,
                speed_mhz=_mhz(getattr(row, "Speed", None)),
                manufacturer=_clean(getattr(row, "Manufacturer", None)) or "Unavailable",
                part_number=_clean(getattr(row, "PartNumber", None)) or "Unavailable",
            )
        )

    slots_total: int | None = None
    arrays = session.query("Win32_PhysicalMemoryArray")
    if arrays:
        devices = getattr(arrays[0], "MemoryDevices", None)
        if devices:
            slots_total = int(devices)

    slots_used = len(slots)
    if not slots and total is None:
        status = Status.UNKNOWN
        message = "Memory information could not be retrieved."
    elif not slots:
        status = Status.UNKNOWN
        message = (
            f"Total RAM {format_bytes(total) if total else 'Unavailable'}; "
            "per-slot map unavailable (WMI Win32_PhysicalMemory returned no rows)."
        )
    else:
        status = Status.PASS
        total_label = format_bytes(total) if total else "Unavailable"
        slot_label = f"{slots_used} populated"
        if slots_total:
            slot_label += f" / {slots_total} slots"
        message = f"{total_label} installed ({slot_label}). Slot map is inventory only - not a memory test."

    return MemoryReport(
        total_bytes=total,
        available_bytes=available,
        used_bytes=used,
        slots=slots,
        slots_used=slots_used,
        slots_total=slots_total,
        status=status,
        message=message,
    )


def _clean(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _mhz(value: object) -> str:
    if value in (None, "", 0):
        return "Unavailable"
    return f"{value} MHz"
