"""Paint the GIT badge into assets/icons/techbench.ico (taskbar + exe)."""

from __future__ import annotations

import os
import struct
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPainterPath

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "icons"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def _paint(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = max(1.0, size / 16)
    radius = size * 0.22
    path = QPainterPath()
    path.addRoundedRect(QRectF(margin, margin, size - 2 * margin, size - 2 * margin), radius, radius)
    painter.fillPath(path, QColor("#1d4ed8"))
    painter.setPen(QColor("#ffffff"))
    font = QFont("Segoe UI")
    font.setBold(True)
    font.setPixelSize(max(8, int(size * (0.56 if size < 32 else 0.30))))
    painter.setFont(font)
    text = "G" if size < 32 else "GIT"
    painter.drawText(image.rect(), int(Qt.AlignmentFlag.AlignCenter), text)
    painter.end()
    return image


def _png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def _write_ico(path: Path, pngs: list[tuple[int, bytes]]) -> None:
    count = len(pngs)
    offset = 6 + 16 * count
    directory = bytearray()
    payload = bytearray()
    for size, data in pngs:
        dim = 0 if size >= 256 else size
        directory += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        payload += data
        offset += len(data)
    path.write_bytes(struct.pack("<HHH", 0, 1, count) + directory + payload)


def main() -> int:
    QGuiApplication.instance() or QGuiApplication([])
    OUT.mkdir(parents=True, exist_ok=True)
    pngs = [(size, _png_bytes(_paint(size))) for size in SIZES]
    _write_ico(OUT / "techbench.ico", pngs)
    _paint(256).save(str(OUT / "techbench.png"), "PNG")
    print(OUT / "techbench.ico")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
