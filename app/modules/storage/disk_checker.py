"""Per-drive capacity and SMART when Windows exposes it.

If SMART cannot be read, status is never PASS.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any

from app.core.config import load_app_config
from app.core.system_info import DataOrigin, FieldValue, VolumeInfo, format_bytes
from app.core.wmi_session import WmiSession
from app.models.diagnostic_result import DiagnosticResult, Status

logger = logging.getLogger("techbench.storage")

MODULE = "Storage"
CREATE_NO_WINDOW = 0x08000000


@dataclass
class DriveReport:
    model: str
    serial: str
    kind: str
    bus: str
    media: str
    interface: str
    size_bytes: int | None
    windows_health: str
    smart_available: bool
    smart_predict_failure: bool | None
    smart_note: str
    realloc_or_pending: bool
    temperature_c: str
    volumes: list[str] = field(default_factory=list)


@dataclass
class StorageReport:
    drives: list[DriveReport]
    volumes: list[VolumeInfo]
    space_warning: bool
    status: Status
    message: str


class DiskChecker:
    phase = 2
    title = "Storage Health"

    def check(self) -> tuple[StorageReport, DiagnosticResult]:
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
            details=_details(report),
        )
        return report, result


def overall_from_signals(
    *,
    smart_available: bool,
    predict_failure: bool,
    realloc: bool,
    space_warning: bool,
    windows_unhealthy: bool,
) -> tuple[Status, str]:
    """SMART missing never becomes PASS."""
    if predict_failure or realloc or windows_unhealthy:
        return Status.FAIL, "Storage reported a failure or predictive-failure signal."
    if not smart_available:
        if space_warning:
            return (
                Status.WARNING,
                "Low disk space. SMART information unavailable — health is not assumed.",
            )
        return Status.UNKNOWN, "SMART information unavailable. Drive health is not assumed."
    if space_warning:
        return Status.WARNING, "SMART predictive failure is not set; one or more volumes are low on space."
    return Status.PASS, "No critical SMART or Windows disk-health issues detected."


def _details(report: StorageReport) -> dict[str, str]:
    any_smart = any(d.smart_available for d in report.drives)
    predict = any(d.smart_predict_failure is True for d in report.drives)
    realloc = any(d.realloc_or_pending for d in report.drives)
    kinds = ",".join(d.kind for d in report.drives)
    return {
        "smart_available": "true" if any_smart else "false",
        "smart_predict_failure": "true" if predict else "false",
        "smart_realloc_or_pending": "true" if realloc else "false",
        "space_warning": "true" if report.space_warning else "false",
        "drive_kinds": kinds,
    }


def _clean(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _scalar(value: object) -> object:
    if value in (None, "", "{}"):
        return None
    if isinstance(value, (dict, list)):
        return None
    return value


def classify_drive_kind(media: str, bus: str = "") -> str:
    """SSD / HDD / SCM from Storage MediaType. NVMe bus implies SSD. Never from model name."""
    key = (media or "").strip().upper()
    mapped = {
        "SSD": "SSD",
        "HDD": "HDD",
        "SCM": "SCM",
        "3": "HDD",
        "4": "SSD",
        "5": "SCM",
    }
    if key in mapped:
        return mapped[key]
    if (bus or "").strip().upper() == "NVME":
        return "SSD"
    return "Unavailable"


def _as_int(value: object) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _volumes() -> list[VolumeInfo]:
    import psutil

    volumes: list[VolumeInfo] = []
    try:
        for part in psutil.disk_partitions(all=False):
            if "cdrom" in part.opts.lower() or not part.fstype:
                continue
            letter = part.device.rstrip("\\") or part.mountpoint
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError) as exc:
                volumes.append(
                    VolumeInfo(
                        letter=letter,
                        filesystem=FieldValue.measured(part.fstype),
                        total_bytes=None,
                        used_bytes=None,
                        free_bytes=None,
                        origin=DataOrigin.UNAVAILABLE,
                        note=str(exc),
                    )
                )
                continue
            volumes.append(
                VolumeInfo(
                    letter=letter,
                    filesystem=FieldValue.measured(part.fstype),
                    total_bytes=int(usage.total),
                    used_bytes=int(usage.used),
                    free_bytes=int(usage.free),
                    origin=DataOrigin.MEASURED,
                    note="From psutil.disk_usage",
                )
            )
    except Exception:
        logger.exception("Volume enumeration failed")
    return volumes


def _smart_predict(session: WmiSession) -> list[dict[str, Any]]:
    rows = []
    for item in session.query_wmi("MSStorageDriver_FailurePredictStatus"):
        rows.append(
            {
                "instance": _clean(getattr(item, "InstanceName", None)),
                "predict": bool(getattr(item, "PredictFailure", False)),
            }
        )
    return rows


def _parse_smart_vendor(raw: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"realloc": False, "temp": None}
    if raw is None:
        return result
    try:
        data = bytes(raw)
    except Exception:
        return result
    if len(data) < 362:
        return result
    for i in range(30):
        base = 2 + i * 12
        attr_id = data[base]
        if attr_id == 0:
            continue
        raw_val = int.from_bytes(data[base + 5 : base + 11], "little")
        if attr_id in {5, 196, 197} and raw_val > 0:
            result["realloc"] = True
        if attr_id in {190, 194} and result["temp"] is None:
            temp = data[base + 5]
            if 1 <= temp <= 125:
                result["temp"] = temp
    return result


def _smart_attributes(session: WmiSession) -> list[dict[str, Any]]:
    rows = []
    for item in session.query_wmi("MSStorageDriver_FailurePredictData"):
        parsed = _parse_smart_vendor(getattr(item, "VendorSpecific", None))
        parsed["instance"] = _clean(getattr(item, "InstanceName", None))
        rows.append(parsed)
    return rows


def _match_smart(
    pnp: str,
    serial: str,
    model: str,
    predict_map: list[dict[str, Any]],
    attr_map: list[dict[str, Any]],
) -> dict[str, Any] | None:
    needle = (pnp or serial or model).lower()
    found: dict[str, Any] | None = None
    for row in predict_map:
        inst = str(row.get("instance") or "").lower()
        if needle and (needle in inst or inst in needle):
            found = dict(row)
            break
    if found is None and len(predict_map) == 1:
        found = dict(predict_map[0])
    if found is None:
        return None
    for attr in attr_map:
        inst = str(attr.get("instance") or "").lower()
        if not needle or needle in inst or inst in needle or len(attr_map) == 1:
            found["realloc"] = attr.get("realloc", False)
            found["temp"] = attr.get("temp")
            break
    return found


def _powershell_physical_disks() -> list[dict[str, Any]]:
    script = (
        "Get-PhysicalDisk | ForEach-Object {"
        " $c = $null; try { $c = $_ | Get-StorageReliabilityCounter } catch {};"
        " [pscustomobject]@{"
        " name=$_.FriendlyName; serial=$_.SerialNumber; media=$_.MediaType.ToString();"
        " bus=$_.BusType.ToString(); health=$_.HealthStatus.ToString(); size=$_.Size;"
        " temperature=$(if($c){$c.Temperature}); wear=$(if($c){$c.Wear})"
        " } } | ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=25,
            creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.warning("Get-PhysicalDisk failed", exc_info=True)
        return []
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    rows = []
    for item in data:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _match_ps(serial: str, model: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    serial_l = serial.lower().replace(" ", "")
    model_l = model.lower()
    for row in rows:
        s = str(row.get("serial") or "").lower().replace(" ", "")
        n = str(row.get("name") or "").lower()
        if serial_l and serial_l in s:
            return row
        if model_l and (model_l in n or n in model_l):
            return row
    if len(rows) == 1:
        return rows[0]
    return None


def _collect(session: WmiSession) -> StorageReport:
    cfg = load_app_config().get("storage") or {}
    warn_pct = float(cfg.get("space_warning_percent", 90))
    volumes = _volumes()
    space_warning = False
    for vol in volumes:
        if vol.total_bytes and vol.used_bytes is not None:
            if 100.0 * vol.used_bytes / vol.total_bytes >= warn_pct:
                space_warning = True

    predict_map = _smart_predict(session)
    attr_map = _smart_attributes(session)
    ps_disks = _powershell_physical_disks()
    drives: list[DriveReport] = []

    for row in session.query("Win32_DiskDrive"):
        serial = _clean(getattr(row, "SerialNumber", None)) or "Unavailable"
        model = _clean(getattr(row, "Model", None)) or "Unavailable"
        instance = _clean(getattr(row, "PNPDeviceID", None))
        smart = _match_smart(instance, serial, model, predict_map, attr_map)
        ps = _match_ps(serial, model, ps_disks)
        temp = "Unavailable"
        realloc = False
        predict: bool | None = None
        smart_ok = False
        smart_note = "SMART information unavailable"
        if smart:
            predict = smart.get("predict")
            smart_ok = predict is not None
            realloc = bool(smart.get("realloc"))
            if smart.get("temp") is not None:
                temp = f"{smart['temp']} C (measured SMART)"
            if predict is True:
                smart_note = "SMART predictive failure is set"
            elif predict is False:
                smart_note = "SMART predictive failure is not set"
        if ps:
            temp_ps = _scalar(ps.get("temperature"))
            wear_ps = _scalar(ps.get("wear"))
            if temp_ps is not None and temp.startswith("Unavail"):
                temp = f"{temp_ps} C (Windows reliability counter)"
            if wear_ps is not None:
                smart_note += f"; NVMe wear {wear_ps}"
        windows_health = _clean(getattr(row, "Status", None)) or "Unavailable"
        if ps and ps.get("health"):
            windows_health = str(ps["health"])
        ps_media = str(ps.get("media") or "") if ps else ""
        ps_bus = str(ps.get("bus") or "") if ps else ""
        kind = classify_drive_kind(ps_media, ps_bus)
        drives.append(
            DriveReport(
                model=model,
                serial=serial,
                kind=kind,
                bus=ps_bus or "Unavailable",
                media=ps_media or _clean(getattr(row, "MediaType", None)) or "Unavailable",
                interface=_clean(getattr(row, "InterfaceType", None)) or "Unavailable",
                size_bytes=_as_int(getattr(row, "Size", None)),
                windows_health=windows_health,
                smart_available=smart_ok,
                smart_predict_failure=predict,
                smart_note=smart_note,
                realloc_or_pending=realloc,
                temperature_c=temp,
            )
        )

    if not drives:
        for ps in ps_disks:
            drives.append(
                DriveReport(
                    model=str(ps.get("name") or "Unavailable"),
                    serial=str(ps.get("serial") or "Unavailable"),
                    kind=classify_drive_kind(str(ps.get("media") or ""), str(ps.get("bus") or "")),
                    bus=str(ps.get("bus") or "Unavailable"),
                    media=str(ps.get("media") or "Unavailable"),
                    interface="Unavailable",
                    size_bytes=_as_int(ps.get("size")),
                    windows_health=str(ps.get("health") or "Unavailable"),
                    smart_available=False,
                    smart_predict_failure=None,
                    smart_note="SMART information unavailable",
                    realloc_or_pending=False,
                    temperature_c=(
                        f"{_scalar(ps.get('temperature'))} C (Windows reliability counter)"
                        if _scalar(ps.get("temperature")) is not None
                        else "Unavailable"
                    ),
                )
            )

    vol_labels = [
        f"{v.letter} {format_bytes(v.total_bytes) if v.total_bytes else 'size unavailable'}"
        for v in volumes
    ]
    if drives and vol_labels:
        drives[0].volumes = vol_labels

    predict_fail = any(d.smart_predict_failure is True for d in drives)
    realloc = any(d.realloc_or_pending for d in drives)
    smart_any = any(d.smart_available for d in drives)
    win_bad = any(d.windows_health.lower() in {"unhealthy", "pred fail", "error"} for d in drives)

    if not drives:
        status, message = Status.UNKNOWN, "No physical disks enumerated."
        if space_warning:
            status, message = Status.WARNING, "Low disk space. Physical disk / SMART data unavailable."
    else:
        status, message = overall_from_signals(
            smart_available=smart_any,
            predict_failure=predict_fail,
            realloc=realloc,
            space_warning=space_warning,
            windows_unhealthy=win_bad,
        )
        kinds = [d.kind for d in drives if d.kind in {"SSD", "HDD", "SCM"}]
        if kinds:
            message = f"{', '.join(kinds)}. {message}"

    return StorageReport(
        drives=drives,
        volumes=volumes,
        space_warning=space_warning,
        status=status,
        message=message,
    )
