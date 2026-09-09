"""Fullscreen color plates for visual panel inspection."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter
from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton, QWidget

from app.core.recommendation_engine import RecommendationEngine
from app.modules.display.display_tester import GUIDANCE, PLATES, DisplayTester
from app.ui.components.page_header import PageHeader
from app.ui.components.result_banner import ResultBanner
from app.ui.components.scroll_page import ScrollPage


class ColorOverlay(QWidget):
    finished = Signal()
    plate_shown = Signal(str)

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self._index = 0
        self.setCursor(Qt.CursorShape.BlankCursor)

    def start(self) -> None:
        self._index = 0
        self.showFullScreen()
        self._broadcast()

    def _broadcast(self) -> None:
        name, _hex = PLATES[self._index]
        self.plate_shown.emit(name)
        self.update()

    def _next(self) -> None:
        if self._index + 1 >= len(PLATES):
            self.close()
            self.finished.emit()
            return
        self._index += 1
        self._broadcast()

    def paintEvent(self, event) -> None:  # noqa: N802
        name, hex_color = PLATES[self._index]
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(hex_color))
        fg = QColor("#ffffff") if name == "black" else QColor("#000000")
        painter.setPen(fg)
        painter.drawText(
            24,
            36,
            f"{name.upper()}  ·  Space/click: next  ·  Esc: exit  ·  look for dead, stuck, and bright pixels",
        )
        painter.end()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            self.finished.emit()
        elif event.key() in {Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            self._next()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._next()


class DisplayPage(ScrollPage):
    result_ready = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.tester = DisplayTester()
        self.recommender = RecommendationEngine()
        self.overlay = ColorOverlay()
        self.overlay.plate_shown.connect(self.tester.note_plate)
        self.overlay.finished.connect(self._emit)
        self.body.addWidget(
            PageHeader(
                "Display Test",
                "Fullscreen black / white / red / green / blue plates. Esc exits.",
            )
        )
        for line in GUIDANCE:
            label = QLabel(line)
            label.setObjectName("muted")
            label.setWordWrap(True)
            self.body.addWidget(label)
        start = QPushButton("Start fullscreen plates")
        start.clicked.connect(self.overlay.start)
        self.body.addWidget(start, alignment=Qt.AlignmentFlag.AlignLeft)
        self.dead = QCheckBox("Technician confirms dead or stuck pixels")
        self.backlight = QCheckBox("Technician confirms backlight / bleed issue")
        self.color = QCheckBox("Technician confirms color problem")
        for box in (self.dead, self.backlight, self.color):
            box.toggled.connect(self._findings)
            self.body.addWidget(box)
        reset = QPushButton("Reset")
        reset.setObjectName("secondaryButton")
        reset.clicked.connect(self._reset)
        self.body.addWidget(reset, alignment=Qt.AlignmentFlag.AlignLeft)
        self.banner = ResultBanner()
        self.body.addWidget(self.banner)
        self.body.addStretch()
        self._emit()

    def _findings(self) -> None:
        self.tester.dead_or_stuck_pixel = self.dead.isChecked()
        self.tester.backlight_issue = self.backlight.isChecked()
        self.tester.color_issue = self.color.isChecked()
        if any((self.dead.isChecked(), self.backlight.isChecked(), self.color.isChecked())):
            self.tester.not_tested = False
        self._emit()

    def _reset(self) -> None:
        self.tester.reset()
        for box in (self.dead, self.backlight, self.color):
            box.setChecked(False)
        self._emit()

    def _emit(self) -> None:
        result = self.recommender.annotate(self.tester.to_result())
        self.banner.apply(result)
        self.result_ready.emit(result)
