"""Windows Health command helpers. Nothing runs without the caller confirming."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from app.core.windows_commands import is_elevated
from app.models.diagnostic_result import DiagnosticResult, Status

logger = logging.getLogger("techbench.windows_health")

MODULE = "Windows"


class WindowsHealth:
    phase = 3
    title = "Windows Health"

    def __init__(self) -> None:
        self.last_command = ""
        self.last_exit: int | None = None
        self.ran_any = False

    def to_result(self) -> DiagnosticResult:
        if not self.ran_any:
            return DiagnosticResult(
                module=MODULE,
                status=Status.UNKNOWN,
                message="No Windows Health command has been run this session.",
            )
        code = "unknown" if self.last_exit is None else str(self.last_exit)
        status = Status.PASS if self.last_exit == 0 else Status.WARNING
        return DiagnosticResult(
            module=MODULE,
            status=status,
            message=f"Last command {self.last_command} exited {code}. Review the live output.",
            details={"command": self.last_command, "exit": code},
        )


def system32(name: str) -> str:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    return str(Path(root) / "System32" / name)


def sfc_command() -> list[str]:
    return [system32("sfc.exe"), "/scannow"]


def dism_checkhealth_command() -> list[str]:
    return [system32("Dism.exe"), "/Online", "/Cleanup-Image", "/CheckHealth"]


def chkdsk_readonly_command(drive: str) -> list[str]:
    letter = drive.strip().rstrip("\\").rstrip(":")
    return [system32("chkdsk.exe"), f"{letter}:"]


def elevation_message() -> str:
    if is_elevated():
        return "This session is running elevated."
    return (
        "This session is a standard user. SFC, DISM, and Check Disk need Administrator. "
        "Close TechBench and restart it with Run as administrator."
    )
