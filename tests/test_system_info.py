"""System inventory collector checks."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.system_info import DataOrigin, FieldValue, collect_system_info, format_bytes, format_uptime


class FormatTests(unittest.TestCase):
    def test_format_bytes(self) -> None:
        self.assertEqual(format_bytes(1024), "1.0 KiB")
        self.assertIn("GiB", format_bytes(8 * 1024**3))

    def test_format_uptime(self) -> None:
        self.assertEqual(format_uptime(90), "1m")
        self.assertIn("h", format_uptime(3700))


class FieldValueTests(unittest.TestCase):
    def test_empty_is_unavailable(self) -> None:
        field = FieldValue.measured("  ")
        self.assertEqual(field.origin, DataOrigin.UNAVAILABLE)
        self.assertEqual(field.display(), "Unavailable")

    def test_oem_placeholder_is_measured_with_note(self) -> None:
        field = FieldValue.measured("To Be Filled By O.E.M.")
        self.assertEqual(field.origin, DataOrigin.MEASURED)
        self.assertIn("placeholder", field.note.lower())


class CollectorTests(unittest.TestCase):
    def test_collect_returns_identity(self) -> None:
        info = collect_system_info()
        self.assertTrue(info.computer_name.display())
        self.assertNotEqual(info.computer_name.display(), "")
        self.assertIsInstance(info.ram_origin, DataOrigin)
        if info.ram_total_bytes is not None:
            self.assertGreater(info.ram_total_bytes, 0)
            self.assertEqual(info.ram_origin, DataOrigin.MEASURED)
        self.assertIsInstance(info.volumes, list)
        self.assertIsInstance(info.gpus, list)


if __name__ == "__main__":
    unittest.main()
