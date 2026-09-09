"""Windows Segoe icon font helper."""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase


def icon_font(point_size: int = 14) -> QFont:
    """Prefer Segoe Fluent Icons, then MDL2 Assets (shipped with Windows)."""
    families = set(QFontDatabase.families())
    family = "Segoe MDL2 Assets"
    if "Segoe Fluent Icons" in families:
        family = "Segoe Fluent Icons"
    font = QFont(family)
    font.setPointSize(point_size)
    font.setStyleStrategy(QFont.StyleStrategy.PreferQuality)
    return font
