"""Memory inventory and Windows Memory Diagnostic shortcut."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from app.core.recommendation_engine import RecommendationEngine
from app.core.system_info import format_bytes
from app.core.windows_commands import is_elevated
from app.models.diagnostic_result import DiagnosticResult
from app.modules.memory.ram_checker import MemoryReport, RamChecker, launch_memory_diagnostic
from app.ui.components.page_header import PageHeader
from app.ui.components.result_banner import ResultBanner
from app.ui.components.scroll_page import ScrollPage
from app.ui.workers import CallableWorker


class MemoryPage(ScrollPage):
    result_ready = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.recommender = RecommendationEngine()
        self._worker: CallableWorker | None = None
        self.body.addWidget(
            PageHeader(
                "Memory Info",
                "Slot map is inventory. Windows Memory Diagnostic is a separate, confirmed action.",
            )
        )
        self.summary = QLabel("—")
        self.summary.setObjectName("fieldValue")
        self.body.addWidget(self.summary)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Locator", "Capacity", "Speed", "Manufacturer", "Part number"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(180)
        self.body.addWidget(self.table)
        scan = QPushButton("Scan memory")
        scan.clicked.connect(self.start)
        self.body.addWidget(scan)
        mdsched = QPushButton("Launch Windows Memory Diagnostic…")
        mdsched.setObjectName("secondaryButton")
        mdsched.clicked.connect(self._mdsched)
        self.body.addWidget(mdsched)
        note = QLabel(
            "Memory Diagnostic schedules a test on reboot. It is not run automatically. "
            + ("This session is elevated." if is_elevated() else "Administrator approval will be required.")
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        self.body.addWidget(note)
        self.banner = ResultBanner()
        self.body.addWidget(self.banner)
        self.body.addStretch()

    def start(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self.summary.setText("Reading Win32_PhysicalMemory…")
        self._worker = CallableWorker(lambda: RamChecker().check(), self)
        self._worker.succeeded.connect(self._ok)
        self._worker.failed.connect(lambda msg: self.summary.setText(msg))
        self._worker.start()

    def _ok(self, payload: object) -> None:
        report, result = payload  # type: ignore[misc]
        self.apply_report(report, result)

    def apply_report(self, report: MemoryReport, result: DiagnosticResult) -> None:
        result = self.recommender.annotate(result)
        total = format_bytes(report.total_bytes) if report.total_bytes else "Unavailable"
        avail = format_bytes(report.available_bytes) if report.available_bytes else "Unavailable"
        used = format_bytes(report.used_bytes) if report.used_bytes else "Unavailable"
        slots = f"{report.slots_used} used"
        if report.slots_total:
            slots += f" / {report.slots_total} total"
        self.summary.setText(f"Total {total}  ·  Used {used}  ·  Available {avail}  ·  {slots}")
        self.table.setRowCount(len(report.slots))
        for i, slot in enumerate(report.slots):
            cap = format_bytes(slot.capacity_bytes) if slot.capacity_bytes else "Unavailable"
            for col, text in enumerate(
                (slot.locator, cap, slot.speed_mhz, slot.manufacturer, slot.part_number)
            ):
                self.table.setItem(i, col, QTableWidgetItem(text))
        self.banner.apply(result)
        self.result_ready.emit(result)

    def _mdsched(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Windows Memory Diagnostic")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(
            "Windows Memory Diagnostic will open the system tool. "
            "It typically schedules a scan on the next reboot and is not run inside TechBench."
        )
        box.setInformativeText("No memory is tested until you confirm inside the Windows dialog.")
        box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        if box.exec() != QMessageBox.StandardButton.Ok:
            return
        ok, message = launch_memory_diagnostic()
        QMessageBox.information(self, "Memory Diagnostic", message) if ok else QMessageBox.warning(
            self, "Memory Diagnostic", message
        )
