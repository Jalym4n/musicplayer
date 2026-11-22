"""Small hand-painted widgets: pixel buttons, heart sliders, scrolling titles."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractButton, QWidget

from .. import theme
from ..theme import C


class PixelButton(QAbstractButton):
    """Round candy button with a pixel icon. `checkable` buttons glow when on."""

    def __init__(self, icon_name: str, diameter: int = 40, px: float = 2.5,
                 fill: str = C.white, ink: str = C.hot, tooltip: str = "", parent=None):
        super().__init__(parent)
        self.icon_name, self.d, self.px = icon_name, diameter, px
        self.fill, self.ink = fill, ink
        self.badge = ""
        self._hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(diameter + 6, diameter + 8)
        if tooltip:
            self.setToolTip(tooltip)

    def set_icon(self, name: str):
        self.icon_name = name
        self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def sizeHint(self):
        return QSize(self.d + 6, self.d + 8)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        down = self.isDown()
        on = self.isCheckable() and self.isChecked()
        x, y = 3, 2 + (3 if down else 0)
        r = QRectF(x, y, self.d, self.d)
        # chunky retro drop shadow
        if not down:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C.shell_dark))
            p.drawEllipse(r.translated(0, 4))
        fill = QColor(self.ink if on else self.fill)
        if self._hover and not on:
            fill = QColor(C.cream)
        p.setBrush(fill)
        p.setPen(QPen(QColor(self.ink), 3))
        p.drawEllipse(r)
        # tiny shine
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 170))
        p.drawEllipse(QRectF(r.x() + self.d * .2, r.y() + self.d * .14, self.d * .18, self.d * .12))
        ink = C.white if on else self.ink
        if not self.isEnabled():
            ink = C.plum_soft
        theme.draw_icon(p, self.icon_name, ink, r.center().x(), r.center().y(), self.px)
        if self.badge:
            p.setFont(theme.heading(10, True))
            br = QRectF(r.right() - 14, r.top() - 2, 16, 16)
            p.setBrush(QColor(C.butter))
            p.setPen(QPen(QColor(self.ink), 2))
            p.drawEllipse(br)
            p.setPen(QColor(C.plum))
            p.drawText(br, Qt.AlignmentFlag.AlignCenter, self.badge)
        p.end()


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


def gingham(p: QPainter, rect: QRectF, cell: int = 18, base: str = C.bg,
            band: str = C.gingham, cross: str = C.gingham_dark) -> None:
    """Paint a soft pink gingham tablecloth pattern."""
    p.fillRect(rect, QColor(base))
    p.setPen(Qt.PenStyle.NoPen)
    b1, b2 = QColor(band), QColor(cross)
    b1.setAlpha(150)
    b2.setAlpha(110)
    x = rect.left()
    while x < rect.right():
        p.fillRect(QRectF(x, rect.top(), cell, rect.height()), b1)
        x += cell * 2
    y = rect.top()
    while y < rect.bottom():
        p.fillRect(QRectF(rect.left(), y, rect.width(), cell), b1)
        y += cell * 2
    x = rect.left()
    while x < rect.right():
        y = rect.top()
        while y < rect.bottom():
            p.fillRect(QRectF(x, y, cell, cell), b2)
            y += cell * 2
        x += cell * 2


def rounded_path(r: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(r, radius, radius)
    return path
