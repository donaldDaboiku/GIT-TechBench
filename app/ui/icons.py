"""Windows Segoe icon font helper.

theme.qss sets QWidget { font-family: Segoe UI }, which overrides QLabel.setFont().
Icon widgets must also set font-family in their own stylesheet.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QWidget

ICON_FONT_CANDIDATES = (
    "Segoe MDL2 Assets",
    "Segoe Fluent Icons",
    "Segoe UI Symbol",
)
_FONT_FILES = (
    Path(r"C:\Windows\Fonts\segmdl2.ttf"),
    Path(r"C:\Windows\Fonts\SegoeIcons.ttf"),
)

_family: str | None = None


def icon_font_family() -> str:
    """MDL2 first — nav glyphs use MDL2 code points, not Fluent-only ones."""
    global _family
    if _family:
        return _family
    for path in _FONT_FILES:
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    installed = set(QFontDatabase.families())
    for name in ICON_FONT_CANDIDATES:
        if name in installed:
            _family = name
            return _family
    _family = ICON_FONT_CANDIDATES[0]
    return _family


def icon_font(point_size: int = 14) -> QFont:
    font = QFont(icon_font_family())
    font.setPointSize(point_size)
    return font


def icon_qss(*, point_size: int, color: str | None = None) -> str:
    color_bit = f"color: {color}; " if color else ""
    return (
        f'font-family: "{icon_font_family()}"; font-size: {point_size}pt; '
        f"{color_bit}background: transparent;"
    )


def apply_icon_font(widget: QWidget, point_size: int = 14, color: str | None = None) -> None:
    """Apply the icon font in a way the global QSS cannot override."""
    widget.setFont(icon_font(point_size))
    widget.setStyleSheet(icon_qss(point_size=point_size, color=color))
