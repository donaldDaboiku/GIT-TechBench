"""Approved Windows diagnostic command catalog.

Phase 3 implements execution. This module only lists commands and
checks elevation — it never runs DISM, SFC, or chkdsk by itself.
"""

from __future__ import annotations

import ctypes
import logging
import sys

logger = logging.getLogger("techbench.windows_commands")

# Keys are stable IDs used by the UI. Values are display metadata only.
# Destructive or long-running commands must always require explicit confirmation.
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
    """Return True when the process has an elevated administrator token."""
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        logger.exception("Could not determine administrator rights")
        return False
