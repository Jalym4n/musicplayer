"""The centre "deck": black screen with a holographic CD, the album cover and a cassette,
a scrolling LCD title, the transport buttons and the otter progress bar."""
from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QConicalGradient, QFontMetricsF, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QAbstractButton, QHBoxLayout, QLabel, QVBoxLayout,
                               QWidget)

from .. import theme
from ..models import fmt_ms
from ..theme import C
from .controls import HeartSlider
from .panels import SpeakerChip

HOLO = ["#ffd1f0", "#e2ccff", "#c9e9ff", "#d4ffe9", "#fff5c4", "#ffd6e6", "#ffd1f0"]


def heart_path(r: QRectF) -> QPainterPath:
    """A plump heart filling rect r."""
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    p = QPainterPath()
    p.moveTo(x + w / 2, y + h * 0.28)
    p.cubicTo(x + w * 0.5, y - h * 0.02, x + w * 0.02, y - h * 0.02, x + w * 0.02, y + h * 0.33)
    p.cubicTo(x + w * 0.02, y + h * 0.62, x + w * 0.3, y + h * 0.78, x + w / 2, y + h)
    p.cubicTo(x + w * 0.7, y + h * 0.78, x + w * 0.98, y + h * 0.62, x + w * 0.98, y + h * 0.33)
    p.cubicTo(x + w * 0.98, y - h * 0.02, x + w * 0.5, y - h * 0.02, x + w / 2, y + h * 0.28)
    return p


class Stage(QWidget):
    """The black "screen": music staff, spinning holographic CD, cover, cassette."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pix: QPixmap | None = None
        self._album = ""
        self._playing = False
        self._angle = 0.0
        self._t = 0
        rnd = random.Random(11)
        self._stars = [(rnd.random(), rnd.random(), rnd.choice((1, 1, 2)), rnd.random() * 6)
                       for _ in range(34)]
        self.setMinimumSize(460, 250)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def set_cover(self, pm: QPixmap | None):
        self._pix = pm
        self.update()

    def set_album(self, text: str):
        self._album = text
        self.update()

    def set_playing(self, on: bool):
        self._playing = on

    def _tick(self):
        self._t += 1
        if self._playing:
            self._angle = (self._angle + 2.4) % 360
        if self.isVisible() and (self._playing or self._t % 5 == 0):
            self.update()

    # -- painting -----------------------------------------------------------------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        w, h = r.width(), r.height()
        p.setPen(QPen(QColor(C.lav_mid), 4))
        p.setBrush(QColor(C.screen))
        p.drawRoundedRect(r, 18, 18)
        p.setPen(QPen(QColor(C.screen_edge), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(6, 6, -6, -6), 13, 13)
        p.save()
        clip = QPainterPath()
        clip.addRoundedRect(r.adjusted(4, 4, -4, -4), 15, 15)
        p.setClipPath(clip)
        self._twinkles(p, r)
        self._staff(p, QRectF(r.left() + 22, r.top() + 20, w * 0.30, 30), flip=False)
        self._staff(p, QRectF(r.right() - 22 - w * 0.26, r.top() + 20, w * 0.26, 30), flip=True)
        cd_r = min(h * 0.36, w * 0.19)
        self._cd(p, QPointF(r.left() + w * 0.21, r.top() + h * 0.60), cd_r)
        side = h * 0.56
        cover = QRectF(r.left() + w * 0.50 - side / 2, r.top() + h * 0.11, side, side)
        self._cover(p, cover)
        tx = cover.right() + 14
        p.setFont(theme.heading(15, True))
        p.setPen(QColor(C.lcd))
        p.drawText(QPointF(tx, cover.top() + side * 0.42), "Side A")
        p.drawText(QPointF(tx, cover.top() + side * 0.42 + 20), "Album ♡")
        theme.draw_icon(p, "note", C.pink_soft, tx + 70, cover.top() + side * 0.42 + 2, 1.8)
        cw, ch = w * 0.36, h * 0.40
        self._cassette(p, QRectF(r.right() - cw - 20, r.bottom() - ch - 16, cw, ch))
        p.restore()
        p.end()

    def _twinkles(self, p: QPainter, r: QRectF):
        p.setPen(Qt.PenStyle.NoPen)
        for fx, fy, size, phase in self._stars:
            a = int(70 + 70 * (1 + math.sin(self._t / 9 + phase)) / 2)
            c = QColor(C.lavender if size == 1 else C.pink_soft)
            c.setAlpha(a)
            p.setBrush(c)
            x, y = r.left() + fx * r.width(), r.top() + fy * r.height()
            p.drawRect(QRectF(x, y, size * 1.5, size * 1.5))

    def _staff(self, p: QPainter, box: QRectF, flip: bool):
        pen = QPen(QColor(C.shell))
        pen.setWidthF(1.4)
        p.setPen(pen)
        for i in range(5):
            y = box.top() + i * 6
            p.drawLine(QPointF(box.left(), y), QPointF(box.right(), y))
        colors = [C.shell, C.lavender, C.pink_soft, C.lav_mid]
        n = 4
        for i in range(n):
            x = box.left() + box.width() * (0.15 + 0.22 * i)
            bob = math.sin(self._t / 7 + i) * (3 if self._playing else 1)
            y = box.top() + 4 + (i % 3) * 5 + bob
            theme.draw_icon(p, "note", colors[(i + flip) % 4], x, y, 2.0)

    def _cd(self, p: QPainter, c: QPointF, rad: float):
        p.save()
        p.translate(c)
        p.rotate(self._angle)
        g = QConicalGradient(QPointF(0, 0), 0)
        for i, col in enumerate(HOLO):
            g.setColorAt(i / (len(HOLO) - 1), QColor(col))
        p.setPen(QPen(QColor("#f6f0ff"), 2))
        p.setBrush(g)
        p.drawEllipse(QPointF(0, 0), rad, rad)
        shine = QRadialGradient(QPointF(-rad * 0.3, -rad * 0.3), rad * 1.2)
        shine.setColorAt(0, QColor(255, 255, 255, 120))
        shine.setColorAt(0.5, QColor(255, 255, 255, 20))
        shine.setColorAt(1, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(shine)
        p.drawEllipse(QPointF(0, 0), rad, rad)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for k in (0.55, 0.7, 0.85):
            p.setPen(QPen(QColor(255, 255, 255, 60), 1))
            p.drawEllipse(QPointF(0, 0), rad * k, rad * k)
        p.setPen(QPen(QColor("#cfc4dc"), 2))
        p.setBrush(QColor("#ece6f3"))
        p.drawEllipse(QPointF(0, 0), rad * 0.30, rad * 0.30)
        p.setBrush(QColor(C.screen))
        p.drawEllipse(QPointF(0, 0), rad * 0.11, rad * 0.11)
        # stickers ride along with the disc
        p.save()
        p.translate(-rad * 0.55, -rad * 0.42)
        p.rotate(-18)
        p.setPen(QPen(QColor(C.white), 2))
        p.setBrush(QColor(C.shell))
        p.drawEllipse(QPointF(0, 0), rad * 0.2, rad * 0.17)
        theme.draw_icon(p, "heart", C.white, 0, 0, max(1.2, rad / 45))
        p.restore()
        p.save()
        p.translate(rad * 0.52, rad * 0.52)
        p.rotate(14)
        s = rad * 0.34
        p.setPen(QPen(QColor(C.lav_mid), 2))
        p.setBrush(QColor(C.butter))
        p.drawRoundedRect(QRectF(-s / 2, -s / 2, s, s), 6, 6)
        theme.draw_emoji(p, theme.OTTER, 0, 0, int(s * 0.62))
        p.restore()
        p.restore()

    def _cover(self, p: QPainter, cover: QRectF):
        frame = cover.adjusted(-7, -7, 7, 7)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 90))
        p.drawRoundedRect(frame.translated(4, 5), 10, 10)
        g = QLinearGradient(frame.topLeft(), frame.bottomRight())
        g.setColorAt(0, QColor(C.pink_soft))
        g.setColorAt(1, QColor(C.lavender))
        p.setBrush(g)
        p.setPen(QPen(QColor(C.white), 3))
        p.drawRoundedRect(frame, 10, 10)
        clip = QPainterPath()
        clip.addRoundedRect(cover, 6, 6)
        p.save()
        p.setClipPath(clip)
        if self._pix and not self._pix.isNull():
            p.drawPixmap(cover, self._pix, QRectF(self._pix.rect()))
        else:
            bg = QLinearGradient(cover.topLeft(), cover.bottomRight())
            bg.setColorAt(0, QColor("#ffd9ef"))
            bg.setColorAt(1, QColor("#e6d6ff"))
            p.fillRect(cover, bg)
            theme.draw_emoji(p, theme.OTTER, cover.center().x(), cover.center().y(),
                             int(cover.width() * 0.42))
        p.restore()

    def _cassette(self, p: QPainter, r: QRectF):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 100))
        p.drawRoundedRect(r.translated(4, 5), 10, 10)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor("#e9dcff"))
        g.setColorAt(1, QColor("#c7b0f7"))
        p.setBrush(g)
        p.setPen(QPen(QColor(C.lav_dark), 2.5))
        p.drawRoundedRect(r, 10, 10)
        # paper label
        label = QRectF(r.left() + r.width() * 0.07, r.top() + r.height() * 0.09,
                       r.width() * 0.86, r.height() * 0.24)
        p.setPen(QPen(QColor(C.lav_mid), 1.5))
        p.setBrush(QColor(C.cream))
        p.drawRoundedRect(label, 4, 4)
        f = theme.heading(max(9, int(r.height() * 0.11)), True)
        p.setFont(f)
        p.setPen(QColor(C.plum))
        text = (self._album or "mixtape for you").upper()
        text = QFontMetricsF(f).elidedText(text, Qt.TextElideMode.ElideRight,
                                           label.width() - 28)
        p.drawText(label.adjusted(14, 0, -14, 0), Qt.AlignmentFlag.AlignCenter, text)
        theme.draw_icon(p, "heart", C.shell, label.left() + 8, label.center().y(), 1.0)
        theme.draw_icon(p, "star", C.star, label.right() - 8, label.center().y(), 1.0)
        # window with reels
        win = QRectF(r.left() + r.width() * 0.2, r.top() + r.height() * 0.42,
                     r.width() * 0.6, r.height() * 0.27)
        p.setPen(QPen(QColor(C.lav_dark), 2))
        p.setBrush(QColor("#3b2c48"))
        p.drawRoundedRect(win, win.height() / 2, win.height() / 2)
        rr = win.height() * 0.36
        for cx in (win.left() + win.width() * 0.24, win.right() - win.width() * 0.24):
            p.save()
            p.translate(cx, win.center().y())
            p.rotate(self._angle * 1.6)
            p.setPen(QPen(QColor(C.lav_mid), 1.5))
            p.setBrush(QColor(C.white))
            p.drawEllipse(QPointF(0, 0), rr, rr)
            p.setPen(QPen(QColor(C.lav_dark), 2))
            for k in range(3):
                a = math.radians(k * 120)
                p.drawLine(QPointF(0, 0), QPointF(math.cos(a) * rr * 0.8, math.sin(a) * rr * 0.8))
            p.restore()
        p.setPen(QPen(QColor("#7a5a6e"), 3))
        p.drawLine(QPointF(win.left() + win.width() * 0.36, win.center().y() + rr * 0.6),
                   QPointF(win.right() - win.width() * 0.36, win.center().y() + rr * 0.6))
        # bottom tab with holes
        tab = QPainterPath()
        bl, br = r.left() + r.width() * 0.22, r.right() - r.width() * 0.22
        tab.moveTo(bl, r.bottom())
        tab.lineTo(bl + 10, r.bottom() - r.height() * 0.2)
        tab.lineTo(br - 10, r.bottom() - r.height() * 0.2)
        tab.lineTo(br, r.bottom())
        p.setPen(QPen(QColor(C.lav_dark), 2))
        p.setBrush(QColor("#dccbfb"))
        p.drawPath(tab)
        p.setBrush(QColor("#3b2c48"))
        p.setPen(Qt.PenStyle.NoPen)
        for k in range(4):
            x = bl + 16 + k * (br - bl - 32) / 3
            p.drawEllipse(QPointF(x, r.bottom() - r.height() * 0.09), 2.6, 2.6)


class LcdMarquee(QWidget):
    """Black LCD strip: ☆ ARTIST - TITLE (YEAR) ☆, scrolling when it doesn't fit."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        self._off = 0.0
        self._pause = 50
        self._font = theme.body(30)
        self.setFixedHeight(44)
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(35)

    def setText(self, text: str):
        if text != self._text:
            self._text, self._off, self._pause = text, 0.0, 50
            self.update()

    def text(self) -> str:
        return self._text

    def _area(self) -> QRectF:
        return QRectF(self.rect()).adjusted(44, 4, -44, -4)

    def _tw(self) -> float:
        return QFontMetricsF(self._font).horizontalAdvance(self._text)

    def _tick(self):
        if not self.isVisible() or self._tw() <= self._area().width():
            return
        if self._pause > 0:
            self._pause -= 1
            return
        self._off += 1.2
        if self._off > self._tw() + 60:
            self._off, self._pause = 0.0, 50
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        p.setPen(QPen(QColor(C.lav_mid), 3))
        p.setBrush(QColor(C.screen))
        p.drawRoundedRect(r, 10, 10)
        for x in (r.left() + 22, r.right() - 22):
            theme.draw_icon(p, "star", C.butter, x, r.center().y(), 1.9)
        a = self._area()
        p.setClipRect(a)
        p.setFont(self._font)
        tw = self._tw()
        glow = QColor(C.lavender)
        glow.setAlpha(90)
        def draw(x: float):
            p.setPen(glow)
            p.drawText(QRectF(x + 1, a.top() + 1, tw + 4, a.height()),
                       Qt.AlignmentFlag.AlignVCenter, self._text)
            p.setPen(QColor(C.lcd))
            p.drawText(QRectF(x, a.top(), tw + 4, a.height()),
                       Qt.AlignmentFlag.AlignVCenter, self._text)
        if tw <= a.width():
            draw(a.left() + (a.width() - tw) / 2)
        else:
            draw(a.left() - self._off)
            draw(a.left() - self._off + tw + 60)
        p.end()


class HeartButton(QAbstractButton):
    """The big glossy holographic heart: play / pause."""

    def __init__(self, size: int = 104, parent=None):
        super().__init__(parent)
        self.playing = False
        self._hover = False
        self.setFixedSize(size, int(size * 0.92))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Play / pause (Space)")

    def set_playing(self, on: bool):
        self.playing = on
        self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        down = 3 if self.isDown() else 0
        r = QRectF(self.rect()).adjusted(6, 6 + down, -6, -8 + down)
        if not down:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C.lav_dark))
            p.drawPath(heart_path(r.translated(0, 5)))
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor("#ffc4e6" if not self._hover else "#ffd6ee"))
        g.setColorAt(0.5, QColor("#f1b6f0"))
        g.setColorAt(1, QColor("#c9b0ff"))
        p.setBrush(g)
        p.setPen(QPen(QColor(C.white), 4))
        p.drawPath(heart_path(r))
        p.setPen(QPen(QColor(C.hot), 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(heart_path(r.adjusted(-3, -3, 3, 3)))
        # glitter + shine
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 170))
        p.drawEllipse(QRectF(r.left() + r.width() * 0.17, r.top() + r.height() * 0.14,
                             r.width() * 0.2, r.height() * 0.13))
        rnd = random.Random(5)
        for _ in range(9):
            p.setBrush(QColor(255, 255, 255, rnd.randint(90, 200)))
            p.drawEllipse(QPointF(r.left() + r.width() * rnd.uniform(0.25, 0.75),
                                  r.top() + r.height() * rnd.uniform(0.25, 0.7)), 1.3, 1.3)
        icon = "pause" if self.playing else "play"
        cx, cy = r.center().x() + (0 if self.playing else 2), r.top() + r.height() * 0.46
        theme.draw_icon(p, icon, C.hot, cx + 1, cy + 2, 3.2)
        theme.draw_icon(p, icon, C.white, cx, cy, 3.2)
        p.end()


class CandyButton(QAbstractButton):
    """Rounded square pink button (previous / next)."""

    def __init__(self, icon: str, tooltip: str = "", parent=None):
        super().__init__(parent)
        self.icon_name = icon
        self.setFixedSize(64, 54)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        down = 3 if self.isDown() else 0
        r = QRectF(self.rect()).adjusted(4, 3 + down, -4, -7 + down)
        if not down:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C.shell_dark))
            p.drawRoundedRect(r.translated(0, 4), 10, 10)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor("#ffd3ea"))
        g.setColorAt(1, QColor("#ffa9d3"))
        p.setBrush(g)
        p.setPen(QPen(QColor(C.white), 3))
        p.drawRoundedRect(r, 10, 10)
        p.setPen(QPen(QColor(C.hot), 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(-2, -2, 2, 2), 11, 11)
        theme.draw_icon(p, self.icon_name, C.hot, r.center().x(), r.center().y() + 1, 2.6)
        theme.draw_icon(p, self.icon_name, C.white, r.center().x() - 1, r.center().y(), 2.6)
        p.end()


class LabelButton(QAbstractButton):
    """Small icon with a label underneath (Shuffle / Repeat). Glows when on."""

    def __init__(self, icon: str, label: str, color: str = C.lav_dark, parent=None):
        super().__init__(parent)
        self.icon_name, self.label, self.color = icon, label, color
        self.badge = ""
        self.setCheckable(True)
        self.setFixedSize(76, 62)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        cx = self.width() / 2
        if on:
            glow = QRadialGradient(QPointF(cx, 20), 24)
            glow.setColorAt(0, QColor(255, 158, 199, 150))
            glow.setColorAt(1, QColor(255, 158, 199, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(QPointF(cx, 20), 24, 24)
        col = C.hot if on else self.color
        theme.draw_icon(p, self.icon_name, col, cx, 20, 2.6, C.butter)
        if self.badge:
            p.setBrush(QColor(C.butter))
            p.setPen(QPen(QColor(C.hot), 1.5))
            p.drawEllipse(QPointF(cx + 17, 9), 7, 7)
            p.setFont(theme.heading(10, True))
            p.setPen(QColor(C.plum))
            p.drawText(QRectF(cx + 10, 2, 14, 14), Qt.AlignmentFlag.AlignCenter, self.badge)
        p.setFont(theme.heading(14, True))
        p.setPen(QColor(C.hot if on else C.plum))
        p.drawText(QRectF(0, 36, self.width(), 22), Qt.AlignmentFlag.AlignCenter, self.label)
        p.end()


class OtterSlider(HeartSlider):
    """Progress bar where the otter swims along, trailing sparkles."""

    def __init__(self, maximum: int = 1000, parent=None):
        super().__init__(maximum, 34, parent)

    def _bar(self) -> QRectF:
        return QRectF(16, (self.height() - 14) / 2, self.width() - 32, 14)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        b = self._bar()
        p.setPen(QPen(QColor(C.white), 3))
        p.setBrush(QColor("#ead9ff"))
        p.drawRoundedRect(b, 7, 7)
        frac = self.value() / max(1, self._max)
        if frac > 0:
            fill = QRectF(b.left(), b.top(), b.width() * frac, b.height())
            g = QLinearGradient(fill.topLeft(), fill.topRight())
            g.setColorAt(0, QColor("#ffc4e6"))
            g.setColorAt(1, QColor("#d7b8ff"))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawRoundedRect(fill.adjusted(2, 2, -1, -2), 5, 5)
            # sparkle trail
            for k, dx in enumerate((18, 34, 50)):
                x = fill.right() - dx
                if x > b.left() + 6:
                    theme.draw_icon(p, "sparkle", C.white if k % 2 else C.butter,
                                    x, b.center().y() - 1, 0.9)
        p.setPen(QPen(QColor(C.lav_mid), 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(b.adjusted(-2, -2, 2, 2), 8, 8)
        cx = b.left() + b.width() * frac
        theme.draw_emoji(p, theme.OTTER, cx, b.center().y() - 2, 26)
        p.end()


class TimeBox(QLabel):
    def __init__(self, parent=None):
        super().__init__("0:00", parent)
        self.setFont(theme.body(24))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(68, 34)
        self.setStyleSheet(f"background:{C.screen}; color:{C.lcd}; border-radius: 8px;"
                           f"border: 2px solid {C.lav_mid};")


class Deck(QWidget):
    """Everything in the centre column. Same API the main window drives."""
    playPause = Signal()
    nextClicked = Signal()
    prevClicked = Signal()
    shuffleToggled = Signal(bool)
    repeatClicked = Signal()
    seekTo = Signal(int)
    volumeTo = Signal(int)
    speakerClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 10)
        lay.setSpacing(8)
        self.stage = Stage()
        lay.addWidget(self.stage, 1)
        self.lcd = LcdMarquee()
        lay.addWidget(self.lcd)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.b_shuffle = LabelButton("shuffle", "Shuffle")
        self.b_prev = CandyButton("rewind", "Previous (Ctrl+Left)")
        self.b_play = HeartButton()
        self.b_next = CandyButton("ffwd", "Next (Ctrl+Right)")
        self.b_repeat = LabelButton("flower", "Repeat", C.shell_dark)
        row.addStretch(1)
        for wdg in (self.b_shuffle, self.b_prev, self.b_play, self.b_next, self.b_repeat):
            row.addWidget(wdg, 0, Qt.AlignmentFlag.AlignVCenter)
            if wdg in (self.b_shuffle, self.b_next):
                row.addSpacing(10)
        row.addStretch(1)
        lay.addLayout(row)
        self.b_play.clicked.connect(self.playPause)
        self.b_prev.clicked.connect(self.prevClicked)
        self.b_next.clicked.connect(self.nextClicked)
        self.b_shuffle.clicked.connect(lambda: self.shuffleToggled.emit(self.b_shuffle.isChecked()))
        self.b_repeat.clicked.connect(self.repeatClicked)

        trow = QHBoxLayout()
        self.t_pos, self.t_len = TimeBox(), TimeBox()
        self.progress = OtterSlider()
        self.progress.released.connect(self.seekTo)
        self.progress.moved.connect(lambda v: self.t_pos.setText(fmt_ms(v)))
        trow.addWidget(self.t_pos)
        trow.addWidget(self.progress, 1)
        trow.addWidget(self.t_len)
        lay.addLayout(trow)

        brow = QHBoxLayout()
        brow.setSpacing(8)
        spk_icon = QLabel()
        spk_icon.setPixmap(theme.pixmap("speaker", C.lav_dark, 2))
        self.volume = HeartSlider(100, 24)
        self.volume.setMaximumWidth(190)
        self.volume.released.connect(self.volumeTo)
        self.speaker = SpeakerChip()
        self.speaker.clicked.connect(self.speakerClicked)
        brow.addWidget(spk_icon)
        brow.addWidget(self.volume, 1)
        brow.addWidget(self.speaker, 2)
        lay.addLayout(brow)
        self._repeat = "off"
        self.set_track("", "", 0, None)

    # --- API used by the main window ------------------------------------------------
    def set_track(self, title: str, artist: str, duration_ms: int, pixmap,
                  album: str = "", year: str = ""):
        if title:
            yr = f" ({year})" if year else ""
            self.lcd.setText(f"{artist.upper()} - {title.upper()}{yr}")
        else:
            self.lcd.setText("PICK A SONG, CUTIE ♡")
        self.stage.set_album(album)
        self.stage.set_cover(pixmap)
        self.progress.set_maximum(max(1, duration_ms))
        self.t_len.setText(fmt_ms(duration_ms))

    def set_cover(self, pm):
        self.stage.set_cover(pm)

    def set_progress(self, ms: int):
        if not self.progress.dragging:
            self.progress.set_value(ms)
            self.t_pos.setText(fmt_ms(ms))

    def set_playing(self, on: bool):
        self.b_play.set_playing(on)
        self.stage.set_playing(on)

    def set_shuffle(self, on: bool):
        self.b_shuffle.setChecked(on)

    def set_repeat(self, mode: str):
        self._repeat = mode
        self.b_repeat.setChecked(mode != "off")
        self.b_repeat.badge = "1" if mode == "track" else ""
        self.b_repeat.setToolTip({"off": "Repeat: off", "context": "Repeat: all",
                                  "track": "Repeat: this song"}.get(mode, "Repeat"))
        self.b_repeat.update()

    @property
    def repeat_mode(self) -> str:
        return self._repeat

    def set_volume(self, v):
        self.volume.setEnabled(v is not None)
        if v is not None and not self.volume.dragging:
            self.volume.set_value(v)

    def set_speaker(self, phase: str, detail: str):
        self.speaker.set_status(phase, detail)

    @property
    def speaker_phase(self) -> str:
        return self.speaker.phase

    def sizeHint(self):
        return QSize(640, 620)
