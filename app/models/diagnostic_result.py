"""Diagnostic result types used by the engine and UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    """Health status for a module or overall session.

    UNKNOWN is used when data could not be retrieved. It is not a pass.
    """

    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class Confidence(str, Enum):
    """How strong the evidence is for a recommendation — never a confirmed fault."""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


@dataclass
class DiagnosticResult:
    """Structured result from one diagnostic module.

    Recommendation fields are suggestions for the technician to accept,
    edit, or override before they appear in a report.
    """

    module: str
    status: Status
    message: str
    likely_cause: str = ""
    recommended_action: str = ""
    confidence: Confidence | None = None
    details: dict[str, str] = field(default_factory=dict)
    technician_override: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "module": self.module,
            "status": self.status.value,
            "message": self.message,
            "likely_cause": self.likely_cause,
            "recommended_action": self.recommended_action,
            "confidence": self.confidence.value if self.confidence else "",
            "details": dict(self.details),
            "technician_override": self.technician_override,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> DiagnosticResult:
        status_raw = str(data.get("status") or "UNKNOWN")
        try:
            status = Status(status_raw)
        except ValueError:
            status = Status.UNKNOWN
        conf_raw = str(data.get("confidence") or "")
        confidence = next((item for item in Confidence if item.value == conf_raw), None)
        details = data.get("details") or {}
        if not isinstance(details, dict):
            details = {}
        return cls(
            module=str(data.get("module") or ""),
            status=status,
            message=str(data.get("message") or ""),
            likely_cause=str(data.get("likely_cause") or ""),
            recommended_action=str(data.get("recommended_action") or ""),
            confidence=confidence,
            details={str(key): str(value) for key, value in details.items()},
            technician_override=str(data.get("technician_override") or ""),
        )
