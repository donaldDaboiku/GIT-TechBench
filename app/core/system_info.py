"""Live system inventory collector.

Every value is tagged as measured, unavailable, or estimated.
Sensor readings are never invented. OEM placeholder strings are
returned as measured, with a note that they are not unique serials.
"""

from __future__ import annotations

import logging
import platform
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import psutil

from app.core.wmi_session import WmiSession
from app.models.device import Device

logger = logging.getLogger("techbench.system_info")

ProgressFn = Callable[[str], None]


class DataOrigin(str, Enum):
    MEASURED = "measured"
    UNAVAILABLE = "unavailable"
    ESTIMATED = "estimated"


_OEM_PLACEHOLDERS = {
    "",
    "none",
    "n/a",
    "na",
    "to be filled by o.e.m.",
    "to be filled by oem",
    "default string",
    "defaultstring",
    "system serial number",
    "system manufacturer",
    "system product name",
    "unknown",
    "not available",
}


@dataclass
class FieldValue:
    """A single inventory field with provenance."""

    value: str | None
    origin: DataOrigin = DataOrigin.MEASURED
    note: str = ""

    def display(self) -> str:
        if self.origin == DataOrigin.UNAVAILABLE or self.value in (None, ""):
            return "Unavailable"
        return str(self.value)

    @classmethod
    def measured(cls, value: str | None, note: str = "") -> FieldValue:
        text = _clean(value)
        if text is None:
            return cls(None, DataOrigin.UNAVAILABLE, note or "No value returned")
        extra = note
        if text.lower() in _OEM_PLACEHOLDERS:
            extra = (note + " " if note else "") + "OEM placeholder (not a unique identifier)"
        return cls(text, DataOrigin.MEASURED, extra.strip())

    @classmethod
    def unavailable(cls, note: str = "Could not retrieve this value") -> FieldValue:
        return cls(None, DataOrigin.UNAVAILABLE, note)


@dataclass
class VolumeInfo:
    letter: str
    filesystem: FieldValue
    total_bytes: int | None
    used_bytes: int | None
    free_bytes: int | None
    origin: DataOrigin = DataOrigin.MEASURED
    note: str = ""


@dataclass
class PhysicalDiskInfo:
    model: FieldValue
    serial: FieldValue
    size_bytes: int | None
    interface: FieldValue
    media_type: FieldValue


@dataclass
class GpuInfo:
    name: FieldValue
    manufacturer: FieldValue
    driver_version: FieldValue
    adapter_ram_bytes: int | None


@dataclass
class BatterySnapshot:
    present: bool
    percent: FieldValue
    charging: FieldValue
    name: FieldValue = field(default_factory=lambda: FieldValue.unavailable())


@dataclass
class NetworkAdapterSnapshot:
    name: str
    ipv4: FieldValue
    mac: FieldValue
    is_up: bool | None


@dataclass
class SystemInfo:
    """Complete Phase 1 inventory snapshot."""

    collected_at: datetime
    computer_name: FieldValue
    manufacturer: FieldValue
    model: FieldValue
    serial_number: FieldValue
    os_caption: FieldValue
    windows_version: FieldValue
    os_architecture: FieldValue
    bios_version: FieldValue
    bios_date: FieldValue
    uptime: FieldValue
    cpu_name: FieldValue
    cpu_physical_cores: FieldValue
    cpu_logical_cores: FieldValue
    ram_total_bytes: int | None
    ram_available_bytes: int | None
    ram_origin: DataOrigin
    ram_note: str
    volumes: list[VolumeInfo]
    physical_disks: list[PhysicalDiskInfo]
    gpus: list[GpuInfo]
    battery: BatterySnapshot
    adapters: list[NetworkAdapterSnapshot]
    elevated: bool
    errors: list[str] = field(default_factory=list)

    def to_device(self, technician_name: str = "") -> Device:
        return Device(
            name=self.computer_name.display(),
            manufacturer=self.manufacturer.display(),
            model=self.model.display(),
            serial_number=self.serial_number.display(),
            os_caption=self.os_caption.display(),
            windows_version=self.windows_version.display(),
            bios_version=self.bios_version.display(),
            technician_name=technician_name,
        )

    def ram_total_display(self) -> str:
        if self.ram_total_bytes is None:
            return "Unavailable"
        return format_bytes(self.ram_total_bytes)

    def storage_summary(self) -> str:
        if not self.volumes:
            return "Unavailable"
        parts: list[str] = []
        for vol in self.volumes:
            if vol.total_bytes is None:
                parts.append(f"{vol.letter} (size unavailable)")
                continue
            used_pct = ""
            if vol.used_bytes is not None and vol.total_bytes:
                pct = 100.0 * vol.used_bytes / vol.total_bytes
                used_pct = f", {pct:.0f}% used"
            parts.append(f"{vol.letter} {format_bytes(vol.total_bytes)}{used_pct}")
        return " · ".join(parts)


def format_bytes(num: int) -> str:
    """Human-readable binary size (measured bytes → GiB/MiB display)."""
    size = float(num)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{num} B"


def format_uptime(seconds: float) -> str:
    total = int(seconds)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _notify(progress: ProgressFn | None, message: str) -> None:
    logger.info(message)
    if progress:
        progress(message)


def _parse_wmi_datetime(raw: Any) -> str | None:
    text = _clean(raw)
    if not text:
        return None
    # WMI datetime: yyyymmddHHMMSS.mmmmmm±UUU
    try:
        parsed = datetime.strptime(text[:14], "%Y%m%d%H%M%S")
        return parsed.strftime("%Y-%m-%d")
    except ValueError:
        return text


def collect_system_info(progress: ProgressFn | None = None) -> SystemInfo:
    """Collect inventory. Safe to call from a QThread."""
    errors: list[str] = []
    wmi_session = WmiSession()
    _notify(progress, "Connecting to Windows Management Instrumentation...")
    wmi_session.connect()
    if not wmi_session.available:
        errors.append(wmi_session.error or "WMI unavailable")

    try:
        _notify(progress, "Reading computer identity...")
        computer = _read_computer_system(wmi_session, errors)

        _notify(progress, "Reading BIOS / serial...")
        bios = _read_bios(wmi_session, errors)

        _notify(progress, "Reading operating system...")
        osinfo = _read_os(wmi_session, errors)

        _notify(progress, "Reading processor...")
        cpu = _read_cpu(wmi_session, errors)

        _notify(progress, "Reading memory...")
        ram_total, ram_avail, ram_origin, ram_note = _read_ram(wmi_session, errors)

        _notify(progress, "Reading storage...")
        volumes, disks = _read_storage(wmi_session, errors)

        _notify(progress, "Reading graphics adapters...")
        gpus = _read_gpus(wmi_session, errors)

        _notify(progress, "Reading battery...")
        battery = _read_battery(wmi_session, errors)

        _notify(progress, "Reading network adapters...")
        adapters = _read_adapters(errors)

        from app.core.windows_commands import is_elevated

        info = SystemInfo(
            collected_at=datetime.now(),
            computer_name=computer["name"],
            manufacturer=computer["manufacturer"],
            model=computer["model"],
            serial_number=bios["serial"],
            os_caption=osinfo["caption"],
            windows_version=osinfo["version"],
            os_architecture=osinfo["arch"],
            bios_version=bios["version"],
            bios_date=bios["date"],
            uptime=osinfo["uptime"],
            cpu_name=cpu["name"],
            cpu_physical_cores=cpu["physical"],
            cpu_logical_cores=cpu["logical"],
            ram_total_bytes=ram_total,
            ram_available_bytes=ram_avail,
            ram_origin=ram_origin,
            ram_note=ram_note,
            volumes=volumes,
            physical_disks=disks,
            gpus=gpus,
            battery=battery,
            adapters=adapters,
            elevated=is_elevated(),
            errors=errors,
        )
        _notify(progress, "System inventory complete.")
        return info
    finally:
        wmi_session.close()


def _read_computer_system(wmi_session: WmiSession, errors: list[str]) -> dict[str, FieldValue]:
    name = FieldValue.unavailable("Computer name not returned")
    manufacturer = FieldValue.unavailable()
    model = FieldValue.unavailable()

    fallback_name = _clean(platform.node()) or _clean(_env_computer_name())
    if fallback_name:
        name = FieldValue.measured(fallback_name, "From hostname")

    rows = wmi_session.query("Win32_ComputerSystem")
    if rows:
        row = rows[0]
        wmi_name = FieldValue.measured(getattr(row, "Name", None))
        if wmi_name.origin == DataOrigin.MEASURED:
            name = wmi_name
        manufacturer = FieldValue.measured(getattr(row, "Manufacturer", None))
        model = FieldValue.measured(getattr(row, "Model", None))
    elif wmi_session.available:
        errors.append("Win32_ComputerSystem returned no rows")

    return {"name": name, "manufacturer": manufacturer, "model": model}


def _env_computer_name() -> str | None:
    import os

    return os.environ.get("COMPUTERNAME")


def _read_bios(wmi_session: WmiSession, errors: list[str]) -> dict[str, FieldValue]:
    serial = FieldValue.unavailable("BIOS serial not returned")
    version = FieldValue.unavailable()
    bios_date = FieldValue.unavailable()
    rows = wmi_session.query("Win32_BIOS")
    if not rows:
        if wmi_session.available:
            errors.append("Win32_BIOS returned no rows")
        return {"serial": serial, "version": version, "date": bios_date}

    row = rows[0]
    serial = FieldValue.measured(getattr(row, "SerialNumber", None))
    version = FieldValue.measured(getattr(row, "SMBIOSBIOSVersion", None))
    parsed = _parse_wmi_datetime(getattr(row, "ReleaseDate", None))
    bios_date = FieldValue.measured(parsed) if parsed else FieldValue.unavailable()
    return {"serial": serial, "version": version, "date": bios_date}


def _read_os(wmi_session: WmiSession, errors: list[str]) -> dict[str, FieldValue]:
    caption = FieldValue.measured(platform.platform(), "From platform.platform()")
    version = FieldValue.unavailable()
    arch = FieldValue.measured(platform.machine() or None)
    uptime = FieldValue.unavailable()

    try:
        boot = psutil.boot_time()
        uptime = FieldValue.measured(format_uptime(time.time() - boot), "From psutil.boot_time()")
    except Exception:
        logger.exception("psutil boot_time failed")

    rows = wmi_session.query("Win32_OperatingSystem")
    if rows:
        row = rows[0]
        caption = FieldValue.measured(getattr(row, "Caption", None))
        ver = _clean(getattr(row, "Version", None))
        build = _clean(getattr(row, "BuildNumber", None))
        if ver and build and build not in ver:
            version = FieldValue.measured(f"{ver} (build {build})")
        elif ver:
            version = FieldValue.measured(ver)
        arch = FieldValue.measured(getattr(row, "OSArchitecture", None)) or arch
    elif wmi_session.available:
        errors.append("Win32_OperatingSystem returned no rows")

    return {"caption": caption, "version": version, "arch": arch, "uptime": uptime}


def _read_cpu(wmi_session: WmiSession, errors: list[str]) -> dict[str, FieldValue]:
    name = FieldValue.measured(platform.processor() or None, "From platform.processor()")
    physical = FieldValue.unavailable()
    logical = FieldValue.unavailable()

    try:
        logical_count = psutil.cpu_count(logical=True)
        physical_count = psutil.cpu_count(logical=False)
        if logical_count:
            logical = FieldValue.measured(str(logical_count), "From psutil")
        if physical_count:
            physical = FieldValue.measured(str(physical_count), "From psutil")
    except Exception:
        logger.exception("psutil cpu_count failed")

    rows = wmi_session.query("Win32_Processor")
    if rows:
        row = rows[0]
        name = FieldValue.measured(getattr(row, "Name", None)) or name
        cores = getattr(row, "NumberOfCores", None)
        logical_wmi = getattr(row, "NumberOfLogicalProcessors", None)
        if cores:
            physical = FieldValue.measured(str(cores), "From WMI")
        if logical_wmi:
            logical = FieldValue.measured(str(logical_wmi), "From WMI")
    elif wmi_session.available:
        errors.append("Win32_Processor returned no rows")

    return {"name": name, "physical": physical, "logical": logical}


def _read_ram(
    wmi_session: WmiSession, errors: list[str]
) -> tuple[int | None, int | None, DataOrigin, str]:
    total: int | None = None
    available: int | None = None
    origin = DataOrigin.UNAVAILABLE
    note = "Memory figures not returned"

    try:
        vm = psutil.virtual_memory()
        total = int(vm.total)
        available = int(vm.available)
        origin = DataOrigin.MEASURED
        note = "From psutil.virtual_memory()"
    except Exception:
        logger.exception("psutil virtual_memory failed")
        errors.append("psutil virtual_memory failed")

    rows = wmi_session.query("Win32_ComputerSystem")
    if rows and getattr(rows[0], "TotalPhysicalMemory", None):
        wmi_total = int(rows[0].TotalPhysicalMemory)
        if total is None:
            total = wmi_total
            origin = DataOrigin.MEASURED
            note = "From Win32_ComputerSystem.TotalPhysicalMemory"
        elif abs(wmi_total - total) > 16 * 1024 * 1024:
            note += f"; WMI reports {format_bytes(wmi_total)}"

    return total, available, origin, note


def _read_storage(
    wmi_session: WmiSession, errors: list[str]
) -> tuple[list[VolumeInfo], list[PhysicalDiskInfo]]:
    volumes: list[VolumeInfo] = []
    disks: list[PhysicalDiskInfo] = []

    try:
        for part in psutil.disk_partitions(all=False):
            if "cdrom" in part.opts.lower() or not part.fstype:
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError) as exc:
                volumes.append(
                    VolumeInfo(
                        letter=part.device.rstrip("\\") or part.mountpoint,
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
                    letter=part.device.rstrip("\\") or part.mountpoint,
                    filesystem=FieldValue.measured(part.fstype),
                    total_bytes=int(usage.total),
                    used_bytes=int(usage.used),
                    free_bytes=int(usage.free),
                    origin=DataOrigin.MEASURED,
                    note="From psutil.disk_usage",
                )
            )
    except Exception:
        logger.exception("psutil disk_partitions failed")
        errors.append("Volume enumeration failed")

    for row in wmi_session.query("Win32_DiskDrive"):
        size_raw = getattr(row, "Size", None)
        size_bytes = int(size_raw) if size_raw not in (None, "") else None
        disks.append(
            PhysicalDiskInfo(
                model=FieldValue.measured(getattr(row, "Model", None)),
                serial=FieldValue.measured(getattr(row, "SerialNumber", None)),
                size_bytes=size_bytes,
                interface=FieldValue.measured(getattr(row, "InterfaceType", None)),
                media_type=FieldValue.measured(getattr(row, "MediaType", None)),
            )
        )

    return volumes, disks


def _read_gpus(wmi_session: WmiSession, errors: list[str]) -> list[GpuInfo]:
    gpus: list[GpuInfo] = []
    rows = wmi_session.query("Win32_VideoController")
    if not rows:
        if wmi_session.available:
            errors.append("Win32_VideoController returned no rows")
        return gpus
    for row in rows:
        name = _clean(getattr(row, "Name", None))
        if not name:
            continue
        ram_raw = getattr(row, "AdapterRAM", None)
        ram_bytes = int(ram_raw) if ram_raw not in (None, "", 0) else None
        gpus.append(
            GpuInfo(
                name=FieldValue.measured(name),
                manufacturer=FieldValue.measured(getattr(row, "AdapterCompatibility", None)),
                driver_version=FieldValue.measured(getattr(row, "DriverVersion", None)),
                adapter_ram_bytes=ram_bytes,
            )
        )
    return gpus


def _read_battery(wmi_session: WmiSession, errors: list[str]) -> BatterySnapshot:
    present = False
    percent = FieldValue.unavailable("No battery reported")
    charging = FieldValue.unavailable("No battery reported")
    name = FieldValue.unavailable("No battery reported")

    try:
        batt = psutil.sensors_battery()
    except Exception:
        logger.exception("psutil.sensors_battery failed")
        batt = None
        errors.append("psutil.sensors_battery failed")

    if batt is not None:
        present = True
        percent = FieldValue.measured(f"{batt.percent:.0f}%", "From psutil.sensors_battery()")
        charging = FieldValue.measured("Charging" if batt.power_plugged else "On battery")

    rows = wmi_session.query("Win32_Battery")
    if rows:
        present = True
        row = rows[0]
        name = FieldValue.measured(getattr(row, "Name", None))
        remaining = getattr(row, "EstimatedChargeRemaining", None)
        if remaining is not None and percent.origin != DataOrigin.MEASURED:
            percent = FieldValue.measured(f"{remaining}%", "From Win32_Battery")

    if not present:
        name = FieldValue.measured("No battery detected", "Desktop or battery not exposed")
        percent = FieldValue.unavailable("No battery detected")
        charging = FieldValue.unavailable("No battery detected")

    return BatterySnapshot(present=present, percent=percent, charging=charging, name=name)


def _read_adapters(errors: list[str]) -> list[NetworkAdapterSnapshot]:
    adapters: list[NetworkAdapterSnapshot] = []
    try:
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
    except Exception:
        logger.exception("psutil net interfaces failed")
        errors.append("Network adapter enumeration failed")
        return adapters

    for if_name, addr_list in addrs.items():
        ipv4 = FieldValue.unavailable("No IPv4 address")
        mac = FieldValue.unavailable("No MAC address")
        for addr in addr_list:
            family = getattr(addr.family, "name", str(addr.family))
            if family in ("AF_INET", "2") and addr.address and not addr.address.startswith("127."):
                ipv4 = FieldValue.measured(addr.address)
            if family in ("AF_LINK", "AF_PACKET", "-1") or str(addr.family) == "AddressFamily.AF_LINK":
                if addr.address:
                    mac = FieldValue.measured(addr.address)
        st = stats.get(if_name)
        is_up = bool(st.isup) if st else None
        adapters.append(NetworkAdapterSnapshot(name=if_name, ipv4=ipv4, mac=mac, is_up=is_up))
    return adapters


if __name__ == "__main__":
    snapshot = collect_system_info(progress=print)
    print(f"Name:     {snapshot.computer_name.display()}")
    print(f"Make:     {snapshot.manufacturer.display()}")
    print(f"Model:    {snapshot.model.display()}")
    print(f"Serial:   {snapshot.serial_number.display()}")
    print(f"OS:       {snapshot.os_caption.display()}")
    print(f"Version:  {snapshot.windows_version.display()}")
    print(f"CPU:      {snapshot.cpu_name.display()}")
    print(f"RAM:      {snapshot.ram_total_display()}")
    print(f"Storage:  {snapshot.storage_summary()}")
    if snapshot.errors:
        print("Notes:", "; ".join(snapshot.errors))
