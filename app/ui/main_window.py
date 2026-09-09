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
from app.ui.components.sidebar import Sidebar
from app.ui.dashboard import DashboardPage
from app.ui.nav import NAV_ITEMS
from app.ui.pages.battery_page import BatteryPage
from app.ui.pages.display_page import DisplayPage
from app.ui.pages.full_diagnostic_page import FullDiagnosticPage
from app.ui.pages.hardware_info_page import HardwareInfoPage
from app.ui.pages.keyboard_page import KeyboardPage
from app.ui.pages.memory_page import MemoryPage
from app.ui.pages.mouse_page import MousePage
from app.ui.pages.network_page import NetworkPage
from app.ui.pages.placeholder_page import PlaceholderPage
from app.ui.pages.settings_page import SettingsPage
from app.ui.pages.storage_page import StoragePage
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
        ):
            page.result_ready.connect(self._on_module_result)

        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        status = QStatusBar()
        status.showMessage(f"{APP_NAME} v{__version__}  ·  Phase 2 Core Diagnostics")
        self.setStatusBar(status)

        self.sidebar.set_active("dashboard")
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
            if name in {"Keyboard", "Mouse", "Display"}
        }
        merged = engine.merge_session(list(results), interactive)
        for item in merged:
            self._on_module_result(item)
        self.full_page.show_idle("Automated checks finished.")
        self.statusBar().showMessage("Automated diagnostics finished.")

    def _on_diag_fail(self, message: str) -> None:
        self.full_page.show_idle(f"Failed: {message}")
        self.statusBar().showMessage(f"Diagnostic failed: {message}")

    def _on_module_result(self, result: DiagnosticResult) -> None:
        self._results[result.module] = result
        self.full_page.upsert(result)
        self.dashboard.apply_results(self._results)
