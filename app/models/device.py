"""Identifying information for the machine under test."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Device:
    """Inventory identity for a scanned PC."""

    name: str
    manufacturer: str
    model: str
    serial_number: str
    os_caption: str
    windows_version: str
    bios_version: str = ""
    technician_name: str = ""
