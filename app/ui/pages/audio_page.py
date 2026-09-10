"""Speaker channel test and microphone level meter."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
)

from app.core.recommendation_engine import RecommendationEngine
from app.modules.audio.audio_tester import (
    AudioTester,
    list_input_devices,
    play_tone,
)
from app.ui.components.page_header import PageHeader
from app.ui.components.result_banner import ResultBanner
from app.ui.components.scroll_page import ScrollPage
from app.ui.workers import CallableWorker, MicWorker


class AudioPage(ScrollPage):
    result_ready = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.tester = AudioTester()
        self.recommender = RecommendationEngine()
        self._tone_worker: CallableWorker | None = None
        self.body.addWidget(
            PageHeader(
                "Audio Test",
                "Play a left, right, or both-channel tone. The mic meter uses the selected input device.",
            )
        )
        row = QHBoxLayout()
        for pan, label in (("left", "Left"), ("right", "Right"), ("both", "Both")):
            btn = QPushButton(f"Play {label}")
            btn.clicked.connect(lambda _=False, p=pan: self._play(p))
            row.addWidget(btn)
        self.body.addLayout(row)
        self.speaker_status = QLabel("No tone played yet.")
        self.speaker_status.setObjectName("muted")
        self.body.addWidget(self.speaker_status)

        devices = list_input_devices()
        self.mic_box = QComboBox()
        if devices:
            self.mic_box.addItems(devices)
            self.tester.mic_name = devices[0]
        else:
            self.mic_box.addItem("No recording device found")
        self.mic_box.currentTextChanged.connect(self._mic_changed)
        self.body.addWidget(QLabel("MICROPHONE"))
        self.body.addWidget(self.mic_box)
        self.meter = QProgressBar()
        self.meter.setRange(0, 100)
        self.body.addWidget(self.meter)
        self.mic_label = QLabel("Meter idle — speak after the device is selected.")
        self.mic_label.setObjectName("muted")
        self.body.addWidget(self.mic_label)

        self.issue = QCheckBox("Technician: audio issue observed")
        self.note = QLineEdit()
        self.note.setPlaceholderText("Optional note")
        self.issue.toggled.connect(self._issue)
        self.note.textChanged.connect(self._issue)
        self.body.addWidget(self.issue)
        self.body.addWidget(self.note)
        self.banner = ResultBanner()
        self.body.addWidget(self.banner)
        self.body.addStretch()
        self._mic: MicWorker | None = None
        self._emit()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._start_mic()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._stop_mic()
        super().hideEvent(event)

    def _mic_changed(self, name: str) -> None:
        self.tester.mic_name = name
        if self.isVisible():
            self._start_mic()

    def _start_mic(self) -> None:
        self._stop_mic()
        if self.mic_box.count() == 0 or "No recording" in self.mic_box.currentText():
            return
        self._mic = MicWorker(self.mic_box.currentIndex(), self)
        self._mic.level.connect(self._on_level)
        self._mic.failed.connect(self.mic_label.setText)
        self._mic.start()

    def _stop_mic(self) -> None:
        if self._mic is not None:
            self._mic.stop()
            self._mic.wait(500)
            self._mic = None

    def _play(self, pan: str) -> None:
        if self._tone_worker is not None and self._tone_worker.isRunning():
            return
        self.speaker_status.setText(f"Playing {pan} channel…")
        self._tone_worker = CallableWorker(lambda: play_tone(pan), self)
        self._tone_worker.succeeded.connect(lambda _=None, p=pan: self._played(p))
        self._tone_worker.failed.connect(lambda msg: self.speaker_status.setText(msg))
        self._tone_worker.start()

    def _played(self, pan: str) -> None:
        if pan == "left":
            self.tester.speaker_left = True
        elif pan == "right":
            self.tester.speaker_right = True
        else:
            self.tester.speaker_both = True
        self.speaker_status.setText(f"Played {pan} channel.")
        self._emit()

    def _on_level(self, level: float) -> None:
        self.meter.setValue(int(level))
        if level > 4:
            self.mic_label.setText(f"{self.tester.mic_name}: level {level:.0f}")
            if not self.tester.mic_seen_level:
                self.tester.mic_seen_level = True
                self._emit()

    def _issue(self) -> None:
        self.tester.issue = self.issue.isChecked()
        self.tester.issue_note = self.note.text().strip()
        self._emit()

    def _emit(self) -> None:
        result = self.recommender.annotate(self.tester.to_result())
        self.banner.apply(result)
        self.result_ready.emit(result)
