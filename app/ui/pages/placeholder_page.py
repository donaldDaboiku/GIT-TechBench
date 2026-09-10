"""Placeholder for modules that ship in a later phase."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from app.ui.components.page_header import PageHeader
from app.ui.icons import apply_icon_font
from app.ui.nav import PHASE_LABELS, NavItem


class PlaceholderPage(QWidget):
    def __init__(self, item: NavItem, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(PageHeader(item.label, item.description))

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(12)

        glyph = QLabel(item.glyph)
        glyph.setObjectName("iconGlyph")
        apply_icon_font(glyph, 28, "#3d9cf0")
        phase = QLabel(PHASE_LABELS.get(item.phase, f"Phase {item.phase}"))
        phase.setStyleSheet("font-size: 18px; font-weight: 700; background: transparent;")
        body = QLabel(
            "This tool is listed in the sidebar so navigation is complete, "
            "but the diagnostic logic is not implemented in this phase. "
            "No status is assumed and nothing is marked PASS."
        )
        body.setWordWrap(True)
        body.setObjectName("subtitle")
        extra = QLabel(item.description)
        extra.setWordWrap(True)
        extra.setObjectName("muted")
        card_layout.addWidget(glyph)
        card_layout.addWidget(phase)
        card_layout.addWidget(body)
        card_layout.addWidget(extra)
        layout.addWidget(card)
        layout.addStretch()
