"""Network adapter inventory and connectivity tests."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout

from app.core.config import app_settings, load_app_config
from app.core.recommendation_engine import RecommendationEngine
from app.models.diagnostic_result import DiagnosticResult
from app.modules.network.network_tester import AdapterReport, NetworkReport, NetworkTester
from app.ui.components.page_header import PageHeader
from app.ui.components.result_banner import ResultBanner
from app.ui.components.scroll_page import ScrollPage
from app.ui.workers import CallableWorker


class NetworkPage(ScrollPage):
    result_ready = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.recommender = RecommendationEngine()
        self._worker: CallableWorker | None = None
        cfg = load_app_config().get("network") or {}
        settings = app_settings()
        self.url = settings.value("internet_check_url", cfg.get("internet_check_url", ""), str)
        self.dns = settings.value("dns_test_hostname", cfg.get("dns_test_hostname", ""), str)
        self.body.addWidget(
            PageHeader(
                "Network Test",
                f"Internet check URL is configurable (Settings). Current: {self.url or 'not set'}",
            )
        )
        run = QPushButton("Run network tests")
        run.setToolTip("Gateway ping, DNS, internet URL, and a 1-second traffic sample.")
        run.clicked.connect(self.start)
        self.body.addWidget(run)
        self.status = QLabel("Tests are not started automatically.")
        self.status.setObjectName("muted")
        self.body.addWidget(self.status)
        self.cards = QVBoxLayout()
        self.body.addLayout(self.cards)
        self.banner = ResultBanner()
        self.body.addWidget(self.banner)
        self.body.addStretch()

    def refresh_config(self) -> None:
        cfg = load_app_config().get("network") or {}
        settings = app_settings()
        self.url = settings.value("internet_check_url", cfg.get("internet_check_url", ""), str)
        self.dns = settings.value("dns_test_hostname", cfg.get("dns_test_hostname", ""), str)

    def start(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self.refresh_config()
        self.status.setText("Running ping / DNS / internet checks (does not block the UI)…")
        url, dns = self.url, self.dns
        self._worker = CallableWorker(lambda: NetworkTester(url, dns).check(), self)
        self._worker.succeeded.connect(self._ok)
        self._worker.failed.connect(lambda msg: self.status.setText(msg))
        self._worker.start()

    def _ok(self, payload: object) -> None:
        report, result = payload  # type: ignore[misc]
        self.apply_report(report, result)

    def apply_report(self, report: NetworkReport, result: DiagnosticResult) -> None:
        result = self.recommender.annotate(result)
        while self.cards.count():
            item = self.cards.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        for adapter in report.adapters:
            self.cards.addWidget(self._adapter_card(adapter))
        checks = QFrame()
        checks.setObjectName("card")
        layout = QVBoxLayout(checks)
        layout.addWidget(QLabel(
            f"Gateway ping ({report.gateway_ping.target or 'n/a'}): "
            f"{_flag(report.gateway_ping.ok)}  loss {report.gateway_ping.loss_percent}  "
            f"latency {report.gateway_ping.latency_ms}"
        ))
        layout.addWidget(QLabel(
            f"DNS ({report.dns.target or 'n/a'}): {_flag(report.dns.ok)}  {report.dns.detail}"
        ))
        layout.addWidget(QLabel(
            f"Internet ({report.internet.target or 'n/a'}): {_flag(report.internet.ok)}  {report.internet.detail}"
        ))
        traffic = QLabel(report.traffic)
        traffic.setWordWrap(True)
        layout.addWidget(traffic)
        self.cards.addWidget(checks)
        self.status.setText(report.message)
        self.banner.apply(result)
        self.result_ready.emit(result)

    def _adapter_card(self, adapter: AdapterReport) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        state = "up" if adapter.is_up else "down" if adapter.is_up is False else "unknown"
        dns = ", ".join(adapter.dns) if adapter.dns else "Unavailable"
        for line in (
            adapter.name,
            f"IP {adapter.ip}  ·  MAC {adapter.mac}  ·  {state}",
            f"Gateway {adapter.gateway}  ·  DNS {dns}",
        ):
            label = QLabel(line)
            label.setWordWrap(True)
            layout.addWidget(label)
        return card


def _flag(ok: bool | None) -> str:
    if ok is True:
        return "PASS"
    if ok is False:
        return "FAIL"
    return "UNKNOWN"
