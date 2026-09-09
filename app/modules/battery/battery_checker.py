"""Battery design vs full-charge health.

Health % = Full Charge Capacity / Design Capacity × 100.
Bands: 90–100 Excellent, 75–89 Good, 60–74 Warning, <60 Poor.
Capacities are never estimated.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.wmi_session import WmiSession
from app.models.diagnostic_result import DiagnosticResult, Status

logger = logging.getLogger("techbench.battery")

MODULE = "Battery"


@dataclass
class BatteryReport:
    present: bool
    name: str
    manufacturer: str
    serial: str
    design_mwh: int | None
    full_charge_mwh: int | None
    health_percent: float | None
    health_band: str
    charge_percent: str
    charging: str
    status: Status
    message: str
    notes: list[str]


def health_band(percent: float) -> tuple[str, Status]:
    if percent >= 90:
        return "Excellent", Status.PASS
    if percent >= 75:
        return "Good", Status.PASS
    if percent >= 60:
        return "Warning", Status.WARNING
    return "Poor", Status.FAIL


def health_percent(full_mwh: int, design_mwh: int) -> float | None:
    if design_mwh <= 0 or full_mwh < 0:
        return None
    return 100.0 * full_mwh / design_mwh


class BatteryChecker:
    phase = 2
    title = "Battery Health"

    def check(self) -> tuple[BatteryReport, DiagnosticResult]:
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


def _details(report: BatteryReport) -> dict[str, str]:
    return {
        "present": "true" if report.present else "false",
        "health_band": report.health_band,
        "health_percent": f"{report.health_percent:.1f}" if report.health_percent is not None else "",
    }


def _int(value: object) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _str(value: object) -> str:
    text = str(value).strip() if value is not None else ""
    return text


def _collect(session: WmiSession) -> BatteryReport:
    notes: list[str] = []
    name = "Unavailable"
    manufacturer = "Unavailable"
    serial = "Unavailable"
    design = None
    full = None
    charge = "Unavailable"
    charging = "Unavailable"
    present = False

    try:
        import psutil

        batt = psutil.sensors_battery()
    except Exception:
        logger.exception("psutil.sensors_battery failed")
        batt = None
        notes.append("psutil.sensors_battery failed")

    if batt is not None:
        present = True
        charge = f"{batt.percent:.0f}%"
        charging = "Charging" if batt.power_plugged else "On battery"

    for row in session.query("Win32_Battery"):
        present = True
        name = _str(getattr(row, "Name", None)) or name
        design = design or _int(getattr(row, "DesignCapacity", None))
        remaining = _int(getattr(row, "EstimatedChargeRemaining", None))
        if remaining is not None and charge == "Unavailable":
            charge = f"{remaining}%"
        status_code = _int(getattr(row, "BatteryStatus", None))
        if status_code is not None:
            charging = {
                1: "Discharging",
                2: "On AC (not charging)",
                3: "Fully charged",
                4: "Low",
                5: "Critical",
                6: "Charging",
                7: "Charging / high",
                8: "Charging / low",
                9: "Charging / critical",
                11: "Partially charged",
            }.get(status_code, charging)

    for row in session.query("Win32_PortableBattery"):
        present = True
        name = _str(getattr(row, "Name", None)) or name
        manufacturer = _str(getattr(row, "Manufacturer", None)) or manufacturer
        serial = _str(getattr(row, "SerialNumber", None)) or serial
        location = _str(getattr(row, "Location", None))
        if location and name == "Unavailable":
            name = location
        design = design or _int(getattr(row, "DesignCapacity", None))
        full = full or _int(getattr(row, "FullChargeCapacity", None))

    for row in session.query_wmi("BatteryStaticData"):
        present = True
        design = design or _int(getattr(row, "DesignedCapacity", None))
        manufacturer = _str(getattr(row, "ManufactureName", None)) or manufacturer
        serial = _str(getattr(row, "UniqueID", None)) or serial
        chem = _str(getattr(row, "SerialNumber", None))
        if chem:
            serial = chem

    for row in session.query_wmi("BatteryFullChargedCapacity"):
        present = True
        full = full or _int(getattr(row, "FullChargedCapacity", None))

    if not present:
        return BatteryReport(
            present=False,
            name="No battery detected",
            manufacturer="Unavailable",
            serial="Unavailable",
            design_mwh=None,
            full_charge_mwh=None,
            health_percent=None,
            health_band="N/A",
            charge_percent="Unavailable",
            charging="Unavailable",
            status=Status.UNKNOWN,
            message="No battery detected (typical for a desktop).",
            notes=notes,
        )

    pct = health_percent(full, design) if full is not None and design is not None else None
    if pct is None:
        notes.append("Design and/or full-charge capacity unavailable — health not calculated.")
        return BatteryReport(
            present=True,
            name=name,
            manufacturer=manufacturer,
            serial=serial,
            design_mwh=design,
            full_charge_mwh=full,
            health_percent=None,
            health_band="Unknown",
            charge_percent=charge,
            charging=charging,
            status=Status.UNKNOWN,
            message="Battery present but health % cannot be calculated (capacity data unavailable).",
            notes=notes,
        )

    band, status = health_band(pct)
    message = f"Battery health is {pct:.0f}% ({band})."
    return BatteryReport(
        present=True,
        name=name,
        manufacturer=manufacturer,
        serial=serial,
        design_mwh=design,
        full_charge_mwh=full,
        health_percent=pct,
        health_band=band,
        charge_percent=charge,
        charging=charging,
        status=status,
        message=message,
        notes=notes,
    )
