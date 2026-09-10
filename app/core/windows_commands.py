"""Approved Windows diagnostic command catalog and launchers."""

from __future__ import annotations

import ctypes
import logging
import os
import sys

logger = logging.getLogger("techbench.windows_commands")

CREATE_NO_WINDOW = 0x08000000

APPROVED_COMMANDS: dict[str, dict[str, str]] = {
    "sfc_scan": {
        "label": "System File Checker",
        "command": "sfc /scannow",
        "requires_admin": "true",
        "destructive": "false",
    },
    "dism_health": {
        "label": "DISM component-store health check",
        "command": "DISM /Online /Cleanup-Image /CheckHealth",
        "requires_admin": "true",
        "destructive": "false",
    },
    "chkdsk_readonly": {
        "label": "Check Disk (read-only)",
        "command": "chkdsk {drive}",
        "requires_admin": "true",
        "destructive": "false",
    },
    "mdsched": {
        "label": "Windows Memory Diagnostic",
        "command": "mdsched.exe",
        "requires_admin": "true",
        "destructive": "false",
    },
}


def is_elevated() -> bool:
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        logger.exception("Could not determine administrator rights")
        return False


def open_windows_update() -> None:
    os.startfile("ms-settings:windowsupdate")  # noqa: S606


def open_event_viewer() -> None:
    os.startfile("eventvwr.msc")  # noqa: S606


def open_windows_camera() -> None:
    os.startfile("microsoft.windows.camera:")  # noqa: S606
