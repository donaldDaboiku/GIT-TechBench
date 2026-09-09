"""Health-score algorithm checks."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.health_checker import overall_status
from app.models.diagnostic_result import DiagnosticResult, Status


def _r(status: Status) -> DiagnosticResult:
    return DiagnosticResult(module="Test", status=status, message="x")


class OverallStatusTests(unittest.TestCase):
    def test_empty_is_unknown(self) -> None:
        self.assertEqual(overall_status([]), Status.UNKNOWN)

    def test_fail_wins(self) -> None:
        tests = [_r(Status.PASS), _r(Status.FAIL), _r(Status.WARNING)]
        self.assertEqual(overall_status(tests), Status.FAIL)

    def test_warning_over_pass(self) -> None:
        tests = [_r(Status.PASS), _r(Status.WARNING)]
        self.assertEqual(overall_status(tests), Status.WARNING)

    def test_all_pass(self) -> None:
        tests = [_r(Status.PASS), _r(Status.PASS)]
        self.assertEqual(overall_status(tests), Status.PASS)

    def test_unknown_blocks_pass(self) -> None:
        tests = [_r(Status.PASS), _r(Status.UNKNOWN)]
        self.assertEqual(overall_status(tests), Status.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
