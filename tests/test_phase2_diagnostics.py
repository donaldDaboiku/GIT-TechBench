"""Phase 2 diagnostic rules."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.recommendation_engine import RecommendationEngine
from app.models.diagnostic_result import Confidence, DiagnosticResult, Status
from app.modules.battery.battery_checker import health_band, health_percent
from app.modules.display.display_tester import DisplayTester
from app.modules.keyboard.keyboard_tester import KeyMark, KeyboardTester
from app.modules.mouse.mouse_tester import MouseTester
from app.modules.storage.disk_checker import classify_drive_kind, overall_from_signals
from PySide6.QtCore import Qt


class BatteryBandTests(unittest.TestCase):
    def test_formula_and_bands(self) -> None:
        self.assertAlmostEqual(health_percent(6000, 10000) or 0, 60.0)
        self.assertIsNone(health_percent(10, 0))
        self.assertEqual(health_band(95)[0], "Excellent")
        self.assertEqual(health_band(95)[1], Status.PASS)
        self.assertEqual(health_band(80)[1], Status.PASS)
        self.assertEqual(health_band(70)[1], Status.WARNING)
        self.assertEqual(health_band(50)[1], Status.FAIL)


class StorageRulesTests(unittest.TestCase):
    def test_missing_smart_is_not_pass(self) -> None:
        status, message = overall_from_signals(
            smart_available=False,
            predict_failure=False,
            realloc=False,
            space_warning=False,
            windows_unhealthy=False,
        )
        self.assertEqual(status, Status.UNKNOWN)
        self.assertIn("SMART information unavailable", message)

    def test_predict_failure_is_fail(self) -> None:
        status, _ = overall_from_signals(
            smart_available=True,
            predict_failure=True,
            realloc=False,
            space_warning=False,
            windows_unhealthy=False,
        )
        self.assertEqual(status, Status.FAIL)

    def test_smart_ok_is_pass(self) -> None:
        status, _ = overall_from_signals(
            smart_available=True,
            predict_failure=False,
            realloc=False,
            space_warning=False,
            windows_unhealthy=False,
        )
        self.assertEqual(status, Status.PASS)


class DriveKindTests(unittest.TestCase):
    def test_physicaldisk_media_type(self) -> None:
        self.assertEqual(classify_drive_kind("SSD"), "SSD")
        self.assertEqual(classify_drive_kind("HDD"), "HDD")
        self.assertEqual(classify_drive_kind("4", "SATA"), "SSD")
        self.assertEqual(classify_drive_kind("Unspecified", "NVMe"), "SSD")

    def test_wmi_fixed_disk_is_not_hdd(self) -> None:
        self.assertEqual(classify_drive_kind("Fixed hard disk media", "IDE"), "Unavailable")


class KeyboardSessionTests(unittest.TestCase):
    def test_untested_keys_are_not_failed(self) -> None:
        tester = KeyboardTester()
        tester.note_press(int(Qt.Key.Key_A))
        result = tester.to_result()
        self.assertEqual(result.status, Status.PASS)
        self.assertIn("not tested (not a fail)", result.message)
        self.assertEqual(tester.states["b"].mark, KeyMark.NOT_TESTED)

    def test_faulty_is_only_manual(self) -> None:
        tester = KeyboardTester()
        tester.note_press(int(Qt.Key.Key_A))
        self.assertEqual(tester.states["a"].mark, KeyMark.WORKING)
        tester.set_mark("a", KeyMark.FAULTY)
        self.assertEqual(tester.to_result().status, Status.FAIL)


class MouseDisplayTests(unittest.TestCase):
    def test_mouse_partial_is_unknown(self) -> None:
        mouse = MouseTester()
        mouse.mark_detected("left")
        self.assertEqual(mouse.to_result().status, Status.UNKNOWN)

    def test_display_defect(self) -> None:
        display = DisplayTester()
        display.note_plate("black")
        display.dead_or_stuck_pixel = True
        result = display.to_result()
        self.assertEqual(result.status, Status.FAIL)
        self.assertEqual(result.details["dead_or_stuck_pixel"], "true")


class RecommendationTests(unittest.TestCase):
    def test_battery_poor_rule(self) -> None:
        engine = RecommendationEngine()
        result = DiagnosticResult(
            module="Battery",
            status=Status.FAIL,
            message="Battery health is 58% (Poor).",
            details={"health_band": "Poor"},
        )
        engine.annotate(result)
        self.assertEqual(result.likely_cause, "Battery cell degradation")
        self.assertEqual(result.confidence, Confidence.HIGH)

    def test_pass_is_not_annotated(self) -> None:
        engine = RecommendationEngine()
        result = DiagnosticResult(module="Battery", status=Status.PASS, message="ok")
        engine.annotate(result)
        self.assertEqual(result.likely_cause, "")


if __name__ == "__main__":
    unittest.main()
