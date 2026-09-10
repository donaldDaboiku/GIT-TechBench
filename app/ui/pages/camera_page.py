"""Camera preview and explicit still capture."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

from app.core.recommendation_engine import RecommendationEngine
from app.core.windows_commands import open_windows_camera
from app.modules.camera.camera_tester import (
    CameraTester,
    capture_filename,
    enumerate_cameras,
    opencv_available,
)
from app.ui.components.page_header import PageHeader
from app.ui.components.result_banner import ResultBanner
from app.ui.components.scroll_page import ScrollPage


class CameraPage(ScrollPage):
    result_ready = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.tester = CameraTester()
        self.recommender = RecommendationEngine()
        self._cap = None
        self.body.addWidget(
            PageHeader(
                "Camera Test",
                "Preview is live when a capture backend is available. Stills are saved only when you click Capture.",
            )
        )
        self.combo = QComboBox()
        self.body.addWidget(self.combo)
        btns = QHBoxLayout()
        refresh = QPushButton("Refresh devices")
        refresh.setObjectName("secondaryButton")
        refresh.clicked.connect(self.refresh_devices)
        start = QPushButton("Start preview")
        start.clicked.connect(self.start_preview)
        stop = QPushButton("Stop preview")
        stop.setObjectName("secondaryButton")
        stop.clicked.connect(self.stop_preview)
        capture = QPushButton("Capture still")
        capture.clicked.connect(self.capture_still)
        windows = QPushButton("Open Windows Camera")
        windows.setObjectName("secondaryButton")
        windows.clicked.connect(open_windows_camera)
        for btn in (refresh, start, stop, capture, windows):
            btns.addWidget(btn)
        self.body.addLayout(btns)
        self.preview = QLabel("Preview stopped")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(280)
        self.preview.setStyleSheet("background: #151c27; border: 1px solid #243041; border-radius: 12px;")
        self.body.addWidget(self.preview)
        self.meta = QLabel("")
        self.meta.setObjectName("muted")
        self.meta.setWordWrap(True)
        self.body.addWidget(self.meta)
        self.issue = QCheckBox("Technician: camera issue observed")
        self.note = QLineEdit()
        self.note.setPlaceholderText("Optional note")
        self.issue.toggled.connect(self._issue)
        self.note.textChanged.connect(self._issue)
        self.body.addWidget(self.issue)
        self.body.addWidget(self.note)
        self.banner = ResultBanner()
        self.body.addWidget(self.banner)
        self.body.addStretch()
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._frame)
        self.refresh_devices()
        self._emit()

    def hideEvent(self, event) -> None:  # noqa: N802
        self.stop_preview()
        super().hideEvent(event)

    def refresh_devices(self) -> None:
        self.combo.clear()
        devices = enumerate_cameras()
        if not devices:
            self.combo.addItem("No camera detected")
            self.meta.setText("Windows did not report an imaging device.")
            return
        for device in devices:
            self.combo.addItem(f"{device.name} ({device.source})", device)
        backend = "OpenCV preview available." if opencv_available() else (
            "Live preview backend not installed (opencv-python-headless). "
            "You can still open Windows Camera."
        )
        self.meta.setText(backend)

    def start_preview(self) -> None:
        self.stop_preview()
        if not opencv_available():
            self.preview.setText("Live preview requires opencv-python-headless.")
            return
        import cv2

        data = self.combo.currentData()
        index = data.index if data is not None else 0
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(index)
        if not cap.isOpened():
            self.preview.setText("Could not open this camera.")
            return
        self._cap = cap
        self.tester.previewed = True
        self.tester.selected_name = self.combo.currentText()
        self.timer.start()
        self._emit()

    def stop_preview(self) -> None:
        self.timer.stop()
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _frame(self) -> None:
        if self._cap is None:
            return
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return
        import cv2

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        image = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
        pix = QPixmap.fromImage(image).scaled(
            self.preview.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview.setPixmap(pix)
        self.meta.setText(f"{self.combo.currentText()}  ·  {w}×{h}")

    def capture_still(self) -> None:
        if self._cap is None:
            self.start_preview()
        if self._cap is None:
            self.preview.setText("Start preview before capturing a still.")
            return
        ok, frame = self._cap.read()
        if not ok or frame is None:
            self.preview.setText("No frame available to capture.")
            return
        import cv2

        path = capture_filename(self.combo.currentText() or "camera")
        cv2.imwrite(str(path), frame)
        self.tester.captured_path = str(path)
        self.tester.selected_name = self.combo.currentText()
        self.meta.setText(f"Saved {path}")
        self._emit()

    def _issue(self) -> None:
        self.tester.issue = self.issue.isChecked()
        self.tester.issue_note = self.note.text().strip()
        self._emit()

    def _emit(self) -> None:
        result = self.recommender.annotate(self.tester.to_result())
        self.banner.apply(result)
        self.result_ready.emit(result)
