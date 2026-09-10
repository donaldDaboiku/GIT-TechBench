"""Tiny usage graph without QtCharts."""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class Sparkline(QWidget):
    def __init__(self, title: str = "", parent=None) -> None:
        super().__init__(parent)
        self.title = title
        self._values: deque[float] = deque(maxlen=80)
        self.setMinimumHeight(110)
        self._latest = 0.0

    def add(self, value: float) -> None:
        self._latest = max(0.0, min(100.0, float(value)))
        self._values.append(self._latest)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#151c27"))
        painter.setPen(QColor("#8b9bb0"))
        painter.drawText(10, 18, f"{self.title}  {self._latest:.0f}%")
        if len(self._values) < 2:
            painter.end()
            return
        width = max(1, self.width() - 16)
        height = max(1, self.height() - 32)
        step = width / max(1, self._values.maxlen - 1)
        points = []
        for i, value in enumerate(self._values):
            x = 8 + i * step
            y = 24 + (100 - value) / 100 * height
            points.append(QPointF(x, y))
        painter.setPen(QPen(QColor("#3d9cf0"), 2))
        for i in range(1, len(points)):
            painter.drawLine(points[i - 1], points[i])
        painter.end()
