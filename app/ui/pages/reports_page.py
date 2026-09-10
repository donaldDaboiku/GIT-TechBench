"""Session history, PDF/JSON export, and technician notes."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.models.diagnostic_result import DiagnosticResult
from app.ui.components.page_header import PageHeader
from app.ui.components.scroll_page import ScrollPage


class ReportsPage(ScrollPage):
    save_requested = Signal()
    reopen_requested = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[dict] = []
        self.body.addWidget(
            PageHeader(
                "Reports",
                "Save the current diagnostic session, search history by computer name or serial, "
                "reopen a past session, and export PDF or JSON. Recommendation text stays editable.",
            )
        )
        row = QHBoxLayout()
        save = QPushButton("Save current session")
        save.clicked.connect(lambda: self.save_requested.emit())
        self.export_pdf_btn = QPushButton("Export PDF")
        self.export_pdf_btn.setObjectName("secondaryButton")
        self.export_json_btn = QPushButton("Export JSON")
        self.export_json_btn.setObjectName("secondaryButton")
        reopen = QPushButton("Reopen selected")
        reopen.setObjectName("secondaryButton")
        reopen.clicked.connect(self._reopen)
        row.addWidget(save)
        row.addWidget(self.export_pdf_btn)
        row.addWidget(self.export_json_btn)
        row.addWidget(reopen)
        row.addStretch()
        self.body.addLayout(row)
        self.status = QLabel("No session saved this run.")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        self.body.addWidget(self.status)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by computer name or serial…")
        self.search.textChanged.connect(lambda: self.set_history(self._rows))
        self.body.addWidget(self.search)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(("ID", "Date", "Computer", "Serial", "Technician", "Overall"))
        self.table.setMinimumHeight(200)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.body.addWidget(self.table)
        notes_label = QLabel("TECHNICIAN NOTES")
        notes_label.setObjectName("sectionTitle")
        self.body.addWidget(notes_label)
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Session notes (editable before save/export)")
        self.notes.setMaximumHeight(90)
        self.body.addWidget(self.notes)
        self.repair = QLineEdit()
        self.repair.setPlaceholderText("Repair needed")
        self.parts = QLineEdit()
        self.parts.setPlaceholderText("Parts required")
        self.further = QLineEdit()
        self.further.setPlaceholderText("Further testing")
        self.body.addWidget(self.repair)
        self.body.addWidget(self.parts)
        self.body.addWidget(self.further)
        self.body.addStretch()
        self._selected_id: int | None = None

    def notes_payload(self) -> dict[str, str]:
        return {
            "notes": self.notes.toPlainText().strip(),
            "repair_needed": self.repair.text().strip(),
            "parts_required": self.parts.text().strip(),
            "further_testing": self.further.text().strip(),
        }

    def apply_session_fields(self, session: dict) -> None:
        self.notes.setPlainText(str(session.get("notes") or ""))
        self.repair.setText(str(session.get("repair_needed") or ""))
        self.parts.setText(str(session.get("parts_required") or ""))
        self.further.setText(str(session.get("further_testing") or ""))

    def set_history(self, rows: list[dict], message: str = "") -> None:
        self._rows = rows
        needle = self.search.text().strip().lower()
        self.table.setRowCount(0)
        for item in rows:
            hay = f"{item.get('computer_name', '')} {item.get('serial_number', '')}".lower()
            if needle and needle not in hay:
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = (
                str(item.get("id") or ""),
                str(item.get("created_at") or ""),
                str(item.get("computer_name") or ""),
                str(item.get("serial_number") or ""),
                str(item.get("technician_name") or ""),
                str(item.get("overall_status") or ""),
            )
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()
        if message:
            self.status.setText(message)

    def chosen_path(self, suffix: str, stem: str) -> Path | None:
        if suffix == ".pdf":
            filtr = "PDF (*.pdf)"
        else:
            filtr = "JSON (*.json)"
        path, _ok = QFileDialog.getSaveFileName(self, "Export report", stem + suffix, filtr)
        return Path(path) if path else None

    def confirm_reopen(self) -> bool:
        answer = QMessageBox.question(
            self,
            "Reopen session",
            "Load this saved session into Full Diagnostic? Current unsaved results will be replaced.",
        )
        return answer == QMessageBox.StandardButton.Yes

    def _on_select(self) -> None:
        items = self.table.selectedItems()
        if not items:
            self._selected_id = None
            return
        try:
            self._selected_id = int(self.table.item(items[0].row(), 0).text())
        except (TypeError, ValueError):
            self._selected_id = None

    def _reopen(self) -> None:
        if self._selected_id is None:
            self.status.setText("Select a saved session first.")
            return
        if not self.confirm_reopen():
            return
        self.reopen_requested.emit(self._selected_id)

    def tests_from_session(self, session: dict) -> list[DiagnosticResult]:
        tests = session.get("tests") or []
        results: list[DiagnosticResult] = []
        for item in tests:
            if isinstance(item, dict):
                results.append(DiagnosticResult.from_dict(item))
        return results
