"""Mouse session checks — detection only unless the technician flags an issue."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.diagnostic_result import DiagnosticResult, Status

MODULE = "Mouse"

CHECKS = ("left", "right", "middle", "double", "scroll", "move")


@dataclass
class MouseTester:
    phase: int = 2
    title: str = "Mouse Test"
    detected: dict[str, bool] = field(default_factory=lambda: {name: False for name in CHECKS})
    issue_observed: bool = False
    issue_note: str = ""

    def reset(self) -> None:
        self.detected = {name: False for name in CHECKS}
        self.issue_observed = False
        self.issue_note = ""

    def mark_detected(self, name: str) -> None:
        if name in self.detected:
            self.detected[name] = True

    def to_result(self) -> DiagnosticResult:
        done = sum(1 for value in self.detected.values() if value)
        total = len(self.detected)
        missing = [name for name, value in self.detected.items() if not value]
        if self.issue_observed:
            status = Status.FAIL
            message = self.issue_note or "Technician recorded a pointer hardware issue."
        elif done == total:
            status = Status.PASS
            message = "Left, right, middle, double-click, scroll, and movement all detected."
        elif done:
            status = Status.UNKNOWN
            message = f"{done}/{total} checks detected; not yet complete ({', '.join(missing)})."
        else:
            status = Status.UNKNOWN
            message = "Mouse test not started this session."
        return DiagnosticResult(
            module=MODULE,
            status=status,
            message=message,
            details={"detected": str(done), "issue": "true" if self.issue_observed else "false"},
        )
