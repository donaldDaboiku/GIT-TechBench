"""Phase 4 IT-support helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.diagnostics_engine import AUTOMATED_MODULES, INTERACTIVE_MODULES
from app.core.recommendation_engine import RecommendationEngine
from app.models.diagnostic_result import Confidence, DiagnosticResult, Status
from app.modules.drivers.driver_health import classify_error, overall_from_counts
from app.modules.motherboard.motherboard_info import bios_update_availability
from app.modules.security.security_health import overall_from_flags
from app.modules.software.software_inventory import parse_install_date, startup_enabled
from app.modules.usb.usb_port_tester import UsbDevice, UsbReport, diff_devices, overall_from_usb


class DriverRuleTests(unittest.TestCase):
    def test_code_28_is_fail(self) -> None:
        self.assertEqual(classify_error(28), Status.FAIL)

    def test_disabled_is_warning(self) -> None:
        self.assertEqual(classify_error(22), Status.WARNING)

    def test_ok_is_pass(self) -> None:
        self.assertEqual(classify_error(0), Status.PASS)

    def test_overall_fail_beats_disabled(self) -> None:
        status, message = overall_from_counts(fail=1, warn=2, total=10)
        self.assertEqual(status, Status.FAIL)
        self.assertIn("error codes", message)

    def test_empty_is_unknown(self) -> None:
        status, _ = overall_from_counts(fail=0, warn=0, total=0)
        self.assertEqual(status, Status.UNKNOWN)


class SecurityRuleTests(unittest.TestCase):
    def test_defender_off_no_av_is_fail(self) -> None:
        status, _ = overall_from_flags(
            av_ok=False,
            av_known=True,
            realtime_ok=False,
            third_party=False,
            firewall_off=False,
            firewall_known=True,
            updates_pending=False,
            updates_known=True,
            os_unlocked=False,
        )
        self.assertEqual(status, Status.FAIL)

    def test_incomplete_is_unknown(self) -> None:
        status, _ = overall_from_flags(
            av_ok=False,
            av_known=False,
            realtime_ok=False,
            third_party=False,
            firewall_off=False,
            firewall_known=False,
            updates_pending=False,
            updates_known=False,
            os_unlocked=False,
        )
        self.assertEqual(status, Status.UNKNOWN)


class UsbDiffTests(unittest.TestCase):
    def test_added_and_removed(self) -> None:
        before = UsbReport(
            controllers=[],
            hubs=[],
            devices=[
                UsbDevice("Old", "USB\\VID_1", "Device", 0, "OK", Status.PASS),
            ],
            status=Status.PASS,
            message="",
        )
        after = UsbReport(
            controllers=[],
            hubs=[],
            devices=[
                UsbDevice("New", "USB\\VID_2", "Device", 0, "OK", Status.PASS),
            ],
            status=Status.PASS,
            message="",
        )
        delta = diff_devices(before, after)
        self.assertEqual([item.name for item in delta.added], ["New"])
        self.assertEqual([item.name for item in delta.removed], ["Old"])

    def test_controller_error_is_fail(self) -> None:
        status, _ = overall_from_usb(controllers=1, error_fail=1, error_warn=0)
        self.assertEqual(status, Status.FAIL)

    def test_no_controllers_unknown(self) -> None:
        status, _ = overall_from_usb(controllers=0, error_fail=0, error_warn=0)
        self.assertEqual(status, Status.UNKNOWN)


class SoftwareParseTests(unittest.TestCase):
    def test_install_date(self) -> None:
        self.assertEqual(parse_install_date("20240910"), "2024-09-10")
        self.assertEqual(parse_install_date(""), "Unavailable")

    def test_startup_approved_blob(self) -> None:
        self.assertEqual(startup_enabled(b"\x02\x00\x00\x00"), "Enabled")
        self.assertEqual(startup_enabled(b"\x03\x00\x00\x00"), "Disabled")
        self.assertEqual(startup_enabled(None), "Enabled")


class MotherboardTests(unittest.TestCase):
    def test_tpm_acpi_ids(self) -> None:
        from app.modules.motherboard.motherboard_info import tpm_from_pnp

        self.assertEqual(tpm_from_pnp(r"ACPI\MSFT0101\1", "Trusted Platform Module 2.0")[1], "2.0 (ACPI MSFT0101)")
        self.assertIsNone(tpm_from_pnp(r"USB\VID_1234", "USB Root Hub"))

    def test_missing_vendor_tool_is_not_available(self) -> None:
        text = bios_update_availability()
        self.assertTrue(text.startswith("Not available") or "Vendor tool present" in text)


class EngineCatalogTests(unittest.TestCase):
    def test_phase4_modules_listed(self) -> None:
        for name in ("Motherboard", "Drivers", "Security", "Software", "USB"):
            self.assertIn(name, AUTOMATED_MODULES)
        self.assertNotIn("USB", INTERACTIVE_MODULES)


class RecommendationTests(unittest.TestCase):
    def test_driver_rule(self) -> None:
        engine = RecommendationEngine()
        result = DiagnosticResult(
            module="Drivers",
            status=Status.FAIL,
            message="1 device has an error code.",
            details={"has_error_code": "true"},
        )
        engine.annotate(result)
        self.assertEqual(result.confidence, Confidence.MEDIUM)
        self.assertIn("vendor", result.recommended_action.lower())

    def test_security_rule(self) -> None:
        engine = RecommendationEngine()
        result = DiagnosticResult(
            module="Security",
            status=Status.FAIL,
            message="Defender off",
            details={"defender_off_no_av": "true"},
        )
        engine.annotate(result)
        self.assertEqual(result.confidence, Confidence.HIGH)


if __name__ == "__main__":
    unittest.main()
