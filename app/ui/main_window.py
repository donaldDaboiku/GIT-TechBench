"""Main application window."""

from __future__ import annotations

import logging

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QStatusBar, QWidget

from app import APP_NAME, APP_TAGLINE, ORGANIZATION_NAME, __version__
from app.core.config import load_app_config
from app.core.diagnostics_engine import DiagnosticsEngine
from app.core.system_info import SystemInfo
from app.models.diagnostic_result import DiagnosticResult
from app.services.database_service import DatabaseService
from app.services.report_service import ReportService, build_session_record
from app.ui.components.sidebar import Sidebar
from app.ui.dashboard import DashboardPage
from app.ui.nav import NAV_ITEMS
from app.ui.pages.audio_page import AudioPage
from app.ui.pages.battery_page import BatteryPage
from app.ui.pages.camera_page import CameraPage
from app.ui.pages.cpu_page import CpuPage
from app.ui.pages.display_page import DisplayPage
from app.ui.pages.driver_page import DriverPage
from app.ui.pages.full_diagnostic_page import FullDiagnosticPage
from app.ui.pages.gpu_page import GpuPage
from app.ui.pages.hardware_info_page import HardwareInfoPage
from app.ui.pages.keyboard_page import KeyboardPage
from app.ui.pages.memory_page import MemoryPage
from app.ui.pages.motherboard_page import MotherboardPage
from app.ui.pages.mouse_page import MousePage
from app.ui.pages.network_page import NetworkPage
from app.ui.pages.placeholder_page import PlaceholderPage
from app.ui.pages.reports_page import ReportsPage
from app.ui.pages.security_page import SecurityPage
from app.ui.pages.settings_page import SettingsPage
from app.ui.pages.software_page import SoftwarePage
from app.ui.pages.storage_page import StoragePage
from app.ui.pages.usb_page import UsbPage
from app.ui.pages.windows_health_page import WindowsHealthPage
from app.ui.workers import FullDiagnosticWorker, SystemInfoWorker

logger = logging.getLogger("techbench.ui")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — {APP_TAGLINE}")
        self.resize(1280, 820)
        self.setMinimumSize(960, 640)
        self._worker: SystemInfoWorker | None = None
        self._diag_worker: FullDiagnosticWorker | None = None
        self._info: SystemInfo | None = None
        self._results: dict[str, DiagnosticResult] = {}

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.navigate.connect(self._on_navigate)
        layout.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        self.pages: dict[str, QWidget] = {}

        self.dashboard = DashboardPage()
        self.dashboard.scan_requested.connect(self.start_scan)
        self.dashboard.full_diagnostic_requested.connect(self.start_full_diagnostic)
        self.hardware_page = HardwareInfoPage()
        self.settings_page = SettingsPage()
        self.full_page = FullDiagnosticPage()
        self.full_page.run_requested.connect(self.start_full_diagnostic)
        self.full_page.result_ready.connect(self._on_module_result)
        self.keyboard_page = KeyboardPage()
        self.mouse_page = MousePage()
        self.display_page = DisplayPage()
        self.battery_page = BatteryPage()
        self.storage_page = StoragePage()
        self.memory_page = MemoryPage()
        self.network_page = NetworkPage()
        self.cpu_page = CpuPage()
        self.gpu_page = GpuPage()
        self.audio_page = AudioPage()
        self.camera_page = CameraPage()
        self.windows_page = WindowsHealthPage()
        self.motherboard_page = MotherboardPage()
        self.driver_page = DriverPage()
        self.security_page = SecurityPage()
        self.usb_page = UsbPage()
        self.software_page = SoftwarePage()
        self.reports_page = ReportsPage()
        self._db = DatabaseService()
        self._reports = ReportService()
        self.reports_page.save_requested.connect(self._save_session)
        self.reports_page.reopen_requested.connect(self._reopen_session)
        self.reports_page.export_pdf_btn.clicked.connect(self._export_pdf)
        self.reports_page.export_json_btn.clicked.connect(self._export_json)

        self._register("dashboard", self.dashboard)
        self._register("full_diagnostic", self.full_page)
        self._register("hardware_info", self.hardware_page)
        self._register("keyboard", self.keyboard_page)
        self._register("mouse", self.mouse_page)
        self._register("display", self.display_page)
        self._register("battery", self.battery_page)
        self._register("storage", self.storage_page)
        self._register("memory", self.memory_page)
        self._register("network", self.network_page)
        self._register("cpu", self.cpu_page)
        self._register("gpu", self.gpu_page)
        self._register("audio", self.audio_page)
        self._register("camera", self.camera_page)
        self._register("usb", self.usb_page)
        self._register("motherboard", self.motherboard_page)
        self._register("drivers", self.driver_page)
        self._register("security", self.security_page)
        self._register("software", self.software_page)
        self._register("windows", self.windows_page)
        self._register("reports", self.reports_page)
        self._register("settings", self.settings_page)
        for item in NAV_ITEMS:
            if item.id in self.pages:
                continue
            self._register(item.id, PlaceholderPage(item))

        for page in (
            self.keyboard_page,
            self.mouse_page,
            self.display_page,
            self.battery_page,
            self.storage_page,
            self.memory_page,
            self.network_page,
            self.cpu_page,
            self.gpu_page,
            self.audio_page,
            self.camera_page,
            self.windows_page,
            self.motherboard_page,
            self.driver_page,
            self.security_page,
            self.usb_page,
            self.software_page,
        ):
            page.result_ready.connect(self._on_module_result)

        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        status = QStatusBar()
        status.showMessage(f"{APP_NAME} v{__version__}  ·  Phase 5 Reporting")
        self.setStatusBar(status)

        self.sidebar.set_active("dashboard")
        self._refresh_history()
        self.start_scan()

    def _register(self, nav_id: str, widget: QWidget) -> None:
        self.pages[nav_id] = widget
        self.stack.addWidget(widget)

    def _on_navigate(self, nav_id: str) -> None:
        page = self.pages.get(nav_id)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        self.sidebar.set_active(nav_id)
        item = next((n for n in NAV_ITEMS if n.id == nav_id), None)
        if item:
            self.statusBar().showMessage(f"{item.label}  ·  {item.description}")

    def start_scan(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        logger.info("Starting system inventory scan")
        self.dashboard.show_loading("Scanning system inventory…")
        self.statusBar().showMessage("Scanning system inventory…")
        self._worker = SystemInfoWorker(self)
        self._worker.progress.connect(self._on_scan_progress)
        self._worker.succeeded.connect(self._on_scan_ok)
        self._worker.failed.connect(self._on_scan_fail)
        self._worker.start()

    def start_full_diagnostic(self) -> None:
        if self._diag_worker is not None and self._diag_worker.isRunning():
            return
        self._on_navigate("full_diagnostic")
        cfg = load_app_config().get("network") or {}
        settings = QSettings(ORGANIZATION_NAME, APP_NAME)
        url = settings.value("internet_check_url", cfg.get("internet_check_url", ""), str)
        dns = settings.value("dns_test_hostname", cfg.get("dns_test_hostname", ""), str)
        self.full_page.show_running()
        self.statusBar().showMessage("Running automated diagnostics…")
        self._diag_worker = FullDiagnosticWorker(url, dns, self)
        self._diag_worker.progress.connect(self._on_diag_progress)
        self._diag_worker.module_done.connect(self._on_module_result)
        self._diag_worker.succeeded.connect(self._on_diag_ok)
        self._diag_worker.failed.connect(self._on_diag_fail)
        self._diag_worker.start()

    def _on_scan_progress(self, message: str) -> None:
        self.dashboard.show_progress(message)
        self.statusBar().showMessage(message)

    def _on_scan_ok(self, info: SystemInfo) -> None:
        self._info = info
        self.dashboard.apply_info(info)
        self.dashboard.apply_results(self._results)
        self.hardware_page.apply_info(info)
        self.statusBar().showMessage(
            f"Inventory ready for {info.computer_name.display()}  ·  "
            f"{info.cpu_name.display()}  ·  {info.ram_total_display()}"
        )

    def _on_scan_fail(self, message: str) -> None:
        logger.error("Scan failed: %s", message)
        self.dashboard.show_error(message)
        self.statusBar().showMessage(f"Scan failed: {message}")

    def _on_diag_progress(self, message: str) -> None:
        self.full_page.show_progress(message)
        self.statusBar().showMessage(message)

    def _on_diag_ok(self, results: list) -> None:
        engine = DiagnosticsEngine()
        interactive = {
            name: result
            for name, result in self._results.items()
            if name in {"Keyboard", "Mouse", "Display", "Audio", "Camera", "Windows"}
        }
        merged = engine.merge_session(list(results), interactive)
        for item in merged:
            self._on_module_result(item)
        self.full_page.show_idle("Automated checks finished.")
        self.statusBar().showMessage("Automated diagnostics finished.")
        self._save_session(auto=True)

    def _on_diag_fail(self, message: str) -> None:
        self.full_page.show_idle(f"Failed: {message}")
        self.statusBar().showMessage(f"Diagnostic failed: {message}")

    def _on_module_result(self, result: DiagnosticResult) -> None:
        self._results[result.module] = result
        self.full_page.upsert(result)
        self.dashboard.apply_results(self._results)

    def _session_payload(self) -> dict:
        notes = self.reports_page.notes_payload()
        return build_session_record(
            info=self._info,
            results=list(self._results.values()),
            technician_name=self.settings_page.technician_name(),
            **notes,
        )

    def _save_session(self, auto: bool = False) -> None:
        if not self._results:
            self.reports_page.status.setText("Nothing to save yet — run diagnostics first.")
            return
        try:
            session_id = self._db.save(self._session_payload())
        except Exception as exc:
            logger.exception("Failed to save session")
            self.reports_page.status.setText(f"Save failed: {exc}")
            self.statusBar().showMessage(f"Save failed: {exc}")
            return
        how = "Auto-saved" if auto else "Saved"
        message = f"{how} session #{session_id}."
        self._refresh_history(message)
        self.statusBar().showMessage(message)

    def _refresh_history(self, message: str = "") -> None:
        try:
            rows = self._db.list_sessions()
        except Exception as exc:
            logger.exception("History load failed")
            self.reports_page.status.setText(f"History unavailable: {exc}")
            return
        self.reports_page.set_history(rows, message)

    def _reopen_session(self, session_id: object) -> None:
        try:
            session = self._db.get(int(session_id))
        except Exception as exc:
            self.reports_page.status.setText(f"Could not open session: {exc}")
            return
        if not session:
            self.reports_page.status.setText("Session not found.")
            return
        self.reports_page.apply_session_fields(session)
        self._results = {}
        for result in self.reports_page.tests_from_session(session):
            self._on_module_result(result)
        self._on_navigate("full_diagnostic")
        self.reports_page.status.setText(f"Reopened session #{session.get('id')}.")
        self.statusBar().showMessage(f"Reopened session #{session.get('id')}.")

    def _export_json(self) -> None:
        session = self._session_payload()
        path = self.reports_page.chosen_path(".json", self._reports.default_stem(session))
        if path is None:
            return
        try:
            written = self._reports.export_json(session, path)
        except Exception as exc:
            logger.exception("JSON export failed")
            self.reports_page.status.setText(f"JSON export failed: {exc}")
            return
        self.reports_page.status.setText(f"Wrote {written}")
        self.statusBar().showMessage(f"JSON exported: {written}")

    def _export_pdf(self) -> None:
        if not self._reports.export_available():
            self.reports_page.status.setText("PDF export needs the reportlab package.")
            return
        session = self._session_payload()
        path = self.reports_page.chosen_path(".pdf", self._reports.default_stem(session))
        if path is None:
            return
        try:
            written = self._reports.export_pdf(session, path)
        except Exception as exc:
            logger.exception("PDF export failed")
            self.reports_page.status.setText(f"PDF export failed: {exc}")
            return
        self.reports_page.status.setText(f"Wrote {written}")
        self.statusBar().showMessage(f"PDF exported: {written}")

    def closeEvent(self, event) -> None:  # noqa: N802
        self.usb_page.stop_watch()
        super().closeEvent(event)
