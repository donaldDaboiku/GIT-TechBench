"""Read-only security posture: Defender/AV, firewall, updates, BitLocker."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.wmi_session import WmiSession
from app.models.diagnostic_result import DiagnosticResult, Status

logger = logging.getLogger("techbench.security")

MODULE = "Security"

_FW_DOMAIN = 1
_FW_PRIVATE = 2
_FW_PUBLIC = 4

_BITLOCKER_STATUS = {
    0: "Fully decrypted",
    1: "Fully encrypted",
    2: "Encryption in progress",
    3: "Decryption in progress",
    4: "Encryption paused",
    5: "Decryption paused",
}


@dataclass
class BitLockerVolume:
    drive: str
    protection: str
    conversion: str


@dataclass
class SecurityReport:
    defender_enabled: str
    real_time: str
    av_products: list[str]
    firewall: dict[str, str]
    update_status: str
    bitlocker: list[BitLockerVolume]
    status: Status
    message: str
    notes: list[str] = field(default_factory=list)


class SecurityHealth:
    """Defender, Firewall, Windows Update, BitLocker — read-only."""

    phase = 4
    title = "Security Health"

    def check(self, *, include_updates: bool = True) -> tuple[SecurityReport, DiagnosticResult]:
        session = WmiSession()
        session.connect()
        try:
            report = _collect(session, include_updates=include_updates)
        finally:
            session.close()
        return report, _to_result(report)


def overall_from_flags(
    *,
    av_ok: bool,
    av_known: bool,
    realtime_ok: bool,
    third_party: bool,
    firewall_off: bool,
    firewall_known: bool,
    updates_pending: bool,
    updates_known: bool,
    os_unlocked: bool,
) -> tuple[Status, str]:
    """Compose status from measured flags. Unknown data never becomes PASS."""
    if av_known and not av_ok and not third_party:
        return Status.FAIL, "Windows Defender is off and no third-party antivirus is registered."
    if av_known and not realtime_ok:
        return Status.WARNING, "Antivirus real-time protection is off."
    if firewall_known and firewall_off:
        return Status.WARNING, "Windows Firewall is off on at least one profile."
    if updates_pending:
        return Status.WARNING, "Windows Update reports pending updates."
    if os_unlocked:
        return Status.WARNING, "OS drive is not BitLocker-encrypted."
    if not av_known or not firewall_known:
        return Status.UNKNOWN, "Security status is incomplete — some APIs were unavailable."
    if not updates_known:
        return Status.UNKNOWN, "Antivirus and firewall look enabled; Windows Update status is unconfirmed."
    return Status.PASS, "Antivirus and firewall are enabled; no pending updates in the local cache."


def _collect(session: WmiSession, *, include_updates: bool) -> SecurityReport:
    notes: list[str] = []
    defender_enabled, real_time, defender_known = _defender(session, notes)
    products = _security_center_av(session, notes)
    third_party = any("windows defender" not in name.lower() for name in products)
    av_ok = defender_enabled == "Enabled" or third_party
    av_known = defender_known or bool(products)
    realtime_ok = real_time == "Enabled" or (third_party and real_time != "Disabled")

    firewall, firewall_known = _firewall(notes)
    firewall_off = firewall_known and any(value == "Off" for value in firewall.values())

    if include_updates:
        update_status, updates_pending, updates_known = _windows_update(notes)
    else:
        update_status, updates_pending, updates_known = "Not checked", False, False
        notes.append("Windows Update search skipped for this run.")

    volumes = _bitlocker(session, notes)
    os_unlocked = any(item.drive.upper().startswith("C:") and item.conversion == "Fully decrypted" for item in volumes)

    status, message = overall_from_flags(
        av_ok=av_ok,
        av_known=av_known,
        realtime_ok=bool(realtime_ok),
        third_party=third_party,
        firewall_off=firewall_off,
        firewall_known=firewall_known,
        updates_pending=updates_pending,
        updates_known=updates_known,
        os_unlocked=os_unlocked,
    )
    return SecurityReport(
        defender_enabled=defender_enabled,
        real_time=real_time,
        av_products=products,
        firewall=firewall,
        update_status=update_status,
        bitlocker=volumes,
        status=status,
        message=message,
        notes=notes,
    )


def _defender(session: WmiSession, notes: list[str]) -> tuple[str, str, bool]:
    ns = session.ns(r"root\Microsoft\Windows\Defender")
    if ns is None:
        notes.append("Windows Defender WMI namespace unavailable.")
        return "Unavailable", "Unavailable", False
    try:
        rows = list(ns.MSFT_MpComputerStatus())
    except Exception:
        logger.debug("MSFT_MpComputerStatus failed", exc_info=True)
        notes.append("Could not read Defender status (may need elevation).")
        return "Unavailable", "Unavailable", False
    if not rows:
        return "Unavailable", "Unavailable", False
    row = rows[0]
    enabled = _bool_label(getattr(row, "AntivirusEnabled", None))
    realtime = _bool_label(getattr(row, "RealTimeProtectionEnabled", None))
    return enabled, realtime, enabled != "Unavailable"


def _security_center_av(session: WmiSession, notes: list[str]) -> list[str]:
    ns = session.ns(r"root\SecurityCenter2")
    if ns is None:
        notes.append("Security Center namespace unavailable.")
        return []
    try:
        rows = list(ns.AntiVirusProduct())
    except Exception:
        logger.debug("AntiVirusProduct failed", exc_info=True)
        return []
    names: list[str] = []
    for row in rows:
        name = str(getattr(row, "displayName", "") or "").strip()
        if name:
            names.append(name)
    return names


def _firewall(notes: list[str]) -> tuple[dict[str, str], bool]:
    profiles = {"Domain": "Unavailable", "Private": "Unavailable", "Public": "Unavailable"}
    try:
        import win32com.client

        policy = win32com.client.Dispatch("HNetCfg.FwPolicy2")
        profiles = {
            "Domain": "On" if _firewall_profile_on(policy, _FW_DOMAIN) else "Off",
            "Private": "On" if _firewall_profile_on(policy, _FW_PRIVATE) else "Off",
            "Public": "On" if _firewall_profile_on(policy, _FW_PUBLIC) else "Off",
        }
        return profiles, True
    except Exception:
        logger.debug("FwPolicy2 failed", exc_info=True)
        notes.append("Windows Firewall COM interface unavailable.")
        return profiles, False


def _windows_update(notes: list[str]) -> tuple[str, bool, bool]:
    """Search the local update cache only (Online=False). Not proof the PC is patched."""
    try:
        import win32com.client

        session = win32com.client.Dispatch("Microsoft.Update.Session")
        session.ClientApplicationID = "GIT TechBench"
        searcher = session.CreateUpdateSearcher()
        searcher.Online = False
        result = searcher.Search("IsInstalled=0 and IsHidden=0")
        count = int(result.Updates.Count)
        if count > 0:
            return f"{count} pending update(s) in the local cache", True, True
        return "No pending updates in the local cache (not confirmed fully patched)", False, True
    except Exception:
        logger.debug("Windows Update search failed", exc_info=True)
        notes.append("Windows Update search failed or is unavailable.")
        return "Unavailable", False, False


def _bitlocker(session: WmiSession, notes: list[str]) -> list[BitLockerVolume]:
    ns = session.ns(r"root\CIMV2\Security\MicrosoftVolumeEncryption")
    if ns is None:
        notes.append("BitLocker status unavailable (administrator required).")
        return []
    try:
        rows = list(ns.Win32_EncryptableVolume())
    except Exception:
        logger.debug("Win32_EncryptableVolume failed", exc_info=True)
        notes.append("BitLocker status unavailable (often requires elevation).")
        return []
    volumes: list[BitLockerVolume] = []
    for row in rows:
        letter = str(getattr(row, "DriveLetter", "") or "").strip() or "Unavailable"
        conversion = _wmi_uint(row, "ConversionStatus", "GetConversionStatus")
        protection = _wmi_uint(row, "ProtectionStatus", "GetProtectionStatus")
        prot = {0: "Off", 1: "On", 2: "Unknown"}.get(protection, "Unavailable")
        conv = _BITLOCKER_STATUS.get(conversion, "Unavailable")
        volumes.append(BitLockerVolume(drive=letter, protection=prot, conversion=conv))
    return volumes


def _wmi_uint(row: object, property_name: str, method_name: str) -> int:
    raw = getattr(row, property_name, None)
    if isinstance(raw, int):
        return raw
    method = getattr(row, method_name, None)
    if callable(method):
        try:
            result = method()
        except Exception:
            result = None
        if isinstance(result, int):
            return result
        if isinstance(result, (tuple, list)) and result:
            try:
                return int(result[0])
            except (TypeError, ValueError):
                return -1
    try:
        return int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return -1


def _firewall_profile_on(policy: object, profile: int) -> bool:
    enabled = getattr(policy, "FirewallEnabled")
    try:
        return bool(enabled[profile])
    except Exception:
        return bool(enabled(profile))


def _bool_label(value: object) -> str:
    if value is True:
        return "Enabled"
    if value is False:
        return "Disabled"
    return "Unavailable"


def _to_result(report: SecurityReport) -> DiagnosticResult:
    defender_off = report.defender_enabled == "Disabled"
    third_party = any("windows defender" not in name.lower() for name in report.av_products)
    return DiagnosticResult(
        module=MODULE,
        status=report.status,
        message=report.message,
        details={
            "defender_enabled": report.defender_enabled,
            "real_time": report.real_time,
            "defender_off_no_av": "true" if defender_off and not third_party else "false",
            "update_status": report.update_status,
        },
    )
