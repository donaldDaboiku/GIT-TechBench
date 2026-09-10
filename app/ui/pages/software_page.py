"""Software inventory — installed apps and startup programs, read-only."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from app.core.recommendation_engine import RecommendationEngine
from app.models.diagnostic_result import DiagnosticResult
from app.modules.software.software_inventory import SoftwareInventory, SoftwareReport
from app.ui.components.page_header import PageHeader
from app.ui.components.result_banner import ResultBanner
from app.ui.components.scroll_page import ScrollPage
from app.ui.workers import CallableWorker


class SoftwarePage(ScrollPage):
    result_ready = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.recommender = RecommendationEngine()
        self._worker: CallableWorker | None = None
        self._report: SoftwareReport | None = None
        self.body.addWidget(
            PageHeader(
                "Software Inventory",
                "Read-only list from the Uninstall registry and Run keys. No uninstall or disable actions. Task Manager startup impact is Unavailable unless Windows exposes it.",
            )
        )
        scan = QPushButton("Scan installed software")
        scan.clicked.connect(self.start)
        self.body.addWidget(scan)
        self.summary = QLabel("Not scanned this session.")
        self.summary.setObjectName("muted")
        self.body.addWidget(self.summary)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter applications and startup items…")
        self.search.textChanged.connect(self._refresh_tables)
        self.body.addWidget(self.search)
        apps_label = QLabel("INSTALLED APPLICATIONS")
        apps_label.setObjectName("sectionTitle")
        self.body.addWidget(apps_label)
        self.apps = QTableWidget(0, 4)
        self.apps.setHorizontalHeaderLabels(("Name", "Version", "Install date", "Publisher"))
        self.apps.setMinimumHeight(240)
        self.apps.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.body.addWidget(self.apps)
        start_label = QLabel("STARTUP PROGRAMS")
        start_label.setObjectName("sectionTitle")
        self.body.addWidget(start_label)
        self.startup = QTableWidget(0, 4)
        self.startup.setHorizontalHeaderLabels(("Name", "Enabled", "Impact", "Command"))
        self.startup.setMinimumHeight(180)
        self.startup.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.body.addWidget(self.startup)
        self.banner = ResultBanner()
        self.body.addWidget(self.banner)
        self.body.addStretch()

    def start(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self.summary.setText("Reading Uninstall registry and startup keys…")
        self._worker = CallableWorker(lambda: SoftwareInventory().check(), self)
        self._worker.succeeded.connect(self._ok)
        self._worker.failed.connect(lambda msg: self.summary.setText(msg))
        self._worker.start()

    def _ok(self, payload: object) -> None:
        report, result = payload  # type: ignore[misc]
        self.apply_report(report, result)

    def apply_report(self, report: SoftwareReport, result: DiagnosticResult) -> None:
        result = self.recommender.annotate(result)
        self._report = report
        extra = f" Notes: {'; '.join(report.notes)}" if report.notes else ""
        self.summary.setText(f"{report.message}{extra}")
        self._refresh_tables()
        self.banner.apply(result)
        self.result_ready.emit(result)

    def _refresh_tables(self) -> None:
        report = self._report
        self.apps.setRowCount(0)
        self.startup.setRowCount(0)
        if report is None:
            return
        needle = self.search.text().strip().lower()
        for app in report.apps:
            hay = f"{app.name} {app.version} {app.publisher}".lower()
            if needle and needle not in hay:
                continue
            row = self.apps.rowCount()
            self.apps.insertRow(row)
            self.apps.setItem(row, 0, QTableWidgetItem(app.name))
            self.apps.setItem(row, 1, QTableWidgetItem(app.version))
            self.apps.setItem(row, 2, QTableWidgetItem(app.install_date))
            self.apps.setItem(row, 3, QTableWidgetItem(app.publisher))
        for item in report.startup:
            hay = f"{item.name} {item.command} {item.location}".lower()
            if needle and needle not in hay:
                continue
            row = self.startup.rowCount()
            self.startup.insertRow(row)
            self.startup.setItem(row, 0, QTableWidgetItem(item.name))
            self.startup.setItem(row, 1, QTableWidgetItem(item.enabled))
            self.startup.setItem(row, 2, QTableWidgetItem(item.impact))
            self.startup.setItem(row, 3, QTableWidgetItem(item.command))
        self.apps.resizeColumnsToContents()
        self.startup.resizeColumnsToContents()
