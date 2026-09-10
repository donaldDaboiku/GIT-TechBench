"""USB ports — snapshot plus technician plug/unplug watch."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from app.core.recommendation_engine import RecommendationEngine
from app.models.diagnostic_result import DiagnosticResult
from app.modules.usb.usb_port_tester import UsbPortTester, UsbReport, diff_devices
from app.ui.components.page_header import PageHeader
from app.ui.components.result_banner import ResultBanner
from app.ui.components.scroll_page import ScrollPage
from app.ui.workers import CallableWorker, UsbWatchWorker


class UsbPage(ScrollPage):
    result_ready = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.recommender = RecommendationEngine()
        self._worker: CallableWorker | None = None
        self._watch: UsbWatchWorker | None = None
        self._baseline: UsbReport | None = None
        self.body.addWidget(
            PageHeader(
                "USB Ports",
                "Snapshot lists controllers and connected devices. Start watch, then plug or unplug a known-good device. Watch never runs during Full Diagnostic.",
            )
        )
        row = QHBoxLayout()
        snap = QPushButton("Scan USB snapshot")
        snap.clicked.connect(self.start)
        self.watch_btn = QPushButton("Start plug/unplug watch")
        self.watch_btn.setObjectName("secondaryButton")
        self.watch_btn.clicked.connect(self._toggle_watch)
        row.addWidget(snap)
        row.addWidget(self.watch_btn)
        row.addStretch()
        self.body.addLayout(row)
        self.status = QLabel("Snapshot is not started automatically.")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        self.body.addWidget(self.status)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(140)
        self.log.setPlaceholderText("Plug/unplug events appear here while watch is running.")
        self.body.addWidget(self.log)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("Name", "Kind", "Status", "Device ID"))
        self.table.setMinimumHeight(240)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.body.addWidget(self.table)
        self.banner = ResultBanner()
        self.body.addWidget(self.banner)
        self.body.addStretch()

    def start(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self.status.setText("Reading USB controllers and devices…")
        self._worker = CallableWorker(lambda: UsbPortTester().snapshot(), self)
        self._worker.succeeded.connect(self._ok)
        self._worker.failed.connect(lambda msg: self.status.setText(msg))
        self._worker.start()

    def _ok(self, payload: object) -> None:
        report, result = payload  # type: ignore[misc]
        self.apply_report(report, result)

    def apply_report(self, report: UsbReport, result: DiagnosticResult) -> None:
        result = self.recommender.annotate(result)
        self._fill_table(report)
        self.status.setText(
            f"{len(report.controllers)} controller(s), {len(report.hubs)} hub(s), "
            f"{len(report.devices)} connected USB device(s)."
        )
        self.banner.apply(result)
        self.result_ready.emit(result)

    def stop_watch(self) -> None:
        if self._watch is None:
            return
        if self._watch.isRunning():
            self._watch.stop()
            self._watch.wait(2000)
        self._watch = None
        self.watch_btn.setText("Start plug/unplug watch")

    def _toggle_watch(self) -> None:
        if self._watch is not None and self._watch.isRunning():
            self.stop_watch()
            self.status.setText("Watch stopped.")
            return
        self.log.appendPlainText("Watch started. Plug or unplug a device…")
        self.watch_btn.setText("Stop watch")
        self._watch = UsbWatchWorker(self)
        self._watch.snapshot.connect(self._on_watch)
        self._watch.failed.connect(lambda msg: self.log.appendPlainText(msg))
        self._watch.start()

    def _on_watch(self, report: object) -> None:
        usb = report  # type: UsbReport
        if self._baseline is None:
            self._baseline = usb
            self._fill_table(usb)
            return
        delta = diff_devices(self._baseline, usb)
        for item in delta.added:
            self.log.appendPlainText(f"Connected: {item.name} ({item.device_id})")
        for item in delta.removed:
            self.log.appendPlainText(f"Removed: {item.name} ({item.device_id})")
        if delta.added or delta.removed:
            self._baseline = usb
            self._fill_table(usb)

    def _fill_table(self, report: UsbReport) -> None:
        self.table.setRowCount(0)
        for item in report.all_items():
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(item.name))
            self.table.setItem(row, 1, QTableWidgetItem(item.kind))
            self.table.setItem(row, 2, QTableWidgetItem(item.error_label))
            self.table.setItem(row, 3, QTableWidgetItem(item.device_id))
        self.table.resizeColumnsToContents()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.stop_watch()
        super().closeEvent(event)
