"""Technician and application settings."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME, APP_TAGLINE, __version__
from app.core.config import app_settings, load_app_config, project_root
from app.ui.components.page_header import PageHeader


class SettingsPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.settings = app_settings()
        cfg = load_app_config().get("network") or {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(
            PageHeader(
                "Settings",
                "Technician identity and network test endpoints. Values are stored as an INI file in this app folder.",
            )
        )

        card = QFrame()
        card.setObjectName("card")
        form = QVBoxLayout(card)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(8)
        form.addWidget(self._label("TECHNICIAN NAME"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Alex Rivera")
        self.name_edit.setText(self.settings.value("technician_name", "", str))
        form.addWidget(self.name_edit)
        form.addWidget(self._label("INTERNET CHECK URL"))
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://…")
        self.url_edit.setText(
            self.settings.value("internet_check_url", str(cfg.get("internet_check_url") or ""), str)
        )
        form.addWidget(self.url_edit)
        form.addWidget(self._label("DNS TEST HOSTNAME"))
        self.dns_edit = QLineEdit()
        self.dns_edit.setPlaceholderText("hostname only, not a URL")
        self.dns_edit.setText(
            self.settings.value("dns_test_hostname", str(cfg.get("dns_test_hostname") or ""), str)
        )
        form.addWidget(self.dns_edit)
        row = QHBoxLayout()
        save = QPushButton("Save")
        save.clicked.connect(self._save)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        row.addWidget(save)
        row.addWidget(self.status)
        row.addStretch()
        form.addLayout(row)

        about = QFrame()
        about.setObjectName("card")
        about_layout = QVBoxLayout(about)
        about_layout.setContentsMargins(20, 20, 20, 20)
        about_title = QLabel("APPLICATION")
        about_title.setObjectName("fieldLabel")
        about_body = QLabel(
            f"{APP_NAME} {__version__}\n{APP_TAGLINE}\n\n"
            "Phase 6 — Portable. Copy the app folder to a USB stick and run TechBench.exe. "
            "Settings, logs, history, and reports stay in that folder — not installed on the PC.\n\n"
            f"Data folder:\n{project_root()}"
        )
        about_body.setWordWrap(True)
        about_body.setObjectName("subtitle")
        about_layout.addWidget(about_title)
        about_layout.addWidget(about_body)

        layout.addWidget(card)
        layout.addWidget(about)
        layout.addStretch()

    def technician_name(self) -> str:
        return self.settings.value("technician_name", "", str)

    def _label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def _save(self) -> None:
        self.settings.setValue("technician_name", self.name_edit.text().strip())
        self.settings.setValue("internet_check_url", self.url_edit.text().strip())
        self.settings.setValue("dns_test_hostname", self.dns_edit.text().strip())
        self.status.setText("Saved in this app folder (stays on the USB if you run from a flash drive).")
