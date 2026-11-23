"""Small hand-painted widgets: heart sliders and scrolling titles."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .. import theme
from ..theme import C


class HeartSlider(QWidget):
    """Pill-shaped bar with a heart knob. Emits `released(value)` when you let go."""
    moved = Signal(int)
    released = Signal(int)

    def __init__(self, maximum: int = 100, height: int = 26, parent=None):
        super().__init__(parent)
        self._max = max(1, maximum)
        self._val = 0
        self._drag = False
        self.setFixedHeight(height)
        self.setMinimumWidth(80)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @property
    def dragging(self) -> bool:
        return self._drag

    def set_maximum(self, m: int):
        self._max = max(1, int(m))
        self.update()

    def set_value(self, v: int):
        if not self._drag:
            self._val = max(0, min(self._max, int(v)))
            self.update()

    def value(self) -> int:
        return self._val

    def _bar(self) -> QRectF:
        h = 12
        return QRectF(12, (self.height() - h) / 2, self.width() - 24, h)

    def _from_x(self, x: float) -> int:
        b = self._bar()
        frac = (x - b.left()) / max(1.0, b.width())
        return int(max(0.0, min(1.0, frac)) * self._max)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = True
            self._val = self._from_x(e.position().x())
            self.moved.emit(self._val)
            self.update()

    def mouseMoveEvent(self, e):
        if self._drag:
            self._val = self._from_x(e.position().x())
            self.moved.emit(self._val)
            self.update()

    def mouseReleaseEvent(self, e):
        if self._drag:
            self._drag = False
            self.released.emit(self._val)
            self.update()

    def wheelEvent(self, e):
        step = self._max // 20 or 1
        self._val = max(0, min(self._max, self._val + (step if e.angleDelta().y() > 0 else -step)))
        self.update()
        self.released.emit(self._val)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        b = self._bar()
        p.setPen(QPen(QColor(C.hot), 2))
        p.setBrush(QColor(C.white))
        p.drawRoundedRect(b, 6, 6)
        frac = self._val / self._max
        if frac > 0:
            fill = QRectF(b.left(), b.top(), b.width() * frac, b.height())
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C.shell))
            p.drawRoundedRect(fill.adjusted(2, 2, 0, -2), 4, 4)
            # candy stripes
            p.setClipRect(fill.adjusted(2, 2, 0, -2))
            p.setPen(QPen(QColor(255, 255, 255, 110), 3))
            x = b.left() - b.height()
            while x < fill.right():
                p.drawLine(QPointF(x, b.bottom()), QPointF(x + b.height(), b.top()))
                x += 9
            p.setClipping(False)
        cx = b.left() + b.width() * frac
        cy = self.height() / 2
        theme.draw_icon(p, "heart", C.shell_dark, cx, cy + 2, 2.4)
        theme.draw_icon(p, "heart", C.hot, cx, cy, 2.4)
        p.end()


class MarqueeLabel(QWidget):
    """Single-line label that gently scrolls when the text is too long."""

    def __init__(self, font, color: str = C.plum, parent=None):
        super().__init__(parent)
        self._text = ""
        self._font = font
        self._color = color
        self._offset = 0.0
        self._pause = 40
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)
        self.setFixedHeight(QFontMetrics(font).height() + 4)

    def setText(self, text: str):
        if text != self._text:
            self._text = text
            self._offset = 0
            self._pause = 40
            self.update()

    def text(self) -> str:
        return self._text

    def _text_w(self) -> int:
        return QFontMetrics(self._font).horizontalAdvance(self._text)

    def _tick(self):
        if self._text_w() <= self.width() or not self.isVisible():
            return
        if self._pause > 0:
            self._pause -= 1
            return
        self._offset += 1.0
        if self._offset > self._text_w() + 40:
            self._offset = 0
            self._pause = 40
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setFont(self._font)
        p.setPen(QColor(self._color))
        tw = self._text_w()
        if tw <= self.width():
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)
        else:
            r = self.rect()
            p.drawText(QRectF(-self._offset, 0, tw, r.height()),
                       Qt.AlignmentFlag.AlignVCenter, self._text)
            p.drawText(QRectF(-self._offset + tw + 40, 0, tw, r.height()),
                       Qt.AlignmentFlag.AlignVCenter, self._text)
        p.end()
