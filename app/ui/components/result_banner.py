"""Status + recommendation banner for a diagnostic result."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from app.models.diagnostic_result import DiagnosticResult
from app.ui.components.status_badge import StatusBadge


class ResultBanner(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        top = QHBoxLayout()
        self.title = QLabel("Result")
        self.title.setObjectName("sectionTitle")
        self.badge = StatusBadge()
        top.addWidget(self.title)
        top.addStretch()
        top.addWidget(self.badge)
        layout.addLayout(top)
        self.message = QLabel("Not run this session.")
        self.message.setWordWrap(True)
        self.message.setObjectName("fieldValue")
        self.recommend = QLabel("")
        self.recommend.setWordWrap(True)
        self.recommend.setObjectName("muted")
        layout.addWidget(self.message)
        layout.addWidget(self.recommend)

    def apply(self, result: DiagnosticResult) -> None:
        self.badge.set_status(result.status)
        self.message.setText(result.message)
        parts = []
        if result.likely_cause:
            parts.append(f"Likely cause (suggestion): {result.likely_cause}")
        if result.recommended_action:
            parts.append(f"Recommended action: {result.recommended_action}")
        if result.confidence:
            parts.append(f"Confidence: {result.confidence.value}")
        if parts:
            parts.append("This is not a confirmed diagnosis. Edit or override before any report.")
        self.recommend.setText("\n".join(parts))
