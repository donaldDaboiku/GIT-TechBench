"""CPU snapshot: usage, frequency, temperature if a sensor exists.

Temperature is never fabricated. Missing sensors are reported as unavailable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import psutil

from app.core.config import load_app_config
from app.core.wmi_session import WmiSession
from app.models.diagnostic_result import DiagnosticResult, Status

logger = logging.getLogger("techbench.cpu")

MODULE = "CPU"


@dataclass
class CpuSnapshot:
    name: str
    physical_cores: str
    logical_cores: str
    usage_percent: float | None
    freq_mhz: float | None
    freq_max_mhz: float | None
    temp_c: float | None
    temp_source: str
    throttling_suspected: bool
    status: Status
    message: str


class CpuMonitor:
    phase = 3
    title = "CPU Monitor"

    def snapshot(self, sample_seconds: float = 0.8) -> tuple[CpuSnapshot, DiagnosticResult]:
        cfg = (load_app_config().get("cpu") or {})
        warn_c = float(cfg.get("temp_warning_c", 85))
        fail_c = float(cfg.get("temp_fail_c", 95))
        throttle_usage = float(cfg.get("throttle_usage_percent", 80))
        throttle_ratio = float(cfg.get("throttle_freq_ratio", 0.7))

        name = "Unavailable"
        physical = "Unavailable"
        logical = "Unavailable"
        session = WmiSession()
        session.connect()
        try:
            rows = session.query("Win32_Processor")
            if rows:
                row = rows[0]
                name = _clean(getattr(row, "Name", None)) or name
                if getattr(row, "NumberOfCores", None):
                    physical = str(row.NumberOfCores)
                if getattr(row, "NumberOfLogicalProcessors", None):
                    logical = str(row.NumberOfLogicalProcessors)
        finally:
            session.close()

        if physical == "Unavailable":
            physical = str(psutil.cpu_count(logical=False) or "Unavailable")
        if logical == "Unavailable":
            logical = str(psutil.cpu_count(logical=True) or "Unavailable")

        usage = None
        try:
            usage = float(psutil.cpu_percent(interval=sample_seconds))
        except Exception:
            logger.exception("cpu_percent failed")

        freq_mhz = freq_max = None
        try:
            freq = psutil.cpu_freq()
            if freq:
                freq_mhz = float(freq.current) if freq.current else None
                freq_max = float(freq.max) if freq.max else None
        except Exception:
            logger.exception("cpu_freq failed")

        temp_c, temp_source = read_temperature()
        throttling = False
        if (
            usage is not None
            and usage >= throttle_usage
            and freq_mhz
            and freq_max
            and freq_max > 0
            and freq_mhz < throttle_ratio * freq_max
        ):
            throttling = True

        status, message = _status(usage, temp_c, temp_source, throttling, warn_c, fail_c)
        snap = CpuSnapshot(
            name=name,
            physical_cores=physical,
            logical_cores=logical,
            usage_percent=usage,
            freq_mhz=freq_mhz,
            freq_max_mhz=freq_max,
            temp_c=temp_c,
            temp_source=temp_source,
            throttling_suspected=throttling,
            status=status,
            message=message,
        )
        result = DiagnosticResult(
            module=MODULE,
            status=status,
            message=message,
            details={
                "temp_available": "true" if temp_c is not None else "false",
                "high_temp": "true" if temp_c is not None and temp_c >= warn_c else "false",
                "throttling": "true" if throttling else "false",
            },
        )
        return snap, result


def live_usage() -> tuple[float, float]:
    """Non-blocking-ish: 0.0 interval uses the last psutil window after a prior call."""
    cpu = float(psutil.cpu_percent(interval=None))
    ram = float(psutil.virtual_memory().percent)
    return cpu, ram


def read_temperature() -> tuple[float | None, str]:
    """Return (C, source). Never estimates a value."""
    try:
        sensors = psutil.sensors_temperatures()
    except Exception:
        sensors = {}
    if sensors:
        for name, entries in sensors.items():
            for entry in entries:
                current = getattr(entry, "current", None)
                if current is None:
                    continue
                label = getattr(entry, "label", "") or name
                return float(current), f"psutil:{label}"

    session = WmiSession()
    session.connect()
    try:
        lhm = _libre_hardware(session)
        if lhm is not None:
            return lhm
        acpi = session.query_wmi("MSAcpi_ThermalZoneTemperature")
        temps = []
        for row in acpi:
            raw = getattr(row, "CurrentTemperature", None)
            if raw in (None, 0, ""):
                continue
            try:
                temps.append(int(raw) / 10.0 - 273.15)
            except (TypeError, ValueError):
                continue
        if temps:
            value = max(temps)
            if -20 < value < 150:
                return value, "ACPI thermal zone (not necessarily CPU package)"
    finally:
        session.close()
    return None, "Temperature sensor unavailable"


def _libre_hardware(session: WmiSession) -> tuple[float | None, str] | None:
    if session.client is None:
        return None
    try:
        import wmi as wmi_mod

        lhm = wmi_mod.WMI(namespace="root\\LibreHardwareMonitor")
        for sensor in lhm.Sensor():
            if str(getattr(sensor, "SensorType", "")).lower() != "temperature":
                continue
            name = str(getattr(sensor, "Name", "")).lower()
            if "cpu" not in name and "package" not in name:
                continue
            value = getattr(sensor, "Value", None)
            if value is None:
                continue
            return float(value), f"LibreHardwareMonitor:{getattr(sensor, 'Name', 'CPU')}"
    except Exception:
        logger.debug("LibreHardwareMonitor WMI not present", exc_info=True)
    return None


def _status(
    usage: float | None,
    temp_c: float | None,
    temp_source: str,
    throttling: bool,
    warn_c: float,
    fail_c: float,
) -> tuple[Status, str]:
    if usage is None:
        return Status.UNKNOWN, "CPU usage could not be sampled."
    parts = [f"Usage {usage:.0f}%"]
    if temp_c is None:
        parts.append("temperature sensor unavailable")
    else:
        parts.append(f"{temp_c:.0f} C ({temp_source})")
    if throttling:
        parts.append("frequency well below max under load (possible throttling)")
    message = "; ".join(parts) + "."
    if temp_c is not None and temp_c >= fail_c:
        return Status.FAIL, message
    if (temp_c is not None and temp_c >= warn_c) or throttling:
        return Status.WARNING, message
    return Status.PASS, message


def _clean(value: object) -> str:
    return str(value).strip() if value is not None else ""
