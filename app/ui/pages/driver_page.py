"""Driver Health page — Device Manager codes, report only."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from app.core.recommendation_engine import RecommendationEngine
from app.core.windows_commands import open_device_manager
from app.models.diagnostic_result import DiagnosticResult
from app.modules.drivers.driver_health import DriverHealth, DriverReport
from app.ui.components.page_header import PageHeader
from app.ui.components.result_banner import ResultBanner
from app.ui.components.scroll_page import ScrollPage
from app.ui.workers import CallableWorker


class DriverPage(ScrollPage):
    result_ready = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.recommender = RecommendationEngine()
        self._worker: CallableWorker | None = None
        self._report: DriverReport | None = None
        self.body.addWidget(
            PageHeader(
                "Driver Health",
                "Reports Device Manager error codes only. TechBench never downloads or installs drivers.",
            )
        )
        row = QHBoxLayout()
        scan = QPushButton("Scan drivers")
        scan.clicked.connect(self.start)
        open_dm = QPushButton("Open Device Manager")
        open_dm.setObjectName("secondaryButton")
        open_dm.clicked.connect(open_device_manager)
        row.addWidget(scan)
        row.addWidget(open_dm)
        row.addStretch()
        self.body.addLayout(row)
        self.summary = QLabel("Not scanned this session.")
        self.summary.setWordWrap(True)
        self.summary.setObjectName("muted")
        self.body.addWidget(self.summary)
        filt = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search devices…")
        self.search.textChanged.connect(self._refresh_table)
        self.show_all = QCheckBox("Show devices with no errors")
        self.show_all.stateChanged.connect(self._refresh_table)
        filt.addWidget(self.search)
        filt.addWidget(self.show_all)
        self.body.addLayout(filt)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(("Device", "Class", "Status", "Driver version", "Driver date"))
        self.table.setMinimumHeight(320)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.body.addWidget(self.table)
        self.banner = ResultBanner()
        self.body.addWidget(self.banner)
        self.body.addStretch()

    def start(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self.summary.setText("Reading Plug and Play devices…")
        self._worker = CallableWorker(lambda: DriverHealth().check(), self)
        self._worker.succeeded.connect(self._ok)
        self._worker.failed.connect(lambda msg: self.summary.setText(msg))
        self._worker.start()

    def _ok(self, payload: object) -> None:
        report, result = payload  # type: ignore[misc]
        self.apply_report(report, result)

    def apply_report(self, report: DriverReport, result: DiagnosticResult) -> None:
        result = self.recommender.annotate(result)
        self._report = report
        extra = ""
        if report.notes:
            extra = " " + " ".join(report.notes)
        self.summary.setText(
            f"{len(report.devices)} device(s) · {report.problem_count} with codes · "
            f"{report.missing_count} missing driver (code 28) · {report.disabled_count} disabled (code 22).{extra}"
        )
        self._refresh_table()
        self.banner.apply(result)
        self.result_ready.emit(result)

    def _refresh_table(self) -> None:
        report = self._report
        self.table.setRowCount(0)
        if report is None:
            return
        needle = self.search.text().strip().lower()
        rows = report.devices if self.show_all.isChecked() else report.problems
        for item in rows:
            hay = f"{item.name} {item.pnp_class} {item.error_label} {item.device_id}".lower()
            if needle and needle not in hay:
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(item.name))
            self.table.setItem(row, 1, QTableWidgetItem(item.pnp_class))
            self.table.setItem(row, 2, QTableWidgetItem(item.error_label))
            self.table.setItem(row, 3, QTableWidgetItem(item.driver_version))
            self.table.setItem(row, 4, QTableWidgetItem(item.driver_date))
        self.table.resizeColumnsToContents()
