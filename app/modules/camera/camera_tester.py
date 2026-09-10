"""Camera enumeration and optional OpenCV preview/capture."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.core.config import project_root
from app.core.wmi_session import WmiSession
from app.models.diagnostic_result import DiagnosticResult, Status

logger = logging.getLogger("techbench.camera")

MODULE = "Camera"


@dataclass
class CameraDevice:
    index: int
    name: str
    source: str
    resolution: str = "Unavailable"


@dataclass
class CameraTester:
    phase: int = 3
    title: str = "Camera Test"
    previewed: bool = False
    captured_path: str = ""
    issue: bool = False
    issue_note: str = ""
    selected_name: str = ""

    def reset(self) -> None:
        self.previewed = False
        self.captured_path = ""
        self.issue = False
        self.issue_note = ""

    def to_result(self) -> DiagnosticResult:
        if self.issue:
            status = Status.FAIL
            message = self.issue_note or "Technician recorded a camera issue."
        elif self.captured_path:
            status = Status.PASS
            message = f"Previewed {self.selected_name}; captured {self.captured_path}."
        elif self.previewed:
            status = Status.PASS
            message = f"Live preview ran for {self.selected_name}. No still captured."
        else:
            status = Status.UNKNOWN
            message = "Camera test not started this session."
        return DiagnosticResult(
            module=MODULE,
            status=status,
            message=message,
            details={
                "previewed": "true" if self.previewed else "false",
                "captured": "true" if self.captured_path else "false",
            },
        )


def enumerate_cameras() -> list[CameraDevice]:
    found: list[CameraDevice] = []
    session = WmiSession()
    session.connect()
    try:
        seen: set[str] = set()
        for row in session.query("Win32_PnPEntity"):
            pnp = str(getattr(row, "PNPClass", "") or "")
            name = str(getattr(row, "Name", "") or "").strip()
            if not name or name.lower() in seen:
                continue
            pnp_l = pnp.lower()
            name_l = name.lower()
            is_cam = pnp_l == "camera" or (
                pnp_l == "image"
                and any(token in name_l for token in ("camera", "webcam", "integrated"))
            )
            if is_cam or ("webcam" in name_l or name_l.endswith("camera")):
                if "usb composite" in name.lower():
                    continue
                seen.add(name.lower())
                found.append(CameraDevice(index=len(found), name=name, source="WMI Win32_PnPEntity"))
    finally:
        session.close()
    if not found:
        for index, name in _opencv_names():
            found.append(CameraDevice(index=index, name=name, source="DirectShow/MSMF"))
    return found


def opencv_available() -> bool:
    try:
        import cv2  # noqa: F401

        return True
    except Exception:
        return False


def _opencv_names() -> list[tuple[int, str]]:
    if not opencv_available():
        return []
    import cv2

    names: list[tuple[int, str]] = []
    for index in range(6):
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if cap is None or not cap.isOpened():
            if cap is not None:
                cap.release()
            continue
        names.append((index, f"Camera {index}"))
        cap.release()
    return names


def capture_dir() -> Path:
    path = project_root() / "reports" / "captures"
    path.mkdir(parents=True, exist_ok=True)
    return path


def capture_filename(camera_name: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(ch if ch.isalnum() else "_" for ch in camera_name)[:40]
    return capture_dir() / f"{safe}_{stamp}.png"
