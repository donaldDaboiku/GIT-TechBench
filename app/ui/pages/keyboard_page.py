"""Interactive virtual keyboard."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.recommendation_engine import RecommendationEngine
from app.modules.keyboard.keyboard_tester import KeyMark, KeyboardTester, standard_layout
from app.ui.components.page_header import PageHeader
from app.ui.components.result_banner import ResultBanner
from app.ui.components.scroll_page import ScrollPage


_MARK_COLORS = {
    KeyMark.NOT_TESTED: ("#1b2533", "#8b9bb0"),
    KeyMark.WORKING: ("#10291f", "#3ecf8e"),
    KeyMark.FAULTY: ("#2a1416", "#f07178"),
}


class _KeyCap(QFrame):
    picked = Signal(str)

    def __init__(self, key_id: str, label: str, units: float) -> None:
        super().__init__()
        self.key_id = key_id
        self.setObjectName("keyCap")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(40)
        self.setMinimumWidth(int(44 * units))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.label = QLabel(label)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("background: transparent;")
        layout.addWidget(self.label)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.picked.emit(self.key_id)
        super().mousePressEvent(event)

    def paint_mark(self, mark: KeyMark, selected: bool) -> None:
        bg, fg = _MARK_COLORS[mark]
        border = "#3d9cf0" if selected else fg
        self.setStyleSheet(
            f"QFrame#keyCap {{ background: {bg}; border: 2px solid {border}; border-radius: 6px; }}"
            f"QLabel {{ color: {fg}; font-size: 11px; font-weight: 700; background: transparent; }}"
        )


class KeyboardPage(ScrollPage):
    result_ready = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.tester = KeyboardTester()
        self.recommender = RecommendationEngine()
        self._selected = ""
        self.caps: dict[str, _KeyCap] = {}

        self.body.addWidget(
            PageHeader(
                "Keyboard Test",
                "Press keys on the physical keyboard. Untested keys are never failed automatically.",
            )
        )
        stats = QHBoxLayout()
        self.stats = QLabel("")
        self.stats.setObjectName("muted")
        reset = QPushButton("Reset")
        reset.setObjectName("secondaryButton")
        reset.clicked.connect(self._reset)
        stats.addWidget(self.stats, 1)
        stats.addWidget(reset)
        self.body.addLayout(stats)

        board = QFrame()
        board.setObjectName("card")
        board_layout = QVBoxLayout(board)
        board_layout.setContentsMargins(12, 12, 12, 12)
        board_layout.setSpacing(6)
        for row in standard_layout():
            line = QHBoxLayout()
            line.setSpacing(6)
            for item in row:
                cap = _KeyCap(item.key_id, item.label, item.units)
                cap.picked.connect(self._select)
                self.caps[item.key_id] = cap
                line.addWidget(cap)
            line.addStretch()
            board_layout.addLayout(line)
        self.body.addWidget(board)

        mark_row = QHBoxLayout()
        mark_row.addWidget(QLabel("Selected key:"))
        self.selected_label = QLabel("(click a key)")
        self.mark_box = QComboBox()
        self.mark_box.addItems([m.value for m in KeyMark])
        self.mark_box.currentTextChanged.connect(self._apply_mark)
        mark_row.addWidget(self.selected_label)
        mark_row.addWidget(self.mark_box)
        mark_row.addStretch()
        self.body.addLayout(mark_row)

        self.banner = ResultBanner()
        self.body.addWidget(self.banner)
        self.body.addStretch()
        self._refresh()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.grabKeyboard()
        self.setFocus()

    def hideEvent(self, event) -> None:  # noqa: N802
        self.releaseKeyboard()
        super().hideEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.isAutoRepeat():
            return
        self.tester.note_press(int(event.key()))
        self._refresh()
        self._emit()

    def _select(self, key_id: str) -> None:
        self._selected = key_id
        state = self.tester.states[key_id]
        self.selected_label.setText(state.definition.label)
        self.mark_box.blockSignals(True)
        self.mark_box.setCurrentText(state.mark.value)
        self.mark_box.blockSignals(False)
        self._refresh()

    def _apply_mark(self, text: str) -> None:
        if not self._selected:
            return
        self.tester.set_mark(self._selected, KeyMark(text))
        self._refresh()
        self._emit()

    def _reset(self) -> None:
        self.tester.reset()
        self._selected = ""
        self.selected_label.setText("(click a key)")
        self._refresh()
        self._emit()

    def _refresh(self) -> None:
        detected, working, faulty, total = self.tester.counts()
        self.stats.setText(
            f"Detected this session: {detected}/{total}  ·  Working: {working}  ·  "
            f"Faulty: {faulty}  ·  Not tested: {total - working - faulty}"
        )
        for key_id, cap in self.caps.items():
            cap.paint_mark(self.tester.states[key_id].mark, key_id == self._selected)

    def _emit(self) -> None:
        result = self.recommender.annotate(self.tester.to_result())
        self.banner.apply(result)
        self.result_ready.emit(result)
