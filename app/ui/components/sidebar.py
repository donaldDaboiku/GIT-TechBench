"""Collapsible left navigation."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME
from app.ui.icons import icon_font
from app.ui.nav import NAV_ITEMS, NavItem

EXPANDED_WIDTH = 268
COLLAPSED_WIDTH = 72


class _NavRow(QFrame):
    clicked = Signal(str)

    def __init__(self, item: NavItem, parent=None) -> None:
        super().__init__(parent)
        self.item = item
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(item.label)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)
        self.icon_label = QLabel(item.glyph)
        self.icon_label.setFont(icon_font(16))
        self.icon_label.setFixedWidth(24)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label = QLabel(item.label)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label, 1)
        self.set_selected(False)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.item.id)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool) -> None:
        bg = "#1d4ed8" if selected else "transparent"
        fg = "#ffffff" if selected else "#c5d0dc"
        icon = "#ffffff" if selected else "#3d9cf0"
        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border-radius: 8px; }} "
            f"QLabel {{ background: transparent; color: {fg}; }}"
        )
        self.icon_label.setStyleSheet(f"color: {icon}; background: transparent;")

    def set_collapsed(self, collapsed: bool) -> None:
        self.text_label.setVisible(not collapsed)


class Sidebar(QFrame):
    navigate = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self._collapsed = False
        self._rows: dict[str, _NavRow] = {}
        self._group_labels: list[QLabel] = []
        self.setFixedWidth(EXPANDED_WIDTH)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 16, 12, 12)
        root.setSpacing(10)

        header = QHBoxLayout()
        self.logo = QLabel("GIT")
        self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo.setFixedSize(36, 36)
        self.logo.setStyleSheet(
            "background: #1d4ed8; color: white; border-radius: 10px; font-weight: 800; font-size: 11px;"
        )
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.brand = QLabel(APP_NAME)
        self.brand.setStyleSheet("font-weight: 700; font-size: 13px; background: transparent;")
        self.tag = QLabel("IT Support Toolkit")
        self.tag.setObjectName("muted")
        titles.addWidget(self.brand)
        titles.addWidget(self.tag)
        header.addWidget(self.logo)
        header.addLayout(titles, 1)
        self.collapse_btn = QPushButton("\uE700")
        self.collapse_btn.setObjectName("ghostButton")
        self.collapse_btn.setFont(icon_font(11))
        self.collapse_btn.setFixedSize(32, 32)
        self.collapse_btn.setToolTip("Collapse sidebar")
        self.collapse_btn.clicked.connect(self.toggle)
        header.addWidget(self.collapse_btn, alignment=Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search tools…")
        self.search.textChanged.connect(self._filter)
        root.addWidget(self.search)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        self.nav_layout = QVBoxLayout(body)
        self.nav_layout.setContentsMargins(0, 0, 0, 0)
        self.nav_layout.setSpacing(4)

        current_group = ""
        for item in NAV_ITEMS:
            if item.group != current_group:
                current_group = item.group
                label = QLabel(current_group.upper())
                label.setObjectName("sectionTitle")
                label.setStyleSheet("padding: 12px 8px 4px 8px; background: transparent;")
                self.nav_layout.addWidget(label)
                self._group_labels.append(label)
            row = _NavRow(item)
            row.clicked.connect(self.navigate.emit)
            self._rows[item.id] = row
            self.nav_layout.addWidget(row)

        self.nav_layout.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        self.set_active("dashboard")

    def set_active(self, nav_id: str) -> None:
        for key, row in self._rows.items():
            row.set_selected(key == nav_id)

    def toggle(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.setFixedWidth(COLLAPSED_WIDTH if collapsed else EXPANDED_WIDTH)
        self.search.setVisible(not collapsed)
        self.brand.setVisible(not collapsed)
        self.tag.setVisible(not collapsed)
        for label in self._group_labels:
            label.setVisible(not collapsed)
        for row in self._rows.values():
            row.set_collapsed(collapsed)
        self.collapse_btn.setToolTip("Expand sidebar" if collapsed else "Collapse sidebar")
        self.collapse_btn.setText("\uE70F" if collapsed else "\uE700")

    def _filter(self, text: str) -> None:
        needle = text.strip().lower()
        visible_groups: dict[str, bool] = {}
        for item in NAV_ITEMS:
            row = self._rows[item.id]
            match = not needle or needle in item.label.lower() or needle in item.group.lower()
            row.setVisible(match)
            visible_groups[item.group] = visible_groups.get(item.group, False) or match
        if not self._collapsed:
            shown = set()
            for item in NAV_ITEMS:
                if item.group in shown:
                    continue
                shown.add(item.group)
                # group labels are in insertion order matching unique groups
            idx = 0
            groups_in_order = []
            for item in NAV_ITEMS:
                if item.group not in groups_in_order:
                    groups_in_order.append(item.group)
            for group in groups_in_order:
                self._group_labels[idx].setVisible(visible_groups.get(group, False))
                idx += 1
