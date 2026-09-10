"""GPU inventory. Usage/temperature only when a vendor tool or counter exists."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field

from app.core.system_info import format_bytes
from app.core.wmi_session import WmiSession
from app.models.diagnostic_result import DiagnosticResult, Status

logger = logging.getLogger("techbench.gpu")

MODULE = "GPU"
CREATE_NO_WINDOW = 0x08000000


@dataclass
class GpuAdapter:
    name: str
    manufacturer: str
    driver_version: str
    dedicated_bytes: int | None
    dedicated_note: str
    usage_percent: str
    temperature_c: str
    source: str


@dataclass
class GpuReport:
    adapters: list[GpuAdapter] = field(default_factory=list)
    status: Status = Status.UNKNOWN
    message: str = ""


class GpuMonitor:
    phase = 3
    title = "GPU Info"

    def snapshot(self) -> tuple[GpuReport, DiagnosticResult]:
        session = WmiSession()
        session.connect()
        try:
            adapters = _from_wmi(session)
        finally:
            session.close()
        nvidia = _nvidia_smi()
        if nvidia:
            adapters = _merge_nvidia(adapters, nvidia)

        if not adapters:
            report = GpuReport(status=Status.UNKNOWN, message="No video controller reported.")
        else:
            missing_usage = all(a.usage_percent.startswith("Unavail") for a in adapters)
            names = ", ".join(a.name for a in adapters)
            if missing_usage:
                message = f"{len(adapters)} GPU(s): {names}. Usage not accessible on this adapter."
            else:
                message = f"{len(adapters)} GPU(s): {names}."
            report = GpuReport(adapters=adapters, status=Status.PASS, message=message)

        result = DiagnosticResult(
            module=MODULE,
            status=report.status,
            message=report.message,
            details={
                "count": str(len(adapters)),
                "usage_available": "false"
                if not adapters or all(a.usage_percent.startswith("Unavail") for a in adapters)
                else "true",
            },
        )
        return report, result


def _from_wmi(session: WmiSession) -> list[GpuAdapter]:
    adapters: list[GpuAdapter] = []
    for row in session.query("Win32_VideoController"):
        name = _clean(getattr(row, "Name", None))
        if not name:
            continue
        ram_raw = getattr(row, "AdapterRAM", None)
        ram = int(ram_raw) if ram_raw not in (None, "", 0) else None
        note = "From Win32_VideoController.AdapterRAM (may be capped at 4 GiB)"
        if ram is None:
            note = "Dedicated memory unavailable"
        adapters.append(
            GpuAdapter(
                name=name,
                manufacturer=_clean(getattr(row, "AdapterCompatibility", None)) or "Unavailable",
                driver_version=_clean(getattr(row, "DriverVersion", None)) or "Unavailable",
                dedicated_bytes=ram,
                dedicated_note=note,
                usage_percent="Unavailable",
                temperature_c="Unavailable",
                source="WMI Win32_VideoController",
            )
        )
    return adapters


def _nvidia_smi() -> list[dict[str, str]]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    try:
        completed = subprocess.run(
            [
                exe,
                "--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.debug("nvidia-smi failed", exc_info=True)
        return []
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    rows = []
    for line in completed.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue
        rows.append(
            {
                "name": parts[0],
                "driver": parts[1],
                "mem_total": parts[2],
                "mem_used": parts[3],
                "usage": parts[4],
                "temp": parts[5],
            }
        )
    return rows


def _merge_nvidia(adapters: list[GpuAdapter], nvidia: list[dict[str, str]]) -> list[GpuAdapter]:
    for nvi in nvidia:
        matched = next((a for a in adapters if nvi["name"].lower() in a.name.lower()), None)
        mem_mib = _to_int(nvi.get("mem_total"))
        used_mib = _to_int(nvi.get("mem_used"))
        dedicated = mem_mib * 1024 * 1024 if mem_mib is not None else None
        usage = nvi.get("usage", "")
        temp = nvi.get("temp", "")
        if matched:
            matched.driver_version = nvi.get("driver") or matched.driver_version
            if dedicated:
                matched.dedicated_bytes = dedicated
                extra = f"{used_mib} MiB used" if used_mib is not None else ""
                matched.dedicated_note = f"From nvidia-smi {extra}".strip()
            if usage not in {"", "[N/A]"}:
                matched.usage_percent = f"{usage}%"
            if temp not in {"", "[N/A]"}:
                matched.temperature_c = f"{temp} C"
            matched.source = "nvidia-smi"
        else:
            adapters.append(
                GpuAdapter(
                    name=nvi["name"],
                    manufacturer="NVIDIA",
                    driver_version=nvi.get("driver") or "Unavailable",
                    dedicated_bytes=dedicated,
                    dedicated_note="From nvidia-smi",
                    usage_percent=f"{usage}%" if usage not in {"", "[N/A]"} else "Unavailable",
                    temperature_c=f"{temp} C" if temp not in {"", "[N/A]"} else "Unavailable",
                    source="nvidia-smi",
                )
            )
    return adapters


def format_dedicated(adapter: GpuAdapter) -> str:
    if adapter.dedicated_bytes is None:
        return "Unavailable"
    return f"{format_bytes(adapter.dedicated_bytes)} ({adapter.dedicated_note})"


def _clean(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _to_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
