"""Overall health scoring.

The algorithm is intentionally simple and documented so it cannot
quietly upgrade UNKNOWN into PASS.

1. Any FAIL  → overall FAIL
2. Else any WARNING → overall WARNING
3. Else if every test is PASS → overall PASS
4. Else → overall UNKNOWN (incomplete or unreadable data)

Scoring never invents a hardware fault. Recommendation text is added
by the recommendation engine in a later phase.
"""

from __future__ import annotations

from app.models.diagnostic_result import DiagnosticResult, Status


def overall_status(tests: list[DiagnosticResult]) -> Status:
    """Compute session-level status from module results."""
    if not tests:
        return Status.UNKNOWN
    statuses = {item.status for item in tests}
    if Status.FAIL in statuses:
        return Status.FAIL
    if Status.WARNING in statuses:
        return Status.WARNING
    if statuses == {Status.PASS}:
        return Status.PASS
    return Status.UNKNOWN


class HealthChecker:
    """Facade used by the diagnostic engine and dashboard."""

    def summarize(self, tests: list[DiagnosticResult]) -> Status:
        return overall_status(tests)
