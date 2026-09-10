"""Background workers so diagnostics never block the UI."""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QThread, Signal

from app.core.diagnostics_engine import DiagnosticsEngine
from app.core.system_info import collect_system_info

logger = logging.getLogger("techbench.workers")


class SystemInfoWorker(QThread):
    progress = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def run(self) -> None:
        try:
            snapshot = collect_system_info(progress=self.progress.emit)
            self.succeeded.emit(snapshot)
        except Exception as exc:
            logger.exception("System inventory scan failed")
            self.failed.emit(str(exc))


class CallableWorker(QThread):
    """Run a zero-arg callable that returns a value."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], object], parent=None) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            self.succeeded.emit(self._fn())
        except Exception as exc:
            logger.exception("Worker failed")
            self.failed.emit(str(exc))


class CommandWorker(QThread):
    """Stream an approved Windows command without blocking the UI."""

    line = Signal(str)
    finished_code = Signal(int)

    def __init__(self, args: list[str], parent=None) -> None:
        super().__init__(parent)
        self.args = args

    def run(self) -> None:
        import os
        import subprocess

        from app.core.windows_commands import CREATE_NO_WINDOW

        try:
            proc = subprocess.Popen(
                self.args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="oem",
                errors="replace",
                creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except OSError as exc:
            self.line.emit(str(exc))
            self.finished_code.emit(1)
            return
        assert proc.stdout is not None
        for raw in proc.stdout:
            self.line.emit(raw.rstrip("\r\n"))
        self.finished_code.emit(int(proc.wait()))


class UsbWatchWorker(QThread):
    """Poll USB inventory until the technician stops the watch."""

    snapshot = Signal(object)
    failed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._running = True

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        from app.modules.usb.usb_port_tester import UsbPortTester

        tester = UsbPortTester()
        while self._running:
            try:
                report, _result = tester.snapshot()
            except Exception as exc:
                logger.exception("USB watch snapshot failed")
                self.failed.emit(str(exc))
                return
            self.snapshot.emit(report)
            self.msleep(1500)


class MicWorker(QThread):
    """Sample microphone RMS off the UI thread."""

    level = Signal(float)
    failed = Signal(str)

    def __init__(self, device_index: int = 0, parent=None) -> None:
        super().__init__(parent)
        self.device_index = device_index
        self._running = True

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        from app.modules.audio.audio_tester import sample_mic_rms

        while self._running:
            value = sample_mic_rms(self.device_index)
            if value is None:
                self.failed.emit("Could not open this recording device.")
                return
            self.level.emit(value)


class FullDiagnosticWorker(QThread):
    progress = Signal(str)
    module_done = Signal(object)
    succeeded = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        internet_url: str | None = None,
        dns_hostname: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.internet_url = internet_url
        self.dns_hostname = dns_hostname

    def run(self) -> None:
        try:
            engine = DiagnosticsEngine()
            results = engine.run_automated(
                progress=self.progress.emit,
                on_result=self.module_done.emit,
                internet_url=self.internet_url,
                dns_hostname=self.dns_hostname,
            )
            self.succeeded.emit(results)
        except Exception as exc:
            logger.exception("Full diagnostic failed")
            self.failed.emit(str(exc))
