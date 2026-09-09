"""Keyboard session model.

Never auto-fails an untested key. Detection marks Working; only the
technician can mark Faulty.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import Qt

from app.models.diagnostic_result import DiagnosticResult, Status

MODULE = "Keyboard"


class KeyMark(str, Enum):
    NOT_TESTED = "Not Tested"
    WORKING = "Working"
    FAULTY = "Faulty"


@dataclass
class KeyDef:
    key_id: str
    label: str
    qt_key: int
    units: float = 1.0


@dataclass
class KeyState:
    definition: KeyDef
    mark: KeyMark = KeyMark.NOT_TESTED
    presses: int = 0


def standard_layout() -> list[list[KeyDef]]:
    """Laptop-style set covering letters, digits, function, arrows, and modifiers."""
    fkeys = [KeyDef("esc", "Esc", Qt.Key.Key_Escape, 1.2)]
    fkeys += [KeyDef(f"f{i}", f"F{i}", getattr(Qt.Key, f"Key_F{i}"), 1.0) for i in range(1, 13)]
    row1 = [
        KeyDef("grave", "`", Qt.Key.Key_QuoteLeft),
        *[KeyDef(str(i), str(i), getattr(Qt.Key, f"Key_{i}")) for i in range(1, 10)],
        KeyDef("0", "0", Qt.Key.Key_0),
        KeyDef("minus", "-", Qt.Key.Key_Minus),
        KeyDef("equal", "=", Qt.Key.Key_Equal),
        KeyDef("backspace", "Backspace", Qt.Key.Key_Backspace, 2.0),
    ]
    row2 = [
        KeyDef("tab", "Tab", Qt.Key.Key_Tab, 1.5),
        *[KeyDef(ch.lower(), ch, getattr(Qt.Key, f"Key_{ch}")) for ch in "QWERTYUIOP"],
        KeyDef("lbracket", "[", Qt.Key.Key_BracketLeft),
        KeyDef("rbracket", "]", Qt.Key.Key_BracketRight),
        KeyDef("backslash", "\\", Qt.Key.Key_Backslash, 1.5),
    ]
    row3 = [
        KeyDef("caps", "Caps", Qt.Key.Key_CapsLock, 1.8),
        *[KeyDef(ch.lower(), ch, getattr(Qt.Key, f"Key_{ch}")) for ch in "ASDFGHJKL"],
        KeyDef("semicolon", ";", Qt.Key.Key_Semicolon),
        KeyDef("quote", "'", Qt.Key.Key_Apostrophe),
        KeyDef("enter", "Enter", Qt.Key.Key_Return, 2.2),
    ]
    row4 = [
        KeyDef("shift", "Shift", Qt.Key.Key_Shift, 2.4),
        *[KeyDef(ch.lower(), ch, getattr(Qt.Key, f"Key_{ch}")) for ch in "ZXCVBNM"],
        KeyDef("comma", ",", Qt.Key.Key_Comma),
        KeyDef("period", ".", Qt.Key.Key_Period),
        KeyDef("slash", "/", Qt.Key.Key_Slash),
        KeyDef("shift_r", "Shift", Qt.Key.Key_Shift, 2.4),
    ]
    row5 = [
        KeyDef("ctrl", "Ctrl", Qt.Key.Key_Control, 1.4),
        KeyDef("win", "Win", Qt.Key.Key_Meta, 1.2),
        KeyDef("alt", "Alt", Qt.Key.Key_Alt, 1.2),
        KeyDef("space", "Space", Qt.Key.Key_Space, 6.0),
        KeyDef("alt_r", "Alt", Qt.Key.Key_Alt, 1.2),
        KeyDef("ctrl_r", "Ctrl", Qt.Key.Key_Control, 1.4),
    ]
    nav = [
        KeyDef("insert", "Ins", Qt.Key.Key_Insert),
        KeyDef("home", "Home", Qt.Key.Key_Home),
        KeyDef("pageup", "PgUp", Qt.Key.Key_PageUp),
        KeyDef("delete", "Del", Qt.Key.Key_Delete),
        KeyDef("end", "End", Qt.Key.Key_End),
        KeyDef("pagedown", "PgDn", Qt.Key.Key_PageDown),
        KeyDef("left", "←", Qt.Key.Key_Left),
        KeyDef("up", "↑", Qt.Key.Key_Up),
        KeyDef("down", "↓", Qt.Key.Key_Down),
        KeyDef("right", "→", Qt.Key.Key_Right),
    ]
    return [fkeys, row1, row2, row3, row4, row5, nav]


class KeyboardTester:
    phase = 2
    title = "Keyboard Test"

    def __init__(self) -> None:
        self.states: dict[str, KeyState] = {}
        for row in standard_layout():
            for item in row:
                self.states[item.key_id] = KeyState(item)

    def reset(self) -> None:
        for state in self.states.values():
            state.mark = KeyMark.NOT_TESTED
            state.presses = 0

    def note_press(self, qt_key: int) -> list[str]:
        """Record a hardware key. Never marks Faulty. Returns matching key ids."""
        matched: list[str] = []
        enter_keys = {int(Qt.Key.Key_Return), int(Qt.Key.Key_Enter)}
        win_keys = {int(Qt.Key.Key_Meta)}
        for name in ("Key_Super_L", "Key_Super_R"):
            if hasattr(Qt.Key, name):
                win_keys.add(int(getattr(Qt.Key, name)))
        for key_id, state in self.states.items():
            same = int(state.definition.qt_key) == int(qt_key)
            if state.definition.key_id == "enter" and int(qt_key) in enter_keys:
                same = True
            if state.definition.key_id == "win" and int(qt_key) in win_keys:
                same = True
            if not same:
                continue
            state.presses += 1
            if state.mark != KeyMark.FAULTY:
                state.mark = KeyMark.WORKING
            matched.append(key_id)
        return matched

    def set_mark(self, key_id: str, mark: KeyMark) -> None:
        if key_id in self.states:
            self.states[key_id].mark = mark

    def counts(self) -> tuple[int, int, int, int]:
        total = len(self.states)
        working = sum(1 for s in self.states.values() if s.mark == KeyMark.WORKING)
        faulty = sum(1 for s in self.states.values() if s.mark == KeyMark.FAULTY)
        detected = sum(1 for s in self.states.values() if s.presses > 0)
        return detected, working, faulty, total

    def to_result(self) -> DiagnosticResult:
        detected, working, faulty, total = self.counts()
        untested = total - working - faulty
        if faulty:
            status = Status.FAIL
            message = f"{faulty} key(s) marked Faulty. {working} working, {untested} not tested."
        elif working:
            status = Status.PASS
            message = (
                f"{working} key(s) confirmed working this session. "
                f"{untested} not tested (not a fail)."
            )
        else:
            status = Status.UNKNOWN
            message = "No keys tested this session."
        return DiagnosticResult(
            module=MODULE,
            status=status,
            message=message,
            details={
                "detected": str(detected),
                "working": str(working),
                "faulty": str(faulty),
                "untested": str(untested),
            },
        )
