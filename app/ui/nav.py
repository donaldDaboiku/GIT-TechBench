"""Navigation catalog and theme tokens."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NavItem:
    id: str
    label: str
    glyph: str
    group: str
    phase: int
    description: str


# Segoe MDL2 Assets / Segoe Fluent Icons — one unique glyph per tool.
NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem("dashboard", "Dashboard", "\uE80F", "Overview", 1, "Computer identity and hardware summary."),  # Home
    NavItem("full_diagnostic", "Full Diagnostic", "\uE90F", "Overview", 2, "Run every non-destructive check in sequence."),  # Repair
    NavItem("hardware_info", "Hardware Info", "\uE770", "Overview", 1, "Full inventory from the last system scan."),  # System
    NavItem("keyboard", "Keyboard Test", "\uE765", "Hardware Tests", 2, "Interactive virtual keyboard and technician marks."),  # KeyboardClassic
    NavItem("mouse", "Mouse Test", "\uE7C9", "Hardware Tests", 2, "Buttons, double-click, scroll, and movement."),  # TouchPointer
    NavItem("display", "Display Test", "\uE7F4", "Hardware Tests", 2, "Fullscreen color plates and pixel-check guidance."),  # TVMonitor
    NavItem("battery", "Battery Health", "\uE83F", "Hardware Tests", 2, "Design vs full-charge capacity health bands."),  # Battery10
    NavItem("storage", "Storage Health", "\uEDA2", "Hardware Tests", 2, "Capacity, SMART, and temperature when available."),  # HardDrive
    NavItem("memory", "Memory Info", "\uE8C8", "Hardware Tests", 2, "RAM map and Windows Memory Diagnostic shortcut."),  # Memory
    NavItem("cpu", "CPU Monitor", "\uE9A5", "Hardware Tests", 3, "Live usage, frequency, and temperature if sensed."),  # SpeedHigh
    NavItem("gpu", "GPU Info", "\uEA86", "Hardware Tests", 3, "Adapter name, driver, memory, and usage."),  # Game
    NavItem("network", "Network Test", "\uE701", "Connectivity & I/O", 2, "Adapters, ping, DNS, and reachability."),  # Wifi
    NavItem("audio", "Audio Test", "\uE767", "Connectivity & I/O", 3, "Speaker channels and microphone level meter."),  # Volume
    NavItem("camera", "Camera Test", "\uE722", "Connectivity & I/O", 3, "Preview and capture on explicit user action."),  # Camera
    NavItem("usb", "USB Ports", "\uE88E", "Connectivity & I/O", 4, "Controllers, connected devices, plug/unplug flow."),  # USB
    NavItem("motherboard", "Motherboard / BIOS", "\uE964", "IT Support", 4, "Board model, BIOS/UEFI, Secure Boot, TPM."),  # Chip
    NavItem("drivers", "Driver Health", "\uE8B7", "IT Support", 4, "Device Manager error codes — report only."),  # DeveloperTools
    NavItem("security", "Security Health", "\uE72E", "IT Support", 4, "Defender, Firewall, Update, BitLocker status."),  # Shield
    NavItem("software", "Software Inventory", "\uE71D", "IT Support", 4, "Installed apps and startup programs (read-only)."),  # AllApps
    NavItem("windows", "Windows Health", "\uE782", "IT Support", 3, "SFC, DISM, Check Disk, Update, Event Viewer."),  # Admin
    NavItem("reports", "Reports", "\uE8A5", "Output", 5, "PDF/JSON export and session history."),  # Document
    NavItem("settings", "Settings", "\uE713", "Output", 1, "Technician name and application options."),  # Settings
)


def nav_glyph(nav_id: str) -> str:
    """Sidebar glyph for a nav id. Empty string if unknown."""
    for item in NAV_ITEMS:
        if item.id == nav_id:
            return item.glyph
    return ""


PHASE_LABELS = {
    2: "Phase 2 — Core Diagnostics",
    3: "Phase 3 — Advanced Tools",
    4: "Phase 4 — IT Support Modules",
    5: "Phase 5 — Reporting",
    6: "Phase 6 — Portable USB",
}
