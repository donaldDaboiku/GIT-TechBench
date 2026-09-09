"""Headless UI smoke test — window builds and navigation works."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow
from app.ui.nav import NAV_ITEMS


class UiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_window_and_nav(self) -> None:
        window = MainWindow()
        self.assertGreaterEqual(len(window.pages), len(NAV_ITEMS))
        for item in NAV_ITEMS:
            self.assertIn(item.id, window.pages)
            window._on_navigate(item.id)
            self.assertIs(window.stack.currentWidget(), window.pages[item.id])
        window.close()
        if window._worker is not None:
            window._worker.wait(8000)


if __name__ == "__main__":
    unittest.main()
