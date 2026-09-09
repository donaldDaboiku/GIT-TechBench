"""Hardware inventory facade used by the UI and later diagnostic modules."""

from __future__ import annotations

from collections.abc import Callable

from app.core.system_info import SystemInfo, collect_system_info


class HardwareScanner:
    """Collects live inventory. Does not run stress tests or SMART checks."""

    def scan_inventory(self, progress: Callable[[str], None] | None = None) -> SystemInfo:
        return collect_system_info(progress=progress)
