"""Title bar, speaker status pill and the compact playlist header."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractButton, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from .. import theme
from ..images import ImageLoader
from ..models import Playlist
from ..theme import C


class RetroButton(QAbstractButton):
    """Tiny square window button, old-school desktop style but pastel."""

    def __init__(self, icon: str, tooltip: str, fill: str = C.white, size: int = 26,
                 px: float = 2.0, parent=None):
        super().__init__(parent)
        self.icon_name, self.fill, self.px = icon, fill, px
        self.setFixedSize(size, size)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        d = 2 if self.isDown() else 0
        r = QRectF(self.rect()).adjusted(2, 2 + d, -2, -3 + d)
        if not d:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C.lav_dark))
            p.drawRoundedRect(r.translated(0, 2), 6, 6)
        p.setBrush(QColor(C.pink_soft if self._hover else self.fill))
        p.setPen(QPen(QColor(C.lav_dark), 1.8))
        p.drawRoundedRect(r, 6, 6)
        theme.draw_icon(p, self.icon_name, C.plum, r.center().x(), r.center().y(), self.px)
        p.end()


class TitleBar(QWidget):
    """Draggable title strip: candies + star, the personalised title, window buttons."""
    settingsClicked = Signal()
    miniClicked = Signal()

    def __init__(self, window, title: str, parent=None):
        super().__init__(parent)
        self.win = window
        self.title = title
        self.setFixedHeight(52)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 14, 4)
        lay.setSpacing(6)
        lay.addStretch(1)
        self.btn_mini = RetroButton("mini", "Mini-player (Ctrl+M)", C.butter, px=1.8)
        self.btn_settings = RetroButton("gear", "Settings", C.white, px=1.6)
        self.btn_min = RetroButton("minus", "Minimize", C.mint)
        self.btn_close = RetroButton("close", "Close", C.pink_soft)
        for b in (self.btn_mini, self.btn_settings, self.btn_min, self.btn_close):
            lay.addWidget(b)
        self.btn_mini.clicked.connect(self.miniClicked)
        self.btn_settings.clicked.connect(self.settingsClicked)
        self.btn_min.clicked.connect(window.showMinimized)
        self.btn_close.clicked.connect(window.close)
        self._drag = None
        self._t = 0
        t = QTimer(self)
        t.timeout.connect(self._twinkle)
        t.start(700)

    def set_title(self, title: str):
        self.title = title
        self.update()

    def _twinkle(self):
        self._t += 1
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cy = self.height() / 2 + 2
        theme.draw_icon(p, "candy", C.lav_dark, 35, cy + 1, 2.4, C.lav_dark)
        theme.draw_icon(p, "candy", C.hot, 34, cy, 2.4, C.white)
        theme.draw_icon(p, "candy", C.lav_dark, 77, cy + 1, 2.4, C.lav_dark)
        theme.draw_icon(p, "candy", C.lav_mid, 76, cy, 2.4, C.white)
        theme.draw_icon(p, "star", "#e0a800", 113, cy + 1, 2.6)
        theme.draw_icon(p, "star", C.star, 112, cy, 2.6)
        f = theme.heading(23, True)
        tw = QFontMetrics(f).horizontalAdvance(self.title)
        emoji_w = 34
        total = tw + emoji_w * 2 + 30
        x = (self.width() - total) / 2
        bounce = (self._t % 2) * 2
        theme.draw_emoji(p, theme.SPARKLES, x + 12, cy - bounce, 20)
        theme.draw_outlined(p, self.title, x + emoji_w, cy + 8, f, C.plum, C.white,
                            shadow=C.lav_mid, width=5)
        theme.draw_emoji(p, theme.OTTER, x + emoji_w + tw + 20, cy, 22)
        theme.draw_emoji(p, theme.SPARKLES, x + emoji_w + tw + 50, cy - (2 - bounce), 20)
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            handle = self.win.windowHandle()
            if handle and handle.startSystemMove():
                return
            self._drag = e.globalPosition().toPoint() - self.win.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.win.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None

    def mouseDoubleClickEvent(self, e):
        self.win.showNormal() if self.win.isMaximized() else self.win.showMaximized()


class SpeakerChip(QWidget):
    """Status pill for the built-in speaker: a blinking light plus a short message."""
    clicked = Signal()
    COLORS = {"ready": C.mint, "starting": C.butter, "login": C.lavender, "pair": C.lavender,
              "elsewhere": C.butter, "error": C.hot, "missing": C.hot,
              "off": C.plum_soft}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.phase, self.detail = "starting", "warming up the speaker"
        self._blink = True
        self.setFixedHeight(48)
        self.setMinimumWidth(180)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(500)

    def set_status(self, phase: str, detail: str):
        self.phase, self.detail = phase, detail or self.detail
        self.setToolTip(self.detail)
        self.update()

    def _tick(self):
        if self.phase in ("starting", "login", "pair", "elsewhere"):
            self._blink = not self._blink
            self.update()
        elif not self._blink:
            self._blink = True
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        p.setPen(QPen(QColor(C.lav_mid), 2.5))
        p.setBrush(QColor(255, 255, 255, 215))
        p.drawRoundedRect(r, 14, 14)
        light = QColor(self.COLORS.get(self.phase, C.butter))
        if not self._blink:
            light.setAlpha(60)
        p.setBrush(light)
        p.setPen(QPen(QColor(C.plum), 1.5))
        p.drawEllipse(QPointF(r.left() + 16, r.center().y()), 6, 6)
        title = {"ready": "playing on this computer", "elsewhere": "playing elsewhere",
                 "login": "speaker login", "pair": "pair once from your phone",
                 "missing": "speaker setup needed",
                 "error": "speaker trouble", "off": "speaker off"}.get(self.phase,
                                                                      "speaker warming up")
        tx = r.left() + 30
        p.setFont(theme.heading(12, True))
        p.setPen(QColor(C.plum))
        p.drawText(QRectF(tx, r.top() + 3, r.width() - 36, 18),
                   Qt.AlignmentFlag.AlignVCenter, title)
        p.setFont(theme.body(17))
        p.setPen(QColor(C.plum_soft))
        fm = QFontMetrics(p.font())
        p.drawText(QRectF(tx, r.top() + 20, r.width() - 36, 18), Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(self.detail, Qt.TextElideMode.ElideRight, int(r.width() - 38)))
        p.end()


class PlaylistHeader(QWidget):
    """Compact header above the song list: cover, name, play + shuffle."""
    playClicked = Signal()
    shuffleClicked = Signal()

    def __init__(self, images: ImageLoader, parent=None):
        super().__init__(parent)
        self.images = images
        self.pl: Playlist | None = None
        self.setFixedHeight(96)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 4)
        lay.setSpacing(12)
        self.cover = QLabel()
        self.cover.setFixedSize(72, 72)
        lay.addWidget(self.cover)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.kicker = QLabel("PLAYLIST")
        self.kicker.setFont(theme.heading(11, True))
        self.kicker.setStyleSheet(f"color:{C.hot}; letter-spacing: 1px;")
        self.title = QLabel("")
        self.title.setFont(theme.heading(18, True))
        self.title.setStyleSheet(f"color:{C.plum};")
        self.meta = QLabel("")
        self.meta.setFont(theme.body(18))
        self.meta.setStyleSheet(f"color:{C.plum_soft};")
        row = QHBoxLayout()
        row.setSpacing(6)
        self.btn_play = QPushButton(" play")
        self.btn_play.setObjectName("primary")
        self.btn_play.setIcon(theme.icon("play", C.white, 1))
        self.btn_shuffle = QPushButton(" shuffle")
        self.btn_shuffle.setIcon(theme.icon("shuffle", C.hot, 1))
        for b in (self.btn_play, self.btn_shuffle):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("padding: 2px 10px; font-size: 13px;")
            row.addWidget(b)
        row.addStretch(1)
        self.btn_play.clicked.connect(self.playClicked)
        self.btn_shuffle.clicked.connect(self.shuffleClicked)
        for w in (self.kicker, self.title, self.meta):
            col.addWidget(w)
        col.addLayout(row)
        lay.addLayout(col, 1)
        images.loaded.connect(lambda u: self.pl and u == self.pl.image_url and self._cover())

    def show_playlist(self, pl: Playlist, count: int | None = None, note: str = ""):
        self.pl = pl
        kinds = {"liked": "YOUR FAVES ♡", "recent": "ON REPEAT LATELY",
                 "search": "SEARCH"}
        self.kicker.setText(kinds.get(pl.kind, "PLAYLIST"))
        fm = QFontMetrics(self.title.font())
        self.title.setText(fm.elidedText(pl.name, Qt.TextElideMode.ElideRight,
                                         max(120, self.width() - 110)))
        self.title.setToolTip(pl.name)
        bits = []
        n = count if count is not None else pl.total
        if n:
            bits.append(f"{n} songs")
        if pl.owner:
            bits.append(f"by {pl.owner}")
        if note:
            bits.append(note)
        self.meta.setText("  ♡  ".join(bits))
        self.btn_shuffle.setVisible(pl.kind != "search")
        self._cover()

    def _cover(self):
        pl = self.pl
        if not pl:
            return
        if pl.kind in ("liked", "recent", "search"):
            self.cover.setPixmap(tile_pixmap(pl.kind, 72))
        else:
            self.cover.setPixmap(self.images.get(pl.image_url, 72, 12))


def tile_pixmap(kind: str, size: int) -> QPixmap:
    """Pastel square with a pixel icon, used for Liked / Recent / Search / Favorites."""
    from PySide6.QtGui import QLinearGradient
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cols = {"liked": ("#ffc4e6", "#ff9ec7"), "recent": ("#e7dbff", "#c3a8ff"),
            "search": ("#d6fff1", "#a9e8d6"), "favorites": ("#fff6c8", "#ffd86b")}
    a, b = cols.get(kind, cols["liked"])
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor(a))
    g.setColorAt(1, QColor(b))
    p.setBrush(g)
    p.setPen(QPen(QColor(C.white), 2))
    p.drawRoundedRect(QRectF(1, 1, size - 2, size - 2), size * 0.2, size * 0.2)
    icon = {"liked": "heart", "recent": "clock", "search": "search",
            "favorites": "star"}.get(kind, "note")
    theme.draw_icon(p, icon, C.white, size / 2, size / 2, size / 16)
    p.end()
    return pm
