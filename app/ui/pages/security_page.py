"""Security Health page — read-only Defender, firewall, update, BitLocker."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from app.core.recommendation_engine import RecommendationEngine
from app.core.windows_commands import open_windows_security, open_windows_update
from app.models.diagnostic_result import DiagnosticResult
from app.modules.security.security_health import SecurityHealth, SecurityReport
from app.ui.components.page_header import PageHeader
from app.ui.components.result_banner import ResultBanner
from app.ui.components.scroll_page import ScrollPage
from app.ui.workers import CallableWorker


class SecurityPage(ScrollPage):
    result_ready = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.recommender = RecommendationEngine()
        self._worker: CallableWorker | None = None
        self.body.addWidget(
            PageHeader(
                "Security Health",
                "Read-only. TechBench never enables, disables, or changes Defender, firewall, updates, or BitLocker.",
            )
        )
        row = QHBoxLayout()
        scan = QPushButton("Scan security status")
        scan.clicked.connect(self.start)
        sec = QPushButton("Open Windows Security")
        sec.setObjectName("secondaryButton")
        sec.clicked.connect(open_windows_security)
        upd = QPushButton("Open Windows Update")
        upd.setObjectName("secondaryButton")
        upd.clicked.connect(open_windows_update)
        row.addWidget(scan)
        row.addWidget(sec)
        row.addWidget(upd)
        row.addStretch()
        self.body.addLayout(row)
        self.host = QVBoxLayout()
        self.body.addLayout(self.host)
        self.banner = ResultBanner()
        self.body.addWidget(self.banner)
        self.body.addStretch()

    def start(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._worker = CallableWorker(lambda: SecurityHealth().check(), self)
        self._worker.succeeded.connect(self._ok)
        self._worker.start()

    def _ok(self, payload: object) -> None:
        report, result = payload  # type: ignore[misc]
        self.apply_report(report, result)

    def apply_report(self, report: SecurityReport, result: DiagnosticResult) -> None:
        result = self.recommender.annotate(result)
        while self.host.count():
            item = self.host.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        av = ", ".join(report.av_products) or "None registered in Security Center"
        fw = " · ".join(f"{name} {state}" for name, state in report.firewall.items())
        bit = (
            " · ".join(f"{item.drive} {item.conversion} (protection {item.protection})" for item in report.bitlocker)
            or "Unavailable"
        )
        for title, body in (
            ("Antivirus", f"Defender: {report.defender_enabled} · Real-time: {report.real_time}\n{av}"),
            ("Firewall", fw),
            ("Windows Update", report.update_status),
            ("BitLocker", bit),
        ):
            self.host.addWidget(self._card(title, body))
        if report.notes:
            note = QLabel(" · ".join(report.notes))
            note.setWordWrap(True)
            note.setObjectName("muted")
            self.host.addWidget(note)
        self.banner.apply(result)
        self.result_ready.emit(result)

    def _card(self, title: str, body: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        heading = QLabel(title.upper())
        heading.setObjectName("sectionTitle")
        text = QLabel(body)
        text.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(text)
        return card
