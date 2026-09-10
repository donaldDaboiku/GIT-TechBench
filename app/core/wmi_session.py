"""COM-initialized WMI connection for worker threads and collectors."""

from __future__ import annotations

import logging
import sys
from typing import Any

logger = logging.getLogger("techbench.wmi")


class WmiSession:
    """One scan's WMI handles. Safe to construct inside a QThread.run()."""

    def __init__(self) -> None:
        self.client: Any = None
        self.wmi_ns: Any = None
        self.available = False
        self.error = ""
        self._initialized = False

    def connect(self) -> None:
        if sys.platform != "win32":
            self.error = "WMI is only available on Windows"
            return
        try:
            import pythoncom

            pythoncom.CoInitialize()
            self._initialized = True
            import wmi

            self.client = wmi.WMI()
            self.available = True
            try:
                self.wmi_ns = wmi.WMI(namespace="root\\wmi")
            except Exception:
                logger.warning("root\\wmi namespace unavailable")
                self.wmi_ns = None
        except Exception as exc:
            self.error = f"WMI unavailable: {exc}"
            logger.warning(self.error)

    def query(self, class_name: str) -> list[Any]:
        if not self.available or self.client is None:
            return []
        try:
            return list(getattr(self.client, class_name)())
        except Exception:
            logger.exception("WMI query failed for %s", class_name)
            return []

    def query_wmi(self, class_name: str) -> list[Any]:
        if self.wmi_ns is None:
            return []
        try:
            return list(getattr(self.wmi_ns, class_name)())
        except Exception:
            logger.debug("root\\wmi query failed for %s", class_name, exc_info=True)
            return []

    def ns(self, path: str) -> Any:
        """Open an extra WMI namespace on this COM apartment."""
        if not self._initialized:
            return None
        try:
            import wmi

            return wmi.WMI(namespace=path)
        except Exception:
            logger.debug("WMI namespace %s unavailable", path, exc_info=True)
            return None

    def close(self) -> None:
        # ponytail: do not CoUninitialize; pythoncom + WMI still hold IUnknowns.
        self.client = None
        self.wmi_ns = None
        self.available = False
        self._initialized = False
