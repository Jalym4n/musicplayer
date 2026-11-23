"""Right column: a cream notebook with UP NEXT / SONGS pages, and the heartbeat screen."""
from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractButton, QHBoxLayout, QLabel, QStackedWidget,
                               QVBoxLayout, QWidget)

from .. import theme
from ..images import ImageLoader
from ..theme import C
from .panels import PlaylistHeader
from .tracklist import TrackList


class TabSticker(QAbstractButton):
    """Outlined sticker-text tab ("UP NEXT" / "SONGS")."""

    def __init__(self, text: str, icon: str, parent=None):
        super().__init__(parent)
        self.text_, self.icon_name = text, icon
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        f = theme.heading(20, True)
        from PySide6.QtGui import QFontMetrics
        self.setFixedWidth(QFontMetrics(f).horizontalAdvance(text) + 52)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        theme.draw_icon(p, self.icon_name, C.lav_dark if on else "#cbbdf0", 16,
                        self.height() / 2, 1.9)
        fill = "#b08cff" if on else "#d9cbfa"
        theme.draw_outlined(p, self.text_, 34, self.height() / 2 + 8, theme.heading(20, True),
                            fill, C.white, shadow="#6f4fc4" if on else "#b9a7ea", width=5)
        p.end()


class Notebook(QWidget):
    """Cream lined paper with two pages: the queue and the selected playlist's songs."""
    upNextPlay = Signal(int)

    def __init__(self, images: ImageLoader, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(330)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 10, 12)
        lay.setSpacing(2)
        tabs = QHBoxLayout()
        tabs.setSpacing(0)
        self.tab_next = TabSticker("UP NEXT", "bubble")
        self.tab_songs = TabSticker("SONGS", "note")
        self.tab_next.setChecked(True)
        tabs.addWidget(self.tab_next)
        tabs.addWidget(self.tab_songs)
        tabs.addStretch(1)
        lay.addLayout(tabs)
        self.pages = QStackedWidget()
        lay.addWidget(self.pages, 1)

        # page 0: up next
        p0 = QWidget()
        l0 = QVBoxLayout(p0)
        l0.setContentsMargins(0, 0, 0, 0)
        self.upnext = TrackList(images)
        self.upnext.playRequested.connect(self.upNextPlay)
        self.upnext_empty = _empty("nothing queued yet\npick a song, cutie ♡")
        l0.addWidget(self.upnext, 1)
        l0.addWidget(self.upnext_empty, 1)
        self.pages.addWidget(p0)

        # page 1: songs of the selected playlist
        p1 = QWidget()
        l1 = QVBoxLayout(p1)
        l1.setContentsMargins(0, 0, 0, 0)
        l1.setSpacing(0)
        self.header = PlaylistHeader(images)
        self.tracks = TrackList(images)
        self.empty = _empty("")
        l1.addWidget(self.header)
        l1.addWidget(self.tracks, 1)
        l1.addWidget(self.empty, 1)
        self.empty.hide()
        self.pages.addWidget(p1)

        self.tab_next.clicked.connect(lambda: self.show_page(0))
        self.tab_songs.clicked.connect(lambda: self.show_page(1))
        self.set_upnext([])

    def show_page(self, i: int):
        self.pages.setCurrentIndex(i)
        (self.tab_next if i == 0 else self.tab_songs).setChecked(True)

    def set_upnext(self, tracks):
        self.upnext.tmodel.set_tracks(tracks)
        self.upnext.setVisible(bool(tracks))
        self.upnext_empty.setVisible(not tracks)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        p.setPen(QPen(QColor(C.lav_mid), 3))
        p.setBrush(QColor(C.cream))
        p.drawRoundedRect(r, 14, 14)
        p.setPen(QPen(QColor(C.white), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(4, 4, -4, -4), 10, 10)
        # notebook rings along the top
        for i in range(6):
            x = r.left() + 30 + i * (r.width() - 60) / 5
            p.setPen(QPen(QColor(C.lav_mid), 2))
            p.setBrush(QColor(C.white))
            p.drawEllipse(QPointF(x, r.top() + 2), 4, 4)
        p.end()


def _empty(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lab.setWordWrap(True)
    lab.setFont(theme.body(22))
    lab.setStyleSheet(f"color:{C.plum_soft}; padding: 20px;")
    return lab


class Heartbeat(QWidget):
    """Black screen with a pink heartbeat line and floating hearts while music plays.

    (Spotify no longer shares audio analysis with apps, so this is a cute animation
    rather than a real spectrum.)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(86)
        self._playing = False
        self._t = 0
        self._pts = [0.0] * 120
        self._hearts: list[list[float]] = []
        rnd = random.Random(2)
        self._stars = [(rnd.random(), rnd.random()) for _ in range(14)]
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(45)

    def set_playing(self, on: bool):
        self._playing = on

    def _tick(self):
        self._t += 1
        beat = self._t % 22
        if self._playing:
            shape = {0: 0.2, 1: -0.5, 2: 1.0, 3: -0.8, 4: 0.35, 5: 0.0}
            v = shape.get(beat, random.uniform(-0.05, 0.05))
            v *= random.uniform(0.75, 1.1)
            if beat == 2 and random.random() < 0.7:
                self._hearts.append([1.0, random.uniform(0.25, 0.75), 1.0])
        else:
            v = 0.0 if beat else 0.08
        self._pts = self._pts[1:] + [v]
        for h in self._hearts:
            h[0] -= 0.012
            h[2] -= 0.015
        self._hearts = [h for h in self._hearts if h[2] > 0 and h[0] > 0]
        if self.isVisible():
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        p.setPen(QPen(QColor(C.lav_mid), 3))
        p.setBrush(QColor(C.screen))
        p.drawRoundedRect(r, 12, 12)
        for i, (fx, fy) in enumerate(self._stars):
            a = 0.35 + 0.35 * math.sin(self._t / 8 + i)
            c = QColor(C.white)
            c.setAlphaF(max(0.05, a))
            theme.draw_icon(p, "sparkle", c.name(QColor.NameFormat.HexArgb),
                            r.left() + 10 + fx * (r.width() - 20),
                            r.top() + 8 + fy * (r.height() - 16), 0.8)
        mid = r.center().y() + 4
        amp = r.height() * 0.34
        path = QPainterPath()
        n = len(self._pts)
        for i, v in enumerate(self._pts):
            x = r.left() + 8 + i * (r.width() - 16) / (n - 1)
            y = mid - v * amp
            path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
        glow = QColor(C.shell)
        glow.setAlpha(80)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(glow, 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)
        p.setPen(QPen(QColor("#ff8cc6"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)
        for fx, fy, a in self._hearts:
            c = QColor(C.shell)
            c.setAlphaF(max(0.0, min(1.0, a)))
            theme.draw_icon(p, "heart", c.name(QColor.NameFormat.HexArgb),
                            r.left() + fx * r.width(), r.top() + fy * r.height(), 1.3)
        for i, x in enumerate((r.left() + 22, r.right() - 22)):
            theme.draw_icon(p, "heart", C.hot if i else C.shell, x, r.bottom() - 16, 1.6)
        p.end()
