"""Run automated Phase 2 checks with live progress."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from app.core.health_checker import overall_status
from app.models.diagnostic_result import DiagnosticResult
from app.ui.components.page_header import PageHeader
from app.ui.components.scroll_page import ScrollPage
from app.ui.components.status_badge import StatusBadge


class _ResultRow(QWidget):
    edited = Signal(object)

    def __init__(self, result: DiagnosticResult) -> None:
        super().__init__()
        self.result = result
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        top = QHBoxLayout()
        title = QLabel(result.module)
        title.setObjectName("fieldValue")
        self.badge = StatusBadge(result.status)
        top.addWidget(title)
        top.addStretch()
        top.addWidget(self.badge)
        layout.addLayout(top)
        self.message = QLabel(result.message)
        self.message.setWordWrap(True)
        self.message.setObjectName("muted")
        layout.addWidget(self.message)
        self.cause = QLineEdit(result.likely_cause)
        self.cause.setPlaceholderText("Likely cause (suggestion — editable)")
        self.action = QLineEdit(result.recommended_action)
        self.action.setPlaceholderText("Recommended action (editable)")
        self.cause.textChanged.connect(self._sync)
        self.action.textChanged.connect(self._sync)
        layout.addWidget(self.cause)
        layout.addWidget(self.action)

    def _sync(self) -> None:
        self.result.likely_cause = self.cause.text()
        self.result.recommended_action = self.action.text()
        self.result.technician_override = "edited"
        self.edited.emit(self.result)

    def apply(self, result: DiagnosticResult) -> None:
        self.result = result
        self.badge.set_status(result.status)
        self.message.setText(result.message)
        self.cause.blockSignals(True)
        self.action.blockSignals(True)
        self.cause.setText(result.likely_cause)
        self.action.setText(result.recommended_action)
        self.cause.blockSignals(False)
        self.action.blockSignals(False)


class FullDiagnosticPage(ScrollPage):
    result_ready = Signal(object)
    run_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: dict[str, _ResultRow] = {}
        self.body.addWidget(
            PageHeader(
                "Full Diagnostic",
                "Runs battery, storage, memory, CPU, GPU, and network tests. "
                "Keyboard, mouse, display, audio, and camera stay UNKNOWN until you run those pages. "
                "Windows Health commands are never auto-started.",
            )
        )
        self.overall = StatusBadge()
        top = QHBoxLayout()
        self.run_btn = QPushButton("Run automated checks")
        self.run_btn.clicked.connect(self.run_requested.emit)
        top.addWidget(self.run_btn)
        top.addStretch()
        top.addWidget(QLabel("Overall"))
        top.addWidget(self.overall)
        self.body.addLayout(top)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("muted")
        self.body.addWidget(self.progress)
        self.body.addWidget(self.progress_label)
        self.list_host = QVBoxLayout()
        self.body.addLayout(self.list_host)
        self.body.addStretch()

    def show_running(self) -> None:
        self.progress.setVisible(True)
        self.run_btn.setEnabled(False)
        self.progress_label.setText("Starting automated checks…")

    def show_progress(self, message: str) -> None:
        self.progress_label.setText(message)

    def show_idle(self, message: str = "") -> None:
        self.progress.setVisible(False)
        self.run_btn.setEnabled(True)
        if message:
            self.progress_label.setText(message)

    def upsert(self, result: DiagnosticResult) -> None:
        if result.module in self._rows:
            self._rows[result.module].apply(result)
        else:
            row = _ResultRow(result)
            row.edited.connect(self.result_ready.emit)
            self._rows[result.module] = row
            self.list_host.addWidget(row)
        self._refresh_overall()

    def results(self) -> list[DiagnosticResult]:
        return [row.result for row in self._rows.values()]

    def _refresh_overall(self) -> None:
        self.overall.set_status(overall_status(self.results()))
