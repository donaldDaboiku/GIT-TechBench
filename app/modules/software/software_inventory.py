"""Read-only installed-app and startup inventory from the Uninstall registry."""

from __future__ import annotations

import logging
import winreg
from dataclasses import dataclass, field

from app.models.diagnostic_result import DiagnosticResult, Status

logger = logging.getLogger("techbench.software")

MODULE = "Software"

_UNINSTALL_PATHS: tuple[tuple[int, str], ...] = (
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
)

_RUN_PATHS: tuple[tuple[int, str, str], ...] = (
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "HKLM Run"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "HKCU Run"),
)

_APPROVED_PATHS: tuple[tuple[int, str], ...] = (
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"),
)


@dataclass
class InstalledApp:
    name: str
    version: str
    install_date: str
    publisher: str


@dataclass
class StartupItem:
    name: str
    command: str
    location: str
    enabled: str
    impact: str = "Unavailable"


@dataclass
class SoftwareReport:
    apps: list[InstalledApp]
    startup: list[StartupItem]
    status: Status
    message: str
    notes: list[str] = field(default_factory=list)


class SoftwareInventory:
    """Read-only application and startup list."""

    phase = 4
    title = "Software Inventory"

    def check(self) -> tuple[SoftwareReport, DiagnosticResult]:
        report = _collect()
        return report, _to_result(report)


def parse_install_date(raw: object) -> str:
    text = str(raw or "").strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return "Unavailable"


def startup_enabled(approved_blob: bytes | None) -> str:
    """StartupApproved first byte: 2 = enabled, 3 = disabled. Else Unavailable."""
    if not approved_blob:
        return "Enabled"
    first = approved_blob[0]
    if first in (2, 6):  # enabled / enabled (legacy)
        return "Enabled"
    if first in (3, 1):  # disabled by user / disabled
        return "Disabled"
    return "Unavailable"


def _collect() -> SoftwareReport:
    notes: list[str] = []
    apps = _installed(notes)
    startup = _startup(notes)
    if not apps and notes:
        status = Status.UNKNOWN
        message = "Installed-application list could not be read."
    else:
        status = Status.PASS
        message = f"{len(apps)} installed application(s), {len(startup)} startup item(s). Read-only."
    return SoftwareReport(apps=apps, startup=startup, status=status, message=message, notes=notes)


def _installed(notes: list[str]) -> list[InstalledApp]:
    found: dict[str, InstalledApp] = {}
    for hive, path in _UNINSTALL_PATHS:
        try:
            with winreg.OpenKey(hive, path) as root:
                for index in range(winreg.QueryInfoKey(root)[0]):
                    subname = winreg.EnumKey(root, index)
                    try:
                        with winreg.OpenKey(root, subname) as sub:
                            app = _read_app(sub)
                    except OSError:
                        continue
                    if app is None:
                        continue
                    found[app.name.lower()] = app
        except FileNotFoundError:
            continue
        except OSError:
            logger.debug("Uninstall key failed: %s", path, exc_info=True)
            notes.append(f"Could not read {path}")
    return sorted(found.values(), key=lambda item: item.name.lower())


def _read_app(key) -> InstalledApp | None:
    name = _reg_str(key, "DisplayName")
    if not name:
        return None
    if _reg_int(key, "SystemComponent") == 1:
        return None
    if _reg_str(key, "ParentKeyName"):
        return None
    return InstalledApp(
        name=name,
        version=_reg_str(key, "DisplayVersion") or "Unavailable",
        install_date=parse_install_date(_reg_str(key, "InstallDate")),
        publisher=_reg_str(key, "Publisher") or "Unavailable",
    )


def _startup(notes: list[str]) -> list[StartupItem]:
    approved = _approved_map()
    items: list[StartupItem] = []
    seen: set[str] = set()
    for hive, path, location in _RUN_PATHS:
        try:
            with winreg.OpenKey(hive, path) as key:
                for index in range(winreg.QueryInfoKey(key)[1]):
                    name, value, _ = winreg.EnumValue(key, index)
                    key_id = f"{location}:{name}".lower()
                    if key_id in seen:
                        continue
                    seen.add(key_id)
                    blob = approved.get(name.lower())
                    items.append(
                        StartupItem(
                            name=str(name),
                            command=str(value) if value else "Unavailable",
                            location=location,
                            enabled=startup_enabled(blob),
                            impact="Unavailable",
                        )
                    )
        except FileNotFoundError:
            continue
        except OSError:
            logger.debug("Run key failed: %s", path, exc_info=True)
            notes.append(f"Could not read {path}")
    items.sort(key=lambda item: item.name.lower())
    return items


def _approved_map() -> dict[str, bytes]:
    mapping: dict[str, bytes] = {}
    for hive, path in _APPROVED_PATHS:
        try:
            with winreg.OpenKey(hive, path) as key:
                for index in range(winreg.QueryInfoKey(key)[1]):
                    name, value, _ = winreg.EnumValue(key, index)
                    if isinstance(value, bytes):
                        mapping[str(name).lower()] = value
        except FileNotFoundError:
            continue
        except OSError:
            logger.debug("StartupApproved failed: %s", path, exc_info=True)
    return mapping


def _reg_str(key, name: str) -> str:
    try:
        value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return ""
    return str(value).strip() if value is not None else ""


def _reg_int(key, name: str) -> int | None:
    try:
        value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_result(report: SoftwareReport) -> DiagnosticResult:
    return DiagnosticResult(
        module=MODULE,
        status=report.status,
        message=report.message,
        details={
            "app_count": str(len(report.apps)),
            "startup_count": str(len(report.startup)),
        },
    )
