"""PASS / WARNING / FAIL / UNKNOWN badge."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from app.models.diagnostic_result import Status

_COLORS = {
    Status.PASS: ("#10291f", "#3ecf8e"),
    Status.WARNING: ("#2a2210", "#e6b450"),
    Status.FAIL: ("#2a1416", "#f07178"),
    Status.UNKNOWN: ("#1b2230", "#8b9bb0"),
}


class StatusBadge(QLabel):
    def __init__(self, status: Status = Status.UNKNOWN, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_status(status)

    def set_status(self, status: Status) -> None:
        bg, fg = _COLORS[status]
        self.setText(status.value)
        self.setStyleSheet(
            f"QLabel {{ background: {bg}; color: {fg}; border: 1px solid {fg}; "
            f"border-radius: 8px; padding: 3px 8px; font-size: 10px; font-weight: 700; }}"
        )
