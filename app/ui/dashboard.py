"""Dashboard — identity, hardware summary, and inventory scan."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.system_info import DataOrigin, SystemInfo, format_bytes
from app.models.diagnostic_result import DiagnosticResult, Status
from app.ui.components.info_card import InfoCard
from app.ui.components.page_header import PageHeader


class DashboardPage(QWidget):
    scan_requested = Signal()
    full_diagnostic_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        top = QHBoxLayout()
        self.header = PageHeader(
            "Dashboard",
            "Professional PC Diagnostics & IT Support Toolkit — live inventory scan.",
        )
        top.addWidget(self.header, 1)
        self.refresh_btn = QPushButton("Refresh scan")
        self.refresh_btn.setObjectName("secondaryButton")
        self.refresh_btn.clicked.connect(self.scan_requested.emit)
        top.addWidget(self.refresh_btn)
        layout.addLayout(top)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("muted")
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress)
        layout.addWidget(self.progress_label)

        self.computer_card = QFrame()
        self.computer_card.setObjectName("computerCard")
        card_layout = QVBoxLayout(self.computer_card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_title = QLabel("COMPUTER INFO")
        card_title.setObjectName("sectionTitle")
        card_layout.addWidget(card_title)
        self.identity_grid = QGridLayout()
        self.identity_grid.setHorizontalSpacing(24)
        self.identity_grid.setVerticalSpacing(14)
        self._identity_values: dict[str, QLabel] = {}
        fields = [
            ("computer_name", "Computer name"),
            ("manufacturer", "Manufacturer"),
            ("model", "Model"),
            ("serial", "Serial number"),
            ("os", "Operating system"),
            ("windows", "Windows version"),
            ("cpu", "CPU"),
            ("ram", "Total RAM"),
            ("storage", "Storage summary"),
            ("bios", "BIOS version"),
            ("uptime", "Uptime"),
            ("elevated", "Admin rights"),
        ]
        for i, (key, label) in enumerate(fields):
            cell = QVBoxLayout()
            name = QLabel(label.upper())
            name.setObjectName("fieldLabel")
            value = QLabel("—")
            value.setObjectName("fieldValue")
            value.setWordWrap(True)
            cell.addWidget(name)
            cell.addWidget(value)
            wrap = QWidget()
            wrap.setStyleSheet("background: transparent;")
            wrap.setLayout(cell)
            self.identity_grid.addWidget(wrap, i // 3, i % 3)
            self._identity_values[key] = value
        card_layout.addLayout(self.identity_grid)
        layout.addWidget(self.computer_card)

        hw_title = QLabel("HARDWARE SUMMARY")
        hw_title.setObjectName("sectionTitle")
        layout.addWidget(hw_title)
        hw_note = QLabel(
            "CPU, GPU, battery, storage, memory, and network status update when those diagnostics run."
        )
        hw_note.setObjectName("muted")
        hw_note.setWordWrap(True)
        layout.addWidget(hw_note)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.cpu_card = InfoCard("CPU", "\uE950")
        self.ram_card = InfoCard("RAM", "\uE8C8")
        self.storage_card = InfoCard("Storage", "\uEDA2")
        self.gpu_card = InfoCard("GPU", "\uEA86")
        self.battery_card = InfoCard("Battery", "\uE83F")
        self.network_card = InfoCard("Network", "\uE968")
        for i, card in enumerate(
            (
                self.cpu_card,
                self.ram_card,
                self.storage_card,
                self.gpu_card,
                self.battery_card,
                self.network_card,
            )
        ):
            grid.addWidget(card, i // 3, i % 3)
        layout.addLayout(grid)

        self.run_btn = QPushButton("Run full diagnostic")
        self.run_btn.setMinimumHeight(44)
        self.run_btn.setToolTip(
            "Runs battery, storage, memory, CPU, GPU, and network tests. "
            "Keyboard, mouse, display, audio, and camera stay UNKNOWN until you use those pages."
        )
        self.run_btn.clicked.connect(self.full_diagnostic_requested.emit)
        layout.addWidget(self.run_btn)

        legend = QLabel(
            "Data origin: Measured = read from the OS/WMI/psutil. "
            "Unavailable = the API did not return a value. "
            "Estimated is never used unless a later module explicitly marks it."
        )
        legend.setObjectName("muted")
        legend.setWordWrap(True)
        layout.addWidget(legend)
        layout.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll)

    def show_loading(self, message: str) -> None:
        self.progress.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress_label.setText(message)
        self.refresh_btn.setEnabled(False)
        self.run_btn.setEnabled(False)

    def show_progress(self, message: str) -> None:
        self.progress_label.setText(message)

    def show_error(self, message: str) -> None:
        self.progress.setVisible(False)
        self.progress_label.setVisible(True)
        self.progress_label.setText(f"Scan failed: {message}")
        self.refresh_btn.setEnabled(True)
        self.run_btn.setEnabled(True)

    def apply_info(self, info: SystemInfo) -> None:
        self.progress.setVisible(False)
        self.progress_label.setVisible(True)
        when = info.collected_at.strftime("%Y-%m-%d %H:%M:%S")
        extra = f"  Notes: {'; '.join(info.errors)}" if info.errors else ""
        self.progress_label.setText(f"Last scan {when}.{extra}")
        self.refresh_btn.setEnabled(True)
        self.run_btn.setEnabled(True)

        self._identity_values["computer_name"].setText(info.computer_name.display())
        self._identity_values["manufacturer"].setText(info.manufacturer.display())
        self._identity_values["model"].setText(info.model.display())
        self._identity_values["serial"].setText(info.serial_number.display())
        self._identity_values["os"].setText(info.os_caption.display())
        self._identity_values["windows"].setText(info.windows_version.display())
        self._identity_values["cpu"].setText(info.cpu_name.display())
        self._identity_values["ram"].setText(info.ram_total_display())
        self._identity_values["storage"].setText(info.storage_summary())
        self._identity_values["bios"].setText(info.bios_version.display())
        self._identity_values["uptime"].setText(info.uptime.display())
        self._identity_values["elevated"].setText(
            "Elevated (administrator)" if info.elevated else "Standard user — some later tools will need elevation"
        )

        cores = info.cpu_logical_cores.display()
        self.cpu_card.update_card(
            info.cpu_name.display(),
            f"{info.cpu_physical_cores.display()} physical / {cores} logical · health not scanned",
            Status.UNKNOWN,
        )
        ram_note = info.ram_note or "Measured total capacity"
        if info.ram_available_bytes is not None:
            ram_note = f"{format_bytes(info.ram_available_bytes)} available · {ram_note}"
            self.ram_card.update_card(info.ram_total_display(), ram_note, Status.UNKNOWN)

        storage_note = "Capacity only until Storage Health runs. SMART is not assumed."
        if info.volumes:
            hottest = None
            for vol in info.volumes:
                if vol.total_bytes and vol.used_bytes is not None:
                    pct = 100.0 * vol.used_bytes / vol.total_bytes
                    if hottest is None or pct > hottest[0]:
                        hottest = (pct, vol.letter)
            if hottest and hottest[0] >= 90:
                storage_note = (
                    f"{hottest[1]} is {hottest[0]:.0f}% full (space warning). "
                    "SMART still not scanned."
                )
                self.storage_card.update_card(info.storage_summary(), storage_note, Status.WARNING)
            else:
                self.storage_card.update_card(info.storage_summary(), storage_note, Status.UNKNOWN)
        else:
            self.storage_card.update_card("Unavailable", "No volumes enumerated.", Status.UNKNOWN)

        if info.gpus:
            gpu = info.gpus[0]
            extra_gpu = f"{len(info.gpus)} adapter(s)" if len(info.gpus) > 1 else "Run GPU Info for driver, memory, and usage."
            self.gpu_card.update_card(gpu.name.display(), extra_gpu, Status.UNKNOWN)
        else:
            self.gpu_card.update_card("Unavailable", "No video controller reported.", Status.UNKNOWN)

        if info.battery.present:
            self.battery_card.update_card(
                f"{info.battery.percent.display()} · {info.battery.charging.display()}",
                "Charge level from inventory. Run Battery Health for design vs full-charge %.",
                Status.UNKNOWN,
            )
        else:
            self.battery_card.update_card(
                "No battery detected",
                "Typical for a desktop. Run Battery Health to confirm.",
                Status.UNKNOWN,
            )

        active = next((a for a in info.adapters if a.ipv4.origin == DataOrigin.MEASURED), None)
        if active:
            self.network_card.update_card(
                f"{active.name} · {active.ipv4.display()}",
                "Address only until Network Test runs.",
                Status.UNKNOWN,
            )
        elif info.adapters:
            self.network_card.update_card(
                f"{len(info.adapters)} adapter(s)",
                "No IPv4 address measured on any adapter.",
                Status.UNKNOWN,
            )
        else:
            self.network_card.update_card("Unavailable", "No adapters enumerated.", Status.UNKNOWN)

    def apply_results(self, results: dict[str, DiagnosticResult]) -> None:
        mapping = {
            "CPU": self.cpu_card,
            "Memory": self.ram_card,
            "Storage": self.storage_card,
            "GPU": self.gpu_card,
            "Battery": self.battery_card,
            "Network": self.network_card,
        }
        for module, card in mapping.items():
            result = results.get(module)
            if result:
                card.set_health(result.message, result.status)

