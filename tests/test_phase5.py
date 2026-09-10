"""Phase 5 history and report export."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.diagnostic_result import Confidence, DiagnosticResult, Status
from app.services.database_service import DatabaseService
from app.services.report_service import ReportService, build_session_record


class ResultRoundTripTests(unittest.TestCase):
    def test_dict_roundtrip(self) -> None:
        original = DiagnosticResult(
            module="Storage",
            status=Status.WARNING,
            message="SSD. Low space.",
            likely_cause="Wear",
            recommended_action="Back up",
            confidence=Confidence.MEDIUM,
            details={"drive_kinds": "SSD"},
        )
        restored = DiagnosticResult.from_dict(original.to_dict())
        self.assertEqual(restored.module, "Storage")
        self.assertEqual(restored.status, Status.WARNING)
        self.assertEqual(restored.confidence, Confidence.MEDIUM)
        self.assertEqual(restored.details["drive_kinds"], "SSD")


class DatabaseServiceTests(unittest.TestCase):
    def test_save_search_and_get(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = DatabaseService(Path(tmp) / "techbench.db")
            result = DiagnosticResult(module="Battery", status=Status.PASS, message="Good")
            session = build_session_record(
                results=[result],
                technician_name="Alex",
                notes="Swap later",
            )
            session["computer_name"] = "MIT"
            session["serial_number"] = "5CG2142VQW"
            session_id = db.save(session)
            rows = db.list_sessions("5CG2142")
            self.assertEqual(len(rows), 1)
            loaded = db.get(session_id)
            assert loaded is not None
            self.assertEqual(loaded["technician_name"], "Alex")
            self.assertEqual(loaded["notes"], "Swap later")
            self.assertEqual(loaded["tests"][0]["module"], "Battery")


class ReportExportTests(unittest.TestCase):
    def test_json_and_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = ReportService(Path(tmp))
            result = DiagnosticResult(
                module="Drivers",
                status=Status.FAIL,
                message="Code 28",
                likely_cause="Missing driver",
                recommended_action="Vendor site",
                confidence=Confidence.MEDIUM,
            )
            session = build_session_record(results=[result], technician_name="Alex")
            session["computer_name"] = "MIT"
            json_path = service.export_json(session)
            self.assertTrue(json_path.exists())
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["tests"][0]["module"], "Drivers")
            self.assertTrue(service.export_available())
            pdf_path = service.export_pdf(session)
            self.assertTrue(pdf_path.exists())
            self.assertGreater(pdf_path.stat().st_size, 200)


if __name__ == "__main__":
    unittest.main()
