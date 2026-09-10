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
from app.modules.storage.smart_ioctl import parse_ata_smart, read_physical_drive

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
    wear: str = "Unavailable"
    spare: str = "Unavailable"
    power_on_hours: str = "Unavailable"
    needs_admin: bool = False


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
    needs_admin: bool = False,
) -> tuple[Status, str]:
    """SMART missing never becomes PASS."""
    if predict_failure or realloc or windows_unhealthy:
        return Status.FAIL, "Storage reported a failure or predictive-failure signal."
    if not smart_available:
        admin_note = (
            "SMART/temperature need administrator rights"
            if needs_admin
            else "SMART information unavailable"
        )
        if space_warning:
            return (
                Status.WARNING,
                f"Low disk space. {admin_note} — health is not assumed.",
            )
        return Status.UNKNOWN, f"{admin_note}. Drive health is not assumed."
    if space_warning:
        return Status.WARNING, "SMART predictive failure is not set; one or more volumes are low on space."
    return Status.PASS, "No critical SMART or Windows disk-health issues detected."


def _details(report: StorageReport) -> dict[str, str]:
    targets = _health_drives(report.drives)
    any_smart = any(d.smart_available for d in targets)
    predict = any(d.smart_predict_failure is True for d in targets)
    realloc = any(d.realloc_or_pending for d in targets)
    kinds = ",".join(d.kind for d in report.drives)
    needs_admin = (not any_smart) and any(d.needs_admin for d in targets)
    return {
        "smart_available": "true" if any_smart else "false",
        "smart_predict_failure": "true" if predict else "false",
        "smart_realloc_or_pending": "true" if realloc else "false",
        "space_warning": "true" if report.space_warning else "false",
        "drive_kinds": kinds,
        "smart_needs_admin": "true" if needs_admin else "false",
    }


def _is_usb_drive(bus: str, interface: str) -> bool:
    return "USB" in (bus or "").upper() or (interface or "").upper() == "USB"


def _health_drives(drives: list[DriveReport]) -> list[DriveReport]:
    """USB flash sticks without SMART must not hide an internal disk's result."""
    internal = [d for d in drives if not _is_usb_drive(d.bus, d.interface)]
    return internal or drives


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


def _smart_attributes(session: WmiSession) -> list[dict[str, Any]]:
    rows = []
    for item in session.query_wmi("MSStorageDriver_FailurePredictData"):
        raw = getattr(item, "VendorSpecific", None)
        parsed: dict[str, Any] = {"realloc": False, "temp": None}
        if raw is not None:
            try:
                reading = parse_ata_smart(bytes(raw))
                parsed["realloc"] = reading.realloc_or_pending
                parsed["temp"] = reading.temperature_c
            except Exception:
                logger.debug("WMI SMART vendor blob not parsed", exc_info=True)
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
        ps_bus = str(ps.get("bus") or "") if ps else ""
        interface = _clean(getattr(row, "InterfaceType", None)) or "Unavailable"
        index = _as_int(getattr(row, "Index", None))
        ioctl = None
        if _is_usb_drive(ps_bus, interface):
            if not smart_ok:
                smart_note = "USB devices typically do not expose SMART"
        elif index is not None:
            ioctl = read_physical_drive(index)
        wear = "Unavailable"
        spare = "Unavailable"
        hours = "Unavailable"
        needs_admin = False
        if ioctl is not None:
            if ioctl.available:
                smart_ok = True
                if ioctl.predict_failure is True:
                    predict = True
                elif predict is None:
                    predict = ioctl.predict_failure
                realloc = realloc or ioctl.realloc_or_pending
                smart_note = ioctl.note
            elif ioctl.needs_admin and not smart_ok:
                needs_admin = True
                smart_note = ioctl.note
            elif not smart_ok and ioctl.note != "SMART information unavailable":
                smart_note = ioctl.note
            if ioctl.temperature_c is not None:
                src = ioctl.source or "measured SMART"
                temp = f"{ioctl.temperature_c} C ({src})"
            wear = ioctl.wear
            spare = ioctl.spare
            hours = ioctl.power_on_hours
        if ps:
            temp_ps = _scalar(ps.get("temperature"))
            wear_ps = _scalar(ps.get("wear"))
            if temp_ps is not None and temp.startswith("Unavail"):
                temp = f"{temp_ps} C (Windows reliability counter)"
            if wear_ps is not None and wear.startswith("Unavail"):
                wear = f"{wear_ps}% (Windows reliability counter)"
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
                interface=interface,
                size_bytes=_as_int(getattr(row, "Size", None)),
                windows_health=windows_health,
                smart_available=smart_ok,
                smart_predict_failure=predict,
                smart_note=smart_note,
                realloc_or_pending=realloc,
                temperature_c=temp,
                wear=wear,
                spare=spare,
                power_on_hours=hours,
                needs_admin=needs_admin,
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

    targets = _health_drives(drives)
    predict_fail = any(d.smart_predict_failure is True for d in targets)
    realloc = any(d.realloc_or_pending for d in targets)
    smart_any = any(d.smart_available for d in targets)
    win_bad = any(d.windows_health.lower() in {"unhealthy", "pred fail", "error"} for d in targets)
    needs_admin = (not smart_any) and any(d.needs_admin for d in targets)

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
            needs_admin=needs_admin,
        )
        kinds = [d.kind for d in targets if d.kind in {"SSD", "HDD", "SCM"}]
        if kinds:
            message = f"{', '.join(kinds)}. {message}"

    return StorageReport(
        drives=drives,
        volumes=volumes,
        space_warning=space_warning,
        status=status,
        message=message,
    )
