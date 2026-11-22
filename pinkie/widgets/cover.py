"""Now-playing album art: a polaroid-style sleeve with a vinyl that spins while playing."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

from .. import theme
from ..theme import C


class VinylCover(QWidget):
    def __init__(self, size: int = 220, parent=None):
        super().__init__(parent)
        self.side = size
        self._pix: QPixmap | None = None
        self._angle = 0.0
        self._slide = 0.0          # 0 = record tucked in, 1 = peeking out
        self._playing = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)
        self.setFixedSize(int(size * 1.36), size + 26)

    def set_pixmap(self, pm: QPixmap | None):
        self._pix = pm
        self.update()

    def set_playing(self, playing: bool):
        self._playing = playing

    def _tick(self):
        target = 1.0 if self._playing else 0.35
        changed = abs(self._slide - target) > 0.002
        self._slide += (target - self._slide) * 0.12
        if self._playing:
            self._angle = (self._angle + 2.2) % 360
            changed = True
        if changed and self.isVisible():
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        s = self.side
        sleeve = QRectF(8, 8, s, s)
        # --- vinyl, behind the sleeve ---
        vr = s * 0.47
        cx = sleeve.center().x() + s * 0.36 * self._slide
        cy = sleeve.center().y()
        p.save()
        p.translate(cx, cy)
        p.rotate(self._angle)
        g = QRadialGradient(QPointF(0, 0), vr)
        g.setColorAt(0, QColor("#4a3247"))
        g.setColorAt(1, QColor(C.vinyl))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(0, 0), vr, vr)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(5):
            p.setPen(QPen(QColor(255, 255, 255, 22 + i * 4), 1))
            rr = vr * (0.55 + i * 0.09)
            p.drawEllipse(QPointF(0, 0), rr, rr)
        # glint so the spin is visible
        p.setPen(QPen(QColor(255, 255, 255, 60), 3))
        p.drawArc(QRectF(-vr * .8, -vr * .8, vr * 1.6, vr * 1.6), 30 * 16, 40 * 16)
        # label = the album cover in a circle
        lr = vr * 0.36
        p.setPen(Qt.PenStyle.NoPen)
        if self._pix and not self._pix.isNull():
            clip = QPainterPath()
            clip.addEllipse(QPointF(0, 0), lr, lr)
            p.setClipPath(clip)
            p.drawPixmap(QRectF(-lr, -lr, lr * 2, lr * 2), self._pix,
                         QRectF(self._pix.rect()))
            p.setClipping(False)
        else:
            p.setBrush(QColor(C.shell))
            p.drawEllipse(QPointF(0, 0), lr, lr)
        p.setBrush(QColor(C.cream))
        p.drawEllipse(QPointF(0, 0), 4, 4)
        p.restore()

        # --- polaroid sleeve ---
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C.shell_dark))
        p.drawRoundedRect(sleeve.translated(5, 6), 14, 14)
        p.setBrush(QColor(C.white))
        p.setPen(QPen(QColor(C.hot), 3))
        p.drawRoundedRect(sleeve, 14, 14)
        art = sleeve.adjusted(10, 10, -10, -10)
        clip = QPainterPath()
        clip.addRoundedRect(art, 8, 8)
        p.save()
        p.setClipPath(clip)
        if self._pix and not self._pix.isNull():
            p.drawPixmap(art, self._pix, QRectF(self._pix.rect()))
        else:
            p.fillRect(art, QColor(C.cream))
            theme.draw_icon(p, "note", C.shell, art.center().x(), art.center().y(), s / 30)
        p.restore()
        # washi tape + sticker
        p.save()
        p.translate(sleeve.left() + 26, sleeve.top() + 2)
        p.rotate(-28)
        p.setPen(Qt.PenStyle.NoPen)
        tape = QColor(C.lavender)
        tape.setAlpha(210)
        p.setBrush(tape)
        p.drawRect(QRectF(-26, -9, 52, 18))
        p.restore()
        theme.draw_icon(p, "heart", C.white, sleeve.right() - 18, sleeve.bottom() - 16, 3.2)
        theme.draw_icon(p, "heart", C.hot, sleeve.right() - 18, sleeve.bottom() - 18, 2.6)
        p.end()
