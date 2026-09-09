"""PDF / JSON report export.

Phase 5 implements reportlab PDF generation and JSON dump.
This stub exists so the reports page can name the service without
pretending exports already work.
"""

from __future__ import annotations

from pathlib import Path


class ReportService:
    """Creates technician reports from a diagnostic session."""

    def __init__(self, output_dir: Path | None = None) -> None:
        root = Path(__file__).resolve().parents[2]
        self.output_dir = output_dir or (root / "reports")

    def export_available(self) -> bool:
        """Phase 1: export is not implemented."""
        return False
