"""NVMe / ATA SMART parsers — no live disk required."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.recommendation_engine import RecommendationEngine
from app.models.diagnostic_result import DiagnosticResult, Status
from app.modules.storage.disk_checker import DriveReport, _health_drives, overall_from_signals
from app.modules.storage.smart_ioctl import (
    parse_ata_smart,
    parse_nvme_health,
    parse_windows_endurance,
    parse_windows_temperature,
)


def _nvme_log(*, kelvin: int = 310, warning: int = 0, spare: int = 100, spare_th: int = 10, used: int = 4, hours: int = 1500) -> bytes:
    data = bytearray(512)
    data[0] = warning
    data[1:3] = kelvin.to_bytes(2, "little")
    data[3] = spare
    data[4] = spare_th
    data[5] = used
    data[128:144] = hours.to_bytes(16, "little")
    return bytes(data)


def _ata_blob(*, temp: int = 41, realloc: int = 0, hours: int = 900, life: int = 97) -> bytes:
    data = bytearray(512)

    def put(slot: int, attr_id: int, current: int, raw0: int, raw_le: int = 0) -> None:
        base = 2 + slot * 12
        data[base] = attr_id
        data[base + 3] = current
        if raw_le:
            data[base + 5 : base + 11] = raw_le.to_bytes(6, "little")
        else:
            data[base + 5] = raw0

    put(0, 194, 50, temp)
    put(1, 5, 100, 0, realloc)
    put(2, 9, 99, 0, hours)
    put(3, 231, life, 0)
    return bytes(data)


class NvmeParseTests(unittest.TestCase):
    def test_health_log_temperature_and_hours(self) -> None:
        reading = parse_nvme_health(_nvme_log())
        self.assertTrue(reading.available)
        self.assertFalse(reading.predict_failure)
        self.assertEqual(reading.temperature_c, 37)
        self.assertEqual(reading.power_on_hours, "1500")
        self.assertIn("4% used", reading.wear)
        self.assertIn("100%", reading.spare)

    def test_critical_warning_is_failure(self) -> None:
        reading = parse_nvme_health(_nvme_log(warning=0x01))
        self.assertTrue(reading.predict_failure)
        self.assertIn("critical warning", reading.note)

    def test_short_buffer_is_unavailable(self) -> None:
        self.assertFalse(parse_nvme_health(b"\x00" * 10).available)


class AtaParseTests(unittest.TestCase):
    def test_attributes(self) -> None:
        reading = parse_ata_smart(_ata_blob(), predict_failure=False)
        self.assertTrue(reading.available)
        self.assertEqual(reading.temperature_c, 41)
        self.assertFalse(reading.realloc_or_pending)
        self.assertEqual(reading.power_on_hours, "900")
        self.assertIn("97% remaining", reading.wear)

    def test_realloc_raw(self) -> None:
        reading = parse_ata_smart(_ata_blob(realloc=3), predict_failure=False)
        self.assertTrue(reading.realloc_or_pending)


class WindowsDescriptorTests(unittest.TestCase):
    def test_temperature_descriptor(self) -> None:
        blob = bytearray(64)
        blob[12:14] = (1).to_bytes(2, "little")
        blob[26:28] = (44).to_bytes(2, "little", signed=True)
        self.assertEqual(parse_windows_temperature(bytes(blob)), 44)

    def test_endurance_descriptor(self) -> None:
        blob = bytearray(64)
        blob[32:36] = (12).to_bytes(4, "little")
        self.assertEqual(parse_windows_endurance(bytes(blob)), 12)


class StorageOverallTests(unittest.TestCase):
    def test_needs_admin_message(self) -> None:
        status, message = overall_from_signals(
            smart_available=False,
            predict_failure=False,
            realloc=False,
            space_warning=False,
            windows_unhealthy=False,
            needs_admin=True,
        )
        self.assertEqual(status, Status.UNKNOWN)
        self.assertIn("administrator", message)

    def test_usb_does_not_hide_internal(self) -> None:
        usb = DriveReport(
            model="SanDisk",
            serial="x",
            kind="Unavailable",
            bus="USB",
            media="Removable",
            interface="USB",
            size_bytes=1,
            windows_health="Healthy",
            smart_available=False,
            smart_predict_failure=None,
            smart_note="unavailable",
            realloc_or_pending=False,
            temperature_c="Unavailable",
        )
        ssd = DriveReport(
            model="TEAM",
            serial="y",
            kind="SSD",
            bus="SATA",
            media="SSD",
            interface="IDE",
            size_bytes=1,
            windows_health="Healthy",
            smart_available=True,
            smart_predict_failure=False,
            smart_note="ok",
            realloc_or_pending=False,
            temperature_c="37 C",
        )
        targets = _health_drives([usb, ssd])
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].model, "TEAM")


class RecommendationAdminTests(unittest.TestCase):
    def test_admin_rule_beats_generic_unavailable(self) -> None:
        engine = RecommendationEngine()
        result = DiagnosticResult(
            module="Storage",
            status=Status.UNKNOWN,
            message="needs admin",
            details={"smart_available": "false", "smart_needs_admin": "true"},
        )
        engine.annotate(result)
        self.assertIn("administrator", result.recommended_action.lower())


if __name__ == "__main__":
    unittest.main()
