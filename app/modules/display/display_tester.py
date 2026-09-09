"""Display color-plate session and technician visual findings."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.diagnostic_result import DiagnosticResult, Status

MODULE = "Display"

PLATES: tuple[tuple[str, str], ...] = (
    ("black", "#000000"),
    ("white", "#ffffff"),
    ("red", "#ff0000"),
    ("green", "#00ff00"),
    ("blue", "#0000ff"),
)

GUIDANCE = (
    "Black: look for bright/stuck pixels and backlight bleed.",
    "White: look for dark/dead pixels and uneven backlight.",
    "Red / Green / Blue: look for tint, missing color, or stuck subpixels.",
    "Press Space or click for the next plate. Press Esc to exit.",
)


@dataclass
class DisplayTester:
    phase: int = 2
    title: str = "Display Test"
    plates_viewed: set[str] = field(default_factory=set)
    dead_or_stuck_pixel: bool = False
    backlight_issue: bool = False
    color_issue: bool = False
    not_tested: bool = True

    def reset(self) -> None:
        self.plates_viewed.clear()
        self.dead_or_stuck_pixel = False
        self.backlight_issue = False
        self.color_issue = False
        self.not_tested = True

    def note_plate(self, name: str) -> None:
        self.plates_viewed.add(name)
        self.not_tested = False

    def to_result(self) -> DiagnosticResult:
        defects = []
        if self.dead_or_stuck_pixel:
            defects.append("dead/stuck pixel")
        if self.backlight_issue:
            defects.append("backlight")
        if self.color_issue:
            defects.append("color")
        if defects:
            status = Status.FAIL if self.dead_or_stuck_pixel else Status.WARNING
            message = "Technician recorded: " + ", ".join(defects) + "."
        elif self.plates_viewed:
            status = Status.PASS
            message = (
                f"Visual inspection completed ({len(self.plates_viewed)}/{len(PLATES)} plates). "
                "No defects recorded."
            )
        else:
            status = Status.UNKNOWN
            message = "Display plates have not been run this session."
        return DiagnosticResult(
            module=MODULE,
            status=status,
            message=message,
            details={
                "dead_or_stuck_pixel": "true" if self.dead_or_stuck_pixel else "false",
                "backlight_issue": "true" if self.backlight_issue else "false",
                "color_issue": "true" if self.color_issue else "false",
                "plates": str(len(self.plates_viewed)),
            },
        )
