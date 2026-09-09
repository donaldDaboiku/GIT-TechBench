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
