"""Motherboard / BIOS inventory page."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QPushButton

from app.core.recommendation_engine import RecommendationEngine
from app.models.diagnostic_result import DiagnosticResult
from app.modules.motherboard.motherboard_info import MotherboardInfo, MotherboardReport
from app.ui.components.page_header import PageHeader
from app.ui.components.result_banner import ResultBanner
from app.ui.components.scroll_page import ScrollPage
from app.ui.workers import CallableWorker


class MotherboardPage(ScrollPage):
    result_ready = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.model = MotherboardInfo()
        self.recommender = RecommendationEngine()
        self._worker: CallableWorker | None = None
        self.body.addWidget(
            PageHeader(
                "Motherboard / BIOS",
                "Board identity, firmware mode, Secure Boot, and TPM. BIOS-update check looks for a vendor tool already installed — it never queries the network from Full Diagnostic.",
            )
        )
        scan = QPushButton("Scan motherboard / BIOS")
        scan.clicked.connect(self.start)
        update = QPushButton("Check BIOS update availability")
        update.setObjectName("secondaryButton")
        update.clicked.connect(self._bios_update)
        self.body.addWidget(scan)
        self.body.addWidget(update)
        self.update_note = QLabel("BIOS update: not checked.")
        self.update_note.setWordWrap(True)
        self.update_note.setObjectName("muted")
        self.body.addWidget(self.update_note)
        self.grid_host = QFrame()
        self.grid_host.setObjectName("card")
        self.grid = QGridLayout(self.grid_host)
        self.body.addWidget(self.grid_host)
        self.banner = ResultBanner()
        self.body.addWidget(self.banner)
        self.body.addStretch()

    def start(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._worker = CallableWorker(self.model.check, self)
        self._worker.succeeded.connect(self._ok)
        self._worker.start()

    def _ok(self, payload: object) -> None:
        report, result = payload  # type: ignore[misc]
        self.apply_report(report, result)

    def apply_report(self, report: MotherboardReport, result: DiagnosticResult) -> None:
        result = self.recommender.annotate(result)
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        rows = (
            ("Board manufacturer", report.board_manufacturer),
            ("Board model", report.board_product),
            ("Board serial", report.board_serial),
            ("Board version", report.board_version),
            ("BIOS version", report.bios_version),
            ("BIOS date", report.bios_date),
            ("Firmware mode", report.firmware_mode),
            ("Secure Boot", report.secure_boot),
            ("TPM", report.tpm_present),
            ("TPM spec", report.tpm_version),
        )
        for index, (label, value) in enumerate(rows):
            name = QLabel(label.upper())
            name.setObjectName("fieldLabel")
            val = QLabel(value)
            val.setObjectName("fieldValue")
            val.setWordWrap(True)
            self.grid.addWidget(name, index, 0)
            self.grid.addWidget(val, index, 1)
        self.banner.apply(result)
        self.result_ready.emit(result)

    def _bios_update(self) -> None:
        self.update_note.setText(f"BIOS update: {self.model.check_bios_update()}")
