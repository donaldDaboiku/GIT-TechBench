"""GPU inventory page."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout

from app.core.recommendation_engine import RecommendationEngine
from app.modules.gpu.gpu_monitor import GpuAdapter, GpuMonitor, GpuReport, format_dedicated
from app.ui.components.page_header import PageHeader
from app.ui.components.result_banner import ResultBanner
from app.ui.components.scroll_page import ScrollPage
from app.ui.workers import CallableWorker


class GpuPage(ScrollPage):
    result_ready = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.recommender = RecommendationEngine()
        self._worker: CallableWorker | None = None
        self.body.addWidget(
            PageHeader(
                "GPU Info",
                "Inventory from Windows. Usage and temperature appear only when a vendor tool exposes them.",
            )
        )
        scan = QPushButton("Scan GPUs")
        scan.clicked.connect(self.start)
        self.body.addWidget(scan)
        self.host = QVBoxLayout()
        self.body.addLayout(self.host)
        self.banner = ResultBanner()
        self.body.addWidget(self.banner)
        self.body.addStretch()

    def start(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._worker = CallableWorker(lambda: GpuMonitor().snapshot(), self)
        self._worker.succeeded.connect(self._ok)
        self._worker.start()

    def _ok(self, payload: object) -> None:
        report, result = payload  # type: ignore[misc]
        self.apply_report(report, result)

    def apply_report(self, report: GpuReport, result) -> None:
        result = self.recommender.annotate(result)
        while self.host.count():
            item = self.host.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        if not report.adapters:
            empty = QLabel("No video controller reported.")
            empty.setObjectName("muted")
            self.host.addWidget(empty)
        for adapter in report.adapters:
            self.host.addWidget(self._card(adapter))
        self.banner.apply(result)
        self.result_ready.emit(result)

    def _card(self, adapter: GpuAdapter) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        for line in (
            adapter.name,
            f"Manufacturer: {adapter.manufacturer}",
            f"Driver: {adapter.driver_version}",
            f"Dedicated memory: {format_dedicated(adapter)}",
            f"Usage: {adapter.usage_percent}",
            f"Temperature: {adapter.temperature_c}",
            f"Source: {adapter.source}",
        ):
            label = QLabel(line)
            label.setWordWrap(True)
            layout.addWidget(label)
        return card
