"""PDF and JSON report export."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app import APP_NAME, APP_TAGLINE


class ReportService:
    """Creates technician reports from a diagnostic session."""

    def __init__(self, output_dir: Path | None = None) -> None:
        root = Path(__file__).resolve().parents[2]
        self.output_dir = output_dir or (root / "reports")

    def export_available(self) -> bool:
        try:
            import reportlab  # noqa: F401
        except ImportError:
            return False
        return True

    def default_stem(self, session: dict[str, Any]) -> str:
        when = str(session.get("created_at") or datetime.now().isoformat(timespec="seconds"))
        stamp = when.replace(":", "").replace(" ", "_")[:15]
        name = str(session.get("computer_name") or "pc").replace(" ", "_")
        serial = str(session.get("serial_number") or "noserial").replace(" ", "_")
        return f"{name}_{serial}_{stamp}"

    def export_json(self, session: dict[str, Any], path: Path | None = None) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        target = path or (self.output_dir / f"{self.default_stem(session)}.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(session)
        payload.setdefault("app", APP_NAME)
        payload.setdefault("tagline", APP_TAGLINE)
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return target

    def export_pdf(self, session: dict[str, Any], path: Path | None = None) -> Path:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        self.output_dir.mkdir(parents=True, exist_ok=True)
        target = path or (self.output_dir / f"{self.default_stem(session)}.pdf")
        target.parent.mkdir(parents=True, exist_ok=True)

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Heading1"],
            fontSize=16,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=6,
        )
        heading = ParagraphStyle(
            "ReportHeading",
            parent=styles["Heading2"],
            fontSize=12,
            textColor=colors.HexColor("#1e3a5f"),
            spaceBefore=10,
            spaceAfter=6,
        )
        body = ParagraphStyle(
            "ReportBody",
            parent=styles["BodyText"],
            fontSize=9,
            leading=12,
        )
        muted = ParagraphStyle(
            "ReportMuted",
            parent=body,
            textColor=colors.HexColor("#64748b"),
            fontSize=8,
        )
        cell = ParagraphStyle("ReportCell", parent=body, fontSize=8, leading=10)

        identity = session.get("identity") if isinstance(session.get("identity"), dict) else {}
        tests = session.get("tests") if isinstance(session.get("tests"), list) else []

        story: list[object] = [
            Paragraph(f"{APP_NAME} — Diagnostic Report", title_style),
            Paragraph(APP_TAGLINE, muted),
            Paragraph(
                f"Generated {session.get('created_at') or datetime.now().isoformat(timespec='seconds')}  ·  "
                f"Overall: {session.get('overall_status') or 'UNKNOWN'}  ·  "
                f"Technician: {session.get('technician_name') or '—'}",
                body,
            ),
            Spacer(1, 4),
            Paragraph("Computer", heading),
        ]
        ident_rows = [
            ["Computer", str(session.get("computer_name") or identity.get("computer_name") or "—")],
            ["Manufacturer", str(identity.get("manufacturer") or "—")],
            ["Model", str(identity.get("model") or "—")],
            ["Serial", str(session.get("serial_number") or identity.get("serial_number") or "—")],
            ["OS", str(identity.get("os") or "—")],
            ["CPU", str(identity.get("cpu") or "—")],
            ["RAM", str(identity.get("ram") or "—")],
            ["Storage", str(identity.get("storage") or "—")],
            ["BIOS", str(identity.get("bios") or "—")],
        ]
        ident_table = Table(ident_rows, colWidths=[35 * mm, 140 * mm])
        ident_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(ident_table)
        story.append(Paragraph("Diagnostic results", heading))

        header = ["Module", "Status", "Message", "Likely cause", "Action", "Conf."]
        table_data: list[list[object]] = [header]
        for item in tests:
            if not isinstance(item, dict):
                continue
            table_data.append(
                [
                    Paragraph(str(item.get("module") or ""), cell),
                    Paragraph(str(item.get("status") or ""), cell),
                    Paragraph(str(item.get("message") or ""), cell),
                    Paragraph(str(item.get("likely_cause") or ""), cell),
                    Paragraph(str(item.get("recommended_action") or ""), cell),
                    Paragraph(str(item.get("confidence") or ""), cell),
                ]
            )
        if len(table_data) == 1:
            table_data.append([Paragraph("No tests stored.", cell), "", "", "", "", ""])
        results_table = Table(table_data, colWidths=[22 * mm, 18 * mm, 48 * mm, 38 * mm, 42 * mm, 16 * mm])
        results_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ]
            )
        )
        story.append(results_table)
        story.append(Paragraph("Technician notes and final recommendation", heading))
        story.append(Paragraph(f"<b>Notes:</b> {_pdf_text(session.get('notes'))}", body))
        story.append(Paragraph(f"<b>Repair needed:</b> {_pdf_text(session.get('repair_needed'))}", body))
        story.append(Paragraph(f"<b>Parts required:</b> {_pdf_text(session.get('parts_required'))}", body))
        story.append(Paragraph(f"<b>Further testing:</b> {_pdf_text(session.get('further_testing'))}", body))
        story.append(Spacer(1, 8))
        story.append(
            Paragraph(
                "Likely cause / recommended action / confidence are suggestions from the rule engine. "
                "They are not a confirmed diagnosis. The technician may edit or override them before this report is issued.",
                muted,
            )
        )

        document = SimpleDocTemplate(
            str(target),
            pagesize=A4,
            leftMargin=14 * mm,
            rightMargin=14 * mm,
            topMargin=14 * mm,
            bottomMargin=14 * mm,
            title=f"{APP_NAME} Diagnostic Report",
            author=str(session.get("technician_name") or APP_NAME),
        )
        document.build(story)
        return target


def build_session_record(
    *,
    info: Any = None,
    results: list[Any],
    technician_name: str = "",
    notes: str = "",
    repair_needed: str = "",
    parts_required: str = "",
    further_testing: str = "",
) -> dict[str, Any]:
    from app.core.health_checker import overall_status
    from app.models.diagnostic_result import DiagnosticResult

    identity: dict[str, str] = {}
    if info is not None:
        identity = {
            "computer_name": info.computer_name.display(),
            "manufacturer": info.manufacturer.display(),
            "model": info.model.display(),
            "serial_number": info.serial_number.display(),
            "os": info.os_caption.display(),
            "cpu": info.cpu_name.display(),
            "ram": info.ram_total_display(),
            "storage": info.storage_summary(),
            "bios": info.bios_version.display(),
        }
    tests = [item.to_dict() if isinstance(item, DiagnosticResult) else item for item in results]
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "computer_name": identity.get("computer_name") or "",
        "serial_number": identity.get("serial_number") or "",
        "technician_name": technician_name,
        "overall_status": overall_status(results).value if results else "UNKNOWN",
        "identity": identity,
        "tests": tests,
        "notes": notes,
        "repair_needed": repair_needed,
        "parts_required": parts_required,
        "further_testing": further_testing,
    }


def _pdf_text(value: object) -> str:
    text = str(value or "").strip() or "—"
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )
