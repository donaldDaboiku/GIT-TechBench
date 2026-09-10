"""CPU live monitor."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QWidget

from app.core.recommendation_engine import RecommendationEngine
from app.modules.cpu.cpu_monitor import CpuMonitor, CpuSnapshot, live_usage
from app.ui.components.page_header import PageHeader
from app.ui.components.result_banner import ResultBanner
from app.ui.components.scroll_page import ScrollPage
from app.ui.components.sparkline import Sparkline
from app.ui.workers import CallableWorker


class CpuPage(ScrollPage):
    result_ready = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.recommender = RecommendationEngine()
        self.monitor = CpuMonitor()
        self._worker: CallableWorker | None = None
        live_usage()
        self.body.addWidget(
            PageHeader(
                "CPU Monitor",
                "Live usage graphs. Temperature is shown only when a sensor exists.",
            )
        )
        grid = QGridLayout()
        self.fields: dict[str, QLabel] = {}
        for i, key in enumerate(
            ("Model", "Cores", "Usage", "Frequency", "Temperature", "Throttling")
        ):
            name = QLabel(key.upper())
            name.setObjectName("fieldLabel")
            value = QLabel("—")
            value.setObjectName("fieldValue")
            value.setWordWrap(True)
            wrap = QWidget()
            wrap.setStyleSheet("background: transparent;")
            from PySide6.QtWidgets import QVBoxLayout

            layout = QVBoxLayout(wrap)
            layout.setContentsMargins(0, 0, 8, 8)
            layout.addWidget(name)
            layout.addWidget(value)
            grid.addWidget(wrap, i // 3, i % 3)
            self.fields[key] = value
        self.body.addLayout(grid)
        self.cpu_graph = Sparkline("CPU")
        self.ram_graph = Sparkline("RAM")
        self.body.addWidget(self.cpu_graph)
        self.body.addWidget(self.ram_graph)
        snap = QPushButton("Record diagnostic snapshot")
        snap.clicked.connect(self.record_snapshot)
        self.body.addWidget(snap)
        self.banner = ResultBanner()
        self.body.addWidget(self.banner)
        self.body.addStretch()
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._tick)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        self.timer.stop()
        super().hideEvent(event)

    def _tick(self) -> None:
        cpu, ram = live_usage()
        self.cpu_graph.add(cpu)
        self.ram_graph.add(ram)
        self.fields["Usage"].setText(f"{cpu:.0f}%")

    def record_snapshot(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self.fields["Temperature"].setText("Sampling…")
        self._worker = CallableWorker(lambda: self.monitor.snapshot(0.8), self)
        self._worker.succeeded.connect(self._ok)
        self._worker.start()

    def _ok(self, payload: object) -> None:
        snap, result = payload  # type: ignore[misc]
        self.apply_snapshot(snap, result)

    def apply_snapshot(self, snap: CpuSnapshot, result) -> None:
        result = self.recommender.annotate(result)
        self.fields["Model"].setText(snap.name)
        self.fields["Cores"].setText(f"{snap.physical_cores} physical / {snap.logical_cores} logical")
        self.fields["Usage"].setText(
            f"{snap.usage_percent:.0f}%" if snap.usage_percent is not None else "Unavailable"
        )
        if snap.freq_mhz:
            mx = f" / max {snap.freq_max_mhz:.0f} MHz" if snap.freq_max_mhz else ""
            self.fields["Frequency"].setText(f"{snap.freq_mhz:.0f} MHz{mx}")
        else:
            self.fields["Frequency"].setText("Unavailable")
        if snap.temp_c is None:
            self.fields["Temperature"].setText("Temperature sensor unavailable")
        else:
            self.fields["Temperature"].setText(f"{snap.temp_c:.0f} C ({snap.temp_source})")
        self.fields["Throttling"].setText(
            "Suspected (freq vs load)" if snap.throttling_suspected else "Not indicated"
        )
        self.banner.apply(result)
        self.result_ready.emit(result)
