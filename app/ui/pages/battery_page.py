"""Battery health page."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QWidget

from app.core.recommendation_engine import RecommendationEngine
from app.models.diagnostic_result import DiagnosticResult
from app.modules.battery.battery_checker import BatteryChecker, BatteryReport
from app.ui.components.page_header import PageHeader
from app.ui.components.result_banner import ResultBanner
from app.ui.components.scroll_page import ScrollPage
from app.ui.workers import CallableWorker


def _cell(grid: QGridLayout, row: int, col: int, label: str, value: str) -> QLabel:
    name = QLabel(label.upper())
    name.setObjectName("fieldLabel")
    val = QLabel(value)
    val.setObjectName("fieldValue")
    val.setWordWrap(True)
    wrap = QWidget()
    wrap.setStyleSheet("background: transparent;")
    from PySide6.QtWidgets import QVBoxLayout

    layout = QVBoxLayout(wrap)
    layout.setContentsMargins(0, 0, 8, 8)
    layout.addWidget(name)
    layout.addWidget(val)
    grid.addWidget(wrap, row, col)
    return val


class BatteryPage(ScrollPage):
    result_ready = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.recommender = RecommendationEngine()
        self._worker: CallableWorker | None = None
        self.body.addWidget(
            PageHeader(
                "Battery Health",
                "Health % = Full Charge Capacity / Design Capacity × 100. Capacities are never estimated.",
            )
        )
        self.grid = QGridLayout()
        self.fields: dict[str, QLabel] = {}
        labels = [
            "Name",
            "Manufacturer",
            "Serial",
            "Design capacity",
            "Full charge capacity",
            "Health %",
            "Band",
            "Charge",
            "Power state",
        ]
        for i, label in enumerate(labels):
            self.fields[label] = _cell(self.grid, i // 3, i % 3, label, "—")
        self.body.addLayout(self.grid)
        scan = QPushButton("Scan battery")
        scan.clicked.connect(self.start)
        self.body.addWidget(scan)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.body.addWidget(self.status)
        self.banner = ResultBanner()
        self.body.addWidget(self.banner)
        self.body.addStretch()

    def start(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self.status.setText("Reading battery WMI classes…")
        self._worker = CallableWorker(lambda: BatteryChecker().check(), self)
        self._worker.succeeded.connect(self._ok)
        self._worker.failed.connect(self._fail)
        self._worker.start()

    def _ok(self, payload: object) -> None:
        report, result = payload  # type: ignore[misc]
        self.apply_report(report, result)

    def _fail(self, message: str) -> None:
        self.status.setText(message)

    def apply_report(self, report: BatteryReport, result: DiagnosticResult) -> None:
        result = self.recommender.annotate(result)
        design = (
            f"{report.design_mwh} mWh (measured)"
            if report.design_mwh is not None
            else "Unavailable"
        )
        full = (
            f"{report.full_charge_mwh} mWh (measured)"
            if report.full_charge_mwh is not None
            else "Unavailable"
        )
        health = (
            f"{report.health_percent:.1f}%"
            if report.health_percent is not None
            else "Unavailable"
        )
        values = {
            "Name": report.name,
            "Manufacturer": report.manufacturer,
            "Serial": report.serial,
            "Design capacity": design,
            "Full charge capacity": full,
            "Health %": health,
            "Band": report.health_band,
            "Charge": report.charge_percent,
            "Power state": report.charging,
        }
        for key, text in values.items():
            self.fields[key].setText(text)
        extra = " ".join(report.notes)
        self.status.setText(extra or "Measured capacities use mWh from WMI when the firmware exposes them.")
        self.banner.apply(result)
        self.result_ready.emit(result)
