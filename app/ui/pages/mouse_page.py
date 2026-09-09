"""Mouse buttons, double-click, scroll, and movement."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.core.recommendation_engine import RecommendationEngine
from app.modules.mouse.mouse_tester import CHECKS, MouseTester
from app.ui.components.page_header import PageHeader
from app.ui.components.result_banner import ResultBanner
from app.ui.components.scroll_page import ScrollPage


class _ClickPad(QFrame):
    detected = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("clickPad")
        self.setMinimumHeight(160)
        self.label = QLabel("Click here: left / right / middle\nDouble-click here too")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.addWidget(self.label)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        mapping = {
            Qt.MouseButton.LeftButton: "left",
            Qt.MouseButton.RightButton: "right",
            Qt.MouseButton.MiddleButton: "middle",
        }
        name = mapping.get(event.button())
        if name:
            self.detected.emit(name)
            self.label.setText(f"Detected: {name} click")

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.detected.emit("double")
            self.label.setText("Detected: double-click")

    def wheelEvent(self, event) -> None:  # noqa: N802
        self.detected.emit("scroll")
        delta = event.angleDelta().y()
        self.label.setText(f"Detected: scroll ({delta})")


class _MovePad(QFrame):
    moved = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("movePad")
        self.setMinimumHeight(180)
        self._points: list[QPoint] = []

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self._points.append(event.position().toPoint())
        if len(self._points) > 400:
            self._points = self._points[-400:]
        self.moved.emit()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(QPen(Qt.GlobalColor.cyan, 2))
        for i in range(1, len(self._points)):
            painter.drawLine(self._points[i - 1], self._points[i])
        painter.end()

    def reset_trace(self) -> None:
        self._points.clear()
        self.update()


class MousePage(ScrollPage):
    result_ready = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.tester = MouseTester()
        self.recommender = RecommendationEngine()
        self.body.addWidget(
            PageHeader("Mouse Test", "Exercise each control. Untested checks stay UNKNOWN, not FAIL.")
        )
        self.flags: dict[str, QLabel] = {}
        grid = QGridLayout()
        for i, name in enumerate(CHECKS):
            label = QLabel(f"{name}: not detected")
            label.setObjectName("muted")
            self.flags[name] = label
            grid.addWidget(label, i // 3, i % 3)
        self.body.addLayout(grid)

        pads = QHBoxLayout()
        self.click = _ClickPad()
        self.click.detected.connect(self._detected)
        self.move = _MovePad()
        self.move.setMouseTracking(True)
        self.move.moved.connect(lambda: self._detected("move"))
        move_col = QVBoxLayout()
        move_col.addWidget(QLabel("Move the pointer inside this pad"))
        move_col.addWidget(self.move)
        pads.addWidget(self.click, 1)
        pads.addLayout(move_col, 1)
        self.body.addLayout(pads)

        issue_row = QHBoxLayout()
        self.issue = QCheckBox("Technician: pointer hardware issue observed")
        self.issue.toggled.connect(self._issue)
        self.note = QLineEdit()
        self.note.setPlaceholderText("Optional note")
        self.note.textChanged.connect(self._issue)
        issue_row.addWidget(self.issue)
        issue_row.addWidget(self.note, 1)
        self.body.addLayout(issue_row)

        reset = QPushButton("Reset")
        reset.setObjectName("secondaryButton")
        reset.clicked.connect(self._reset)
        self.body.addWidget(reset, alignment=Qt.AlignmentFlag.AlignLeft)
        self.banner = ResultBanner()
        self.body.addWidget(self.banner)
        self.body.addStretch()
        self._emit()

    def _detected(self, name: str) -> None:
        self.tester.mark_detected(name)
        self.flags[name].setText(f"{name}: detected")
        self.flags[name].setStyleSheet("color: #3ecf8e;")
        self._emit()

    def _issue(self) -> None:
        self.tester.issue_observed = self.issue.isChecked()
        self.tester.issue_note = self.note.text().strip()
        self._emit()

    def _reset(self) -> None:
        self.tester.reset()
        self.move.reset_trace()
        self.issue.setChecked(False)
        self.note.clear()
        for name, label in self.flags.items():
            label.setText(f"{name}: not detected")
            label.setStyleSheet("")
        self.click.label.setText("Click here: left / right / middle\nDouble-click here too")
        self._emit()

    def _emit(self) -> None:
        result = self.recommender.annotate(self.tester.to_result())
        self.banner.apply(result)
        self.result_ready.emit(result)
