"""Portable USB path helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import config_dir, is_frozen, project_root, resource_root, settings_path


class PortablePathTests(unittest.TestCase):
    def test_dev_root_is_checkout(self) -> None:
        self.assertFalse(is_frozen())
        root = project_root()
        self.assertTrue((root / "main.py").exists())
        self.assertTrue((root / "app").is_dir())
        self.assertEqual(resource_root(), root)
        self.assertTrue((config_dir() / "app_config.json").exists())
        self.assertTrue((config_dir() / "recommendation_rules.json").exists())
        self.assertTrue((resource_root() / "assets" / "icons" / "techbench.ico").is_file())

    def test_frozen_uses_exe_dir(self) -> None:
        original_exe = sys.executable
        sys.frozen = True  # type: ignore[attr-defined]
        sys.executable = r"E:\USB\GIT-TechBench-Portable\TechBench.exe"
        try:
            self.assertTrue(is_frozen())
            self.assertEqual(project_root(), Path(r"E:\USB\GIT-TechBench-Portable"))
        finally:
            sys.executable = original_exe
            if hasattr(sys, "frozen"):
                delattr(sys, "frozen")

    def test_settings_ini_lives_in_app_folder(self) -> None:
        path = settings_path()
        self.assertEqual(path.name, "techbench.ini")
        self.assertEqual(path.parent, project_root() / "config")
