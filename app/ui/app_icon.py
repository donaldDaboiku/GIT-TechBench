"""Application window / taskbar icon."""

from __future__ import annotations

from PySide6.QtGui import QIcon

from app.core.config import resource_root


def icon_path():
    return resource_root() / "assets" / "icons" / "techbench.ico"


def window_icon() -> QIcon:
    path = icon_path()
    if path.is_file():
        return QIcon(str(path))
    return QIcon()
