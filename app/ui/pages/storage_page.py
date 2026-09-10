"""Storage health page."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout

from app.core.recommendation_engine import RecommendationEngine
from app.core.system_info import format_bytes
from app.models.diagnostic_result import DiagnosticResult
from app.modules.storage.disk_checker import DiskChecker, DriveReport, StorageReport
from app.ui.components.page_header import PageHeader
from app.ui.components.result_banner import ResultBanner
from app.ui.components.scroll_page import ScrollPage
from app.ui.workers import CallableWorker


class StoragePage(ScrollPage):
    result_ready = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.recommender = RecommendationEngine()
        self._worker: CallableWorker | None = None
        self.body.addWidget(
            PageHeader(
                "Storage Health",
                "SMART is shown only when it can be read from the drive (NVMe health log or ATA SMART). "
                "That usually needs Run as administrator. Missing SMART is never treated as healthy. "
                "USB flash drives typically have no SMART. SSD vs HDD comes from Windows Storage MediaType, "
                "not the drive model name.",
            )
        )
        scan = QPushButton("Scan storage")
        scan.clicked.connect(self.start)
        self.body.addWidget(scan)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.body.addWidget(self.status)
        self.drive_host = QVBoxLayout()
        self.body.addLayout(self.drive_host)
        self.banner = ResultBanner()
        self.body.addWidget(self.banner)
        self.body.addStretch()

    def start(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self.status.setText("Reading disks, SMART, and volume usage…")
        self._worker = CallableWorker(lambda: DiskChecker().check(), self)
        self._worker.succeeded.connect(self._ok)
        self._worker.failed.connect(lambda msg: self.status.setText(msg))
        self._worker.start()

    def _ok(self, payload: object) -> None:
        report, result = payload  # type: ignore[misc]
        self.apply_report(report, result)

    def apply_report(self, report: StorageReport, result: DiagnosticResult) -> None:
        result = self.recommender.annotate(result)
        while self.drive_host.count():
            item = self.drive_host.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        if report.volumes:
            vol = QLabel(
                "Volumes: "
                + " · ".join(
                    f"{v.letter} {format_bytes(v.total_bytes) if v.total_bytes else 'Unavailable'} "
                    f"({format_bytes(v.used_bytes) if v.used_bytes is not None else '?'} used, "
                    f"{v.filesystem.display()})"
                    for v in report.volumes
                )
            )
            vol.setWordWrap(True)
            vol.setObjectName("muted")
            self.drive_host.addWidget(vol)
        if not report.drives:
            empty = QLabel("No physical disks enumerated.")
            empty.setObjectName("muted")
            self.drive_host.addWidget(empty)
        for drive in report.drives:
            self.drive_host.addWidget(self._card(drive))
        self.status.setText(report.message)
        self.banner.apply(result)
        self.result_ready.emit(result)

    def _card(self, drive: DriveReport) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        size = format_bytes(drive.size_bytes) if drive.size_bytes else "Unavailable"
        lines = [
            f"{drive.model}  ·  {size}  ·  {drive.kind}  ·  {drive.bus}  ·  {drive.interface}",
            f"Serial: {drive.serial}",
            f"Windows disk health: {drive.windows_health}",
            f"SMART: {drive.smart_note}",
            f"Temperature: {drive.temperature_c}",
            f"Wear / endurance: {drive.wear}",
            f"Available spare: {drive.spare}",
            f"Power-on hours: {drive.power_on_hours}",
        ]
        for line in lines:
            label = QLabel(line)
            label.setWordWrap(True)
            layout.addWidget(label)
        return card
