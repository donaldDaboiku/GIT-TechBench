"""SFC, DISM, Check Disk, Windows Update, Event Viewer."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
)

from app.core.recommendation_engine import RecommendationEngine
from app.core.windows_commands import is_elevated, open_event_viewer, open_windows_update
from app.modules.windows.windows_health import (
    WindowsHealth,
    chkdsk_readonly_command,
    dism_checkhealth_command,
    elevation_message,
    sfc_command,
)
from app.ui.components.page_header import PageHeader
from app.ui.components.result_banner import ResultBanner
from app.ui.components.scroll_page import ScrollPage
from app.ui.workers import CommandWorker

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None


class WindowsHealthPage(ScrollPage):
    result_ready = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.model = WindowsHealth()
        self.recommender = RecommendationEngine()
        self._worker: CommandWorker | None = None
        self.body.addWidget(
            PageHeader(
                "Windows Health",
                "Long-running commands run only after you confirm. Output is live. Nothing is auto-repaired beyond the tool you launch.",
            )
        )
        self.elev = QLabel(elevation_message())
        self.elev.setWordWrap(True)
        self.elev.setObjectName("muted")
        self.body.addWidget(self.elev)
        row = QHBoxLayout()
        sfc = QPushButton("Run sfc /scannow")
        sfc.clicked.connect(self._sfc)
        dism = QPushButton("DISM CheckHealth")
        dism.clicked.connect(self._dism)
        self.drive = QComboBox()
        self._fill_drives()
        chkdsk = QPushButton("Check Disk (read-only)")
        chkdsk.clicked.connect(self._chkdsk)
        update = QPushButton("Open Windows Update")
        update.setObjectName("secondaryButton")
        update.clicked.connect(open_windows_update)
        events = QPushButton("Open Event Viewer")
        events.setObjectName("secondaryButton")
        events.clicked.connect(open_event_viewer)
        for widget in (sfc, dism, self.drive, chkdsk, update, events):
            row.addWidget(widget)
        self.body.addLayout(row)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(240)
        self.output.setPlaceholderText("Command output appears here.")
        self.body.addWidget(self.output)
        self.banner = ResultBanner()
        self.body.addWidget(self.banner)
        self.body.addStretch()
        self._emit()

    def _fill_drives(self) -> None:
        self.drive.clear()
        if psutil is None:
            self.drive.addItem("C:")
            return
        for part in psutil.disk_partitions(all=False):
            if "cdrom" in part.opts.lower():
                continue
            letter = part.device.rstrip("\\")
            if letter:
                self.drive.addItem(letter)

    def _confirm(self, title: str, text: str) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(text)
        box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        return box.exec() == QMessageBox.StandardButton.Ok

    def _need_admin(self) -> bool:
        if is_elevated():
            return True
        QMessageBox.warning(self, "Administrator required", elevation_message())
        return False

    def _sfc(self) -> None:
        if not self._need_admin():
            return
        if not self._confirm(
            "System File Checker",
            "sfc /scannow scans protected system files and may repair them. "
            "It can take 15–30 minutes. Continue?",
        ):
            return
        self._run("sfc /scannow", sfc_command())

    def _dism(self) -> None:
        if not self._need_admin():
            return
        if not self._confirm(
            "DISM",
            "DISM /CheckHealth reads the component store. It does not repair. Continue?",
        ):
            return
        self._run("DISM CheckHealth", dism_checkhealth_command())

    def _chkdsk(self) -> None:
        if not self._need_admin():
            return
        drive = self.drive.currentText() or "C:"
        if not self._confirm(
            "Check Disk",
            f"Run a read-only chkdsk on {drive}? This does not fix the volume and does not format the drive. "
            "Windows may report that the volume cannot be locked.",
        ):
            return
        self._run(f"chkdsk {drive}", chkdsk_readonly_command(drive))

    def _run(self, label: str, args: list[str]) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self.output.clear()
        self.output.appendPlainText(f"> {' '.join(args)}\n")
        self.model.last_command = label
        self.model.ran_any = True
        self._worker = CommandWorker(args, self)
        self._worker.line.connect(self.output.appendPlainText)
        self._worker.finished_code.connect(self._done)
        self._worker.start()

    def _done(self, code: int) -> None:
        self.model.last_exit = int(code)
        self._emit()

    def _emit(self) -> None:
        result = self.recommender.annotate(self.model.to_result())
        self.banner.apply(result)
        self.result_ready.emit(result)
