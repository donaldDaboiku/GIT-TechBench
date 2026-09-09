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


# Segoe MDL2 Assets / Segoe Fluent Icons code points.
NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem("dashboard", "Dashboard", "\uE80F", "Overview", 1, "Computer identity and hardware summary."),
    NavItem("full_diagnostic", "Full Diagnostic", "\uE9D9", "Overview", 2, "Run every non-destructive check in sequence."),
    NavItem("hardware_info", "Hardware Info", "\uE770", "Overview", 1, "Full inventory from the last system scan."),
    NavItem("keyboard", "Keyboard Test", "\uE92E", "Hardware Tests", 2, "Interactive virtual keyboard and technician marks."),
    NavItem("mouse", "Mouse Test", "\uE962", "Hardware Tests", 2, "Buttons, double-click, scroll, and movement."),
    NavItem("display", "Display Test", "\uE7F4", "Hardware Tests", 2, "Fullscreen color plates and pixel-check guidance."),
    NavItem("battery", "Battery Health", "\uE83F", "Hardware Tests", 2, "Design vs full-charge capacity health bands."),
    NavItem("storage", "Storage Health", "\uEDA2", "Hardware Tests", 2, "Capacity, SMART, and temperature when available."),
    NavItem("memory", "Memory Info", "\uE950", "Hardware Tests", 2, "RAM map and Windows Memory Diagnostic shortcut."),
    NavItem("cpu", "CPU Monitor", "\uE950", "Hardware Tests", 3, "Live usage, frequency, and temperature if sensed."),
    NavItem("gpu", "GPU Info", "\uEA86", "Hardware Tests", 3, "Adapter name, driver, memory, and usage."),
    NavItem("network", "Network Test", "\uE968", "Connectivity & I/O", 2, "Adapters, ping, DNS, and reachability."),
    NavItem("audio", "Audio Test", "\uE767", "Connectivity & I/O", 3, "Speaker channels and microphone level meter."),
    NavItem("camera", "Camera Test", "\uE722", "Connectivity & I/O", 3, "Preview and capture on explicit user action."),
    NavItem("usb", "USB Ports", "\uE88E", "Connectivity & I/O", 4, "Controllers, connected devices, plug/unplug flow."),
    NavItem("motherboard", "Motherboard / BIOS", "\uE964", "IT Support", 4, "Board model, BIOS/UEFI, Secure Boot, TPM."),
    NavItem("drivers", "Driver Health", "\uE74C", "IT Support", 4, "Device Manager error codes — report only."),
    NavItem("security", "Security Health", "\uE72E", "IT Support", 4, "Defender, Firewall, Update, BitLocker status."),
    NavItem("software", "Software Inventory", "\uE71D", "IT Support", 4, "Installed apps and startup programs (read-only)."),
    NavItem("windows", "Windows Health", "\uE782", "IT Support", 3, "SFC, DISM, Check Disk, Update, Event Viewer."),
    NavItem("reports", "Reports", "\uE8A5", "Output", 5, "PDF/JSON export and session history."),
    NavItem("settings", "Settings", "\uE713", "Output", 1, "Technician name and application options."),
)

PHASE_LABELS = {
    2: "Phase 2 — Core Diagnostics",
    3: "Phase 3 — Advanced Tools",
    4: "Phase 4 — IT Support Modules",
    5: "Phase 5 — Reporting",
}
