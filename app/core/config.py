"""Load JSON config and resolve portable (USB) vs bundled paths."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """Writable app folder: USB/portable directory, or the git checkout in dev."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resource_root() -> Path:
    """Bundled read-only files (config JSON, QSS)."""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        internal = Path(sys.executable).resolve().parent / "_internal"
        if internal.exists():
            return internal
        return Path(sys.executable).resolve().parent
    return project_root()


def config_dir() -> Path:
    return resource_root() / "config"


def data_dir(*parts: str) -> Path:
    """Writable subdirectory next to the app (stays on the flash drive)."""
    path = project_root().joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    path = project_root() / "config" / "techbench.ini"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def app_settings():
    """INI settings stored with the app — not the Windows Registry."""
    from PySide6.QtCore import QSettings

    return QSettings(str(settings_path()), QSettings.Format.IniFormat)


def load_json(filename: str) -> dict[str, Any]:
    path = config_dir() / filename
    with path.open(encoding="utf-8") as handle:
        data = json.loads(handle.read())
    if not isinstance(data, dict):
        raise ValueError(f"{filename} must contain a JSON object")
    return data


def load_app_config() -> dict[str, Any]:
    try:
        return load_json("app_config.json")
    except (OSError, ValueError, json.JSONDecodeError):
        return {
            "network": {
                "internet_check_url": "http://www.msftconnecttest.com/connecttest.txt",
                "dns_test_hostname": "www.msftconnecttest.com",
                "ping_count": 4,
                "timeout_seconds": 10,
            },
            "storage": {"space_warning_percent": 90},
        }
