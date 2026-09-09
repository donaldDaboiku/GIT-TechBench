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
