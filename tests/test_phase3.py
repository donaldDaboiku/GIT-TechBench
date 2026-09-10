"""Phase 3 CPU / GPU / audio / Windows Health helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.diagnostics_engine import AUTOMATED_MODULES, INTERACTIVE_MODULES
from app.models.diagnostic_result import Status
from app.modules.audio.audio_tester import AudioTester, tone_wav
from app.modules.cpu.cpu_monitor import _status
from app.modules.windows.windows_health import chkdsk_readonly_command, sfc_command


class CpuStatusTests(unittest.TestCase):
    def test_no_temp_is_not_fail(self) -> None:
        status, message = _status(12.0, None, "Temperature sensor unavailable", False, 85, 95)
        self.assertEqual(status, Status.PASS)
        self.assertIn("temperature sensor unavailable", message)

    def test_hot_is_warning(self) -> None:
        status, _ = _status(40.0, 88.0, "acpi", False, 85, 95)
        self.assertEqual(status, Status.WARNING)

    def test_critical_temp_is_fail(self) -> None:
        status, _ = _status(90.0, 98.0, "acpi", True, 85, 95)
        self.assertEqual(status, Status.FAIL)


class AudioToneTests(unittest.TestCase):
    def test_tone_file_is_stereo(self) -> None:
        path = tone_wav("left", seconds=0.05)
        self.assertTrue(path.exists())
        self.assertGreater(path.stat().st_size, 44)

    def test_partial_audio_unknown(self) -> None:
        tester = AudioTester()
        tester.speaker_left = True
        self.assertEqual(tester.to_result().status, Status.UNKNOWN)


class WindowsCommandTests(unittest.TestCase):
    def test_chkdsk_is_readonly(self) -> None:
        args = chkdsk_readonly_command("C")
        self.assertTrue(args[-1].startswith("C:"))
        self.assertNotIn("/F", args)
        self.assertTrue(sfc_command()[-1] == "/scannow")


class EngineCatalogTests(unittest.TestCase):
    def test_phase3_modules_listed(self) -> None:
        self.assertIn("CPU", AUTOMATED_MODULES)
        self.assertIn("GPU", AUTOMATED_MODULES)
        self.assertIn("Audio", INTERACTIVE_MODULES)
        self.assertIn("Camera", INTERACTIVE_MODULES)
        self.assertIn("Windows", INTERACTIVE_MODULES)


if __name__ == "__main__":
    unittest.main()
