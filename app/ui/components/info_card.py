"""Dashboard hardware summary card."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from app.models.diagnostic_result import Status
from app.ui.components.status_badge import StatusBadge
from app.ui.icons import apply_icon_font


class InfoCard(QFrame):
    def __init__(self, title: str, glyph: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("infoCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        top = QHBoxLayout()
        icon = QLabel(glyph)
        icon.setObjectName("iconGlyph")
        apply_icon_font(icon, 18, "#3d9cf0")
        heading = QLabel(title.upper())
        heading.setObjectName("cardTitle")
        top.addWidget(icon)
        top.addWidget(heading)
        top.addStretch()
        self.badge = StatusBadge(Status.UNKNOWN)
        top.addWidget(self.badge)
        layout.addLayout(top)

        self.spec = QLabel("Waiting for scan…")
        self.spec.setObjectName("cardSpec")
        self.spec.setWordWrap(True)
        layout.addWidget(self.spec)

        self.note = QLabel("Health status is UNKNOWN until a diagnostic module runs.")
        self.note.setObjectName("muted")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        layout.addStretch()

    def update_card(self, spec: str, note: str, status: Status = Status.UNKNOWN) -> None:
        self.spec.setText(spec)
        self.set_health(note, status)

    def set_health(self, note: str, status: Status) -> None:
        self.note.setText(note)
        self.badge.set_status(status)
        self.setToolTip(note)
