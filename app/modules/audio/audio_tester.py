"""Speaker tone files and microphone RMS via WinMM. No extra audio libraries."""

from __future__ import annotations

import math
import struct
import tempfile
import wave
import winsound
from dataclasses import dataclass
from pathlib import Path

from app.models.diagnostic_result import DiagnosticResult, Status

MODULE = "Audio"


@dataclass
class AudioTester:
    phase: int = 3
    title: str = "Audio Test"
    speaker_left: bool = False
    speaker_right: bool = False
    speaker_both: bool = False
    mic_seen_level: bool = False
    mic_name: str = "Unavailable"
    issue: bool = False
    issue_note: str = ""

    def reset(self) -> None:
        self.speaker_left = self.speaker_right = self.speaker_both = False
        self.mic_seen_level = False
        self.issue = False
        self.issue_note = ""

    def to_result(self) -> DiagnosticResult:
        played = sum([self.speaker_left, self.speaker_right, self.speaker_both])
        if self.issue:
            status = Status.FAIL
            message = self.issue_note or "Technician recorded an audio issue."
        elif played == 3 and self.mic_seen_level:
            status = Status.PASS
            message = f"Left/right/both tones played; microphone level detected ({self.mic_name})."
        elif played or self.mic_seen_level:
            status = Status.UNKNOWN
            message = (
                f"Partial audio test (speakers {played}/3, "
                f"mic {'detected' if self.mic_seen_level else 'not detected'})."
            )
        else:
            status = Status.UNKNOWN
            message = "Audio test not started this session."
        return DiagnosticResult(
            module=MODULE,
            status=status,
            message=message,
            details={
                "speakers": str(played),
                "mic": "true" if self.mic_seen_level else "false",
                "issue": "true" if self.issue else "false",
            },
        )


def tone_wav(pan: str, seconds: float = 0.7, freq: float = 440.0) -> Path:
    """Write a stereo sine WAV with energy on left, right, or both."""
    rate = 44100
    n = int(rate * seconds)
    path = Path(tempfile.gettempdir()) / f"techbench_tone_{pan}.wav"
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        for i in range(n):
            fade = 1.0
            edge = int(rate * 0.02)
            if i < edge:
                fade = i / edge
            elif i > n - edge:
                fade = (n - i) / edge
            sample = int(12000 * fade * math.sin(2 * math.pi * freq * i / rate))
            left = sample if pan in {"left", "both"} else 0
            right = sample if pan in {"right", "both"} else 0
            frames += struct.pack("<hh", left, right)
        handle.writeframes(frames)
    return path


def play_tone(pan: str) -> None:
    path = tone_wav(pan)
    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_NODEFAULT)


def list_input_devices() -> list[str]:
    names: list[str] = []
    try:
        import ctypes
        from ctypes import wintypes

        class WAVEINCAPSW(ctypes.Structure):
            _fields_ = [
                ("wMid", wintypes.WORD),
                ("wPid", wintypes.WORD),
                ("vDriverVersion", wintypes.UINT),
                ("szPname", wintypes.WCHAR * 32),
                ("dwFormats", wintypes.DWORD),
                ("wChannels", wintypes.WORD),
                ("wReserved1", wintypes.WORD),
            ]

        winmm = ctypes.windll.winmm
        count = int(winmm.waveInGetNumDevs())
        for index in range(count):
            caps = WAVEINCAPSW()
            if winmm.waveInGetDevCapsW(index, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
                names.append(str(caps.szPname).strip("\x00"))
    except Exception:
        return names
    return names


def sample_mic_rms(device_index: int = 0, milliseconds: int = 80) -> float | None:
    """Capture a short PCM burst and return 0-100 RMS. None if the device cannot be opened."""
    import ctypes
    from ctypes import wintypes

    class WAVEFORMATEX(ctypes.Structure):
        _fields_ = [
            ("wFormatTag", wintypes.WORD),
            ("nChannels", wintypes.WORD),
            ("nSamplesPerSec", wintypes.DWORD),
            ("nAvgBytesPerSec", wintypes.DWORD),
            ("nBlockAlign", wintypes.WORD),
            ("wBitsPerSample", wintypes.WORD),
            ("cbSize", wintypes.WORD),
        ]

    class WAVEHDR(ctypes.Structure):
        _fields_ = [
            ("lpData", ctypes.c_void_p),
            ("dwBufferLength", wintypes.DWORD),
            ("dwBytesRecorded", wintypes.DWORD),
            ("dwUser", ctypes.POINTER(ctypes.c_ulong)),
            ("dwFlags", wintypes.DWORD),
            ("dwLoops", wintypes.DWORD),
            ("lpNext", ctypes.c_void_p),
            ("reserved", ctypes.POINTER(ctypes.c_ulong)),
        ]

    rate = 16000
    channels = 1
    bits = 16
    nbytes = int(rate * channels * (bits // 8) * milliseconds / 1000)
    buf = ctypes.create_string_buffer(nbytes)
    fmt = WAVEFORMATEX(1, channels, rate, rate * channels * bits // 8, channels * bits // 8, bits, 0)
    handle = wintypes.HANDLE()
    winmm = ctypes.windll.winmm
    err = winmm.waveInOpen(ctypes.byref(handle), device_index, ctypes.byref(fmt), 0, 0, 0)
    if err != 0:
        return None
    hdr = WAVEHDR()
    hdr.lpData = ctypes.cast(buf, ctypes.c_void_p)
    hdr.dwBufferLength = nbytes
    winmm.waveInPrepareHeader(handle, ctypes.byref(hdr), ctypes.sizeof(hdr))
    winmm.waveInAddBuffer(handle, ctypes.byref(hdr), ctypes.sizeof(hdr))
    winmm.waveInStart(handle)
    import time

    time.sleep(milliseconds / 1000 + 0.02)
    winmm.waveInStop(handle)
    recorded = bytes(buf)[: max(int(hdr.dwBytesRecorded), 0) or nbytes]
    winmm.waveInUnprepareHeader(handle, ctypes.byref(hdr), ctypes.sizeof(hdr))
    winmm.waveInClose(handle)
    if len(recorded) < 4:
        return 0.0
    samples = struct.unpack("<" + "h" * (len(recorded) // 2), recorded[: len(recorded) // 2 * 2])
    if not samples:
        return 0.0
    mean = sum(s * s for s in samples) / len(samples)
    rms = math.sqrt(mean) / 32768.0
    return max(0.0, min(100.0, rms * 250.0))

