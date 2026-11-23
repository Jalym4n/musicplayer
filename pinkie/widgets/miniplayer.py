"""The Mini-Player: a tiny always-on-top window in retro desktop style.

Two looks (right-click to switch): "classic" with the album cover, and "cassette" with
spinning tape reels. It remembers where it was put, can stay on top of other windows,
and pops up by itself when the big window is minimized.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QLinearGradient, QPainter, QPainterPath, QPen,
                           QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QAbstractButton, QHBoxLayout, QLabel, QMenu,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import theme
from ..models import fmt_ms
from ..theme import C
from .controls import HeartSlider, MarqueeLabel
from .deck import CandyButton, HeartButton, OtterSlider
from .panels import RetroButton

TITLE_H = 30
M = 10  # shadow margin
ART = 96
STYLES = ("classic", "cassette")


class MiniToggle(QAbstractButton):
    """Small round icon toggle (shuffle / repeat). Glows pink when on."""

    def __init__(self, icon: str, tooltip: str, color: str = C.lav_dark, parent=None):
        super().__init__(parent)
        self.icon_name, self.color = icon, color
        self.badge = ""
        self.setCheckable(True)
        self.setFixedSize(34, 34)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        c = QPointF(self.width() / 2, self.height() / 2)
        if on:
            glow = QRadialGradient(c, 16)
            glow.setColorAt(0, QColor(255, 158, 199, 170))
            glow.setColorAt(1, QColor(255, 158, 199, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(c, 16, 16)
        theme.draw_icon(p, self.icon_name, C.hot if on else self.color, c.x(), c.y(), 2.0,
                        C.butter)
        if self.badge:
            p.setBrush(QColor(C.butter))
            p.setPen(QPen(QColor(C.hot), 1.2))
            p.drawEllipse(QPointF(c.x() + 11, c.y() - 10), 6, 6)
            p.setFont(theme.heading(9, True))
            p.setPen(QColor(C.plum))
            p.drawText(QRectF(c.x() + 5, c.y() - 16, 12, 12), Qt.AlignmentFlag.AlignCenter,
                       self.badge)
        p.end()


class Reels(QWidget):
    """Cassette window: two spinning reels with the album cover as a little sticker."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(ART, ART)
        self._pix: QPixmap | None = None
        self._playing = False
        self._angle = 0.0
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(40)

    def set_cover(self, pm):
        self._pix = pm
        self.update()

    def set_playing(self, on: bool):
        self._playing = on

    def _tick(self):
        if self._playing and self.isVisible():
            self._angle = (self._angle + 4) % 360
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        p.setPen(QPen(QColor(C.lav_dark), 2))
        p.setBrush(QColor(C.cream))
        p.drawRoundedRect(r, 10, 10)
        win = QRectF(r.left() + 8, r.top() + 10, r.width() - 16, r.height() * 0.42)
        p.setBrush(QColor("#3b2c48"))
        p.drawRoundedRect(win, win.height() / 2, win.height() / 2)
        rr = win.height() * 0.38
        for cx in (win.left() + win.width() * 0.26, win.right() - win.width() * 0.26):
            p.save()
            p.translate(cx, win.center().y())
            p.rotate(self._angle)
            p.setPen(QPen(QColor(C.lav_mid), 1.2))
            p.setBrush(QColor(C.white))
            p.drawEllipse(QPointF(0, 0), rr, rr)
            p.setPen(QPen(QColor(C.lav_dark), 1.6))
            for k in range(3):
                a = math.radians(k * 120)
                p.drawLine(QPointF(0, 0), QPointF(math.cos(a) * rr * 0.8, math.sin(a) * rr * 0.8))
            p.restore()
        # cover sticker
        s = r.height() * 0.38
        sticker = QRectF(r.center().x() - s / 2, r.bottom() - s - 6, s, s)
        clip = QPainterPath()
        clip.addEllipse(sticker)
        p.save()
        p.setClipPath(clip)
        if self._pix and not self._pix.isNull():
            p.drawPixmap(sticker, self._pix, QRectF(self._pix.rect()))
        else:
            p.fillRect(sticker, QColor(C.pink_soft))
            theme.draw_emoji(p, theme.OTTER, sticker.center().x(), sticker.center().y(),
                             int(s * 0.6))
        p.restore()
        p.setPen(QPen(QColor(C.white), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(sticker)
        theme.draw_icon(p, "heart", C.shell, sticker.left() - 9, sticker.center().y(), 1.0)
        theme.draw_icon(p, "star", C.star, sticker.right() + 9, sticker.center().y(), 1.0)
        p.end()


class MiniPlayer(QWidget):
    playPause = Signal()
    nextClicked = Signal()
    prevClicked = Signal()
    seekTo = Signal(int)
    shuffleToggled = Signal(bool)
    repeatClicked = Signal()
    volumeTo = Signal(int)
    restoreMain = Signal()
    prefsChanged = Signal()          # style / on-top / pop-up-on-minimize changed
    moved = Signal()                 # dragged somewhere new
    shownChanged = Signal(bool)      # opened or closed by her

    def __init__(self, style: str = "classic", on_top: bool = True,
                 on_minimize: bool = True, parent=None):
        super().__init__(parent)
        self.style_name = style if style in STYLES else "classic"
        self.on_top = on_top
        self.on_minimize = on_minimize
        self._apply_flags()
        # macOS hides tool windows when the app isn't in front; a mini-player shouldn't.
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Mini-Player")
        self.setFixedSize(420 + 2 * M, 214 + 2 * M)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._pix: QPixmap | None = None
        self._drag: QPoint | None = None
        self._duration = 0
        self._repeat = "off"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(M + 8, M + 3, M + 10, M + 8)
        outer.setSpacing(4)
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(4)
        bar.addStretch(1)
        self.b_min = RetroButton("minus", "Minimize", C.white, 20, 1.4)
        self.b_max = RetroButton("square", "Open the big player", C.white, 20, 1.4)
        self.b_close = RetroButton("close", "Close mini-player", C.white, 20, 1.4)
        for b in (self.b_min, self.b_max, self.b_close):
            bar.addWidget(b)
        self.b_min.clicked.connect(self.showMinimized)
        self.b_max.clicked.connect(self.restoreMain)
        self.b_close.clicked.connect(self.close_by_user)
        outer.addLayout(bar)

        body = QHBoxLayout()
        body.setSpacing(12)
        self.art = QStackedWidget()
        self.art.setFixedSize(ART, ART)
        self.cover = QLabel()
        self.cover.setFixedSize(ART, ART)
        self.reels = Reels()
        self.art.addWidget(self.cover)
        self.art.addWidget(self.reels)
        body.addWidget(self.art, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.title = MarqueeLabel(theme.heading(16, True), C.plum)
        self.artist = MarqueeLabel(theme.body(20), C.plum_soft)
        self.time = QLabel("0:00 / 0:00")
        self.time.setFont(theme.body(18))
        self.time.setStyleSheet(f"color:{C.lav_dark};")
        col.addWidget(self.title)
        col.addWidget(self.artist)
        col.addWidget(self.time)
        vrow = QHBoxLayout()
        vrow.setSpacing(4)
        spk = QLabel()
        spk.setPixmap(theme.pixmap("speaker", C.lav_dark, 1.6))
        self.volume = HeartSlider(100, 22)
        self.volume.released.connect(self.volumeTo)
        vrow.addWidget(spk)
        vrow.addWidget(self.volume, 1)
        col.addLayout(vrow)
        col.addStretch(1)
        body.addLayout(col, 1)
        outer.addLayout(body)

        ctr = QHBoxLayout()
        ctr.setSpacing(4)
        self.b_shuffle = MiniToggle("shuffle", "Shuffle")
        self.b_prev = CandyButton("rewind", "Previous")
        self.b_play = HeartButton(62)
        self.b_next = CandyButton("ffwd", "Next")
        self.b_repeat = MiniToggle("flower", "Repeat: off", C.shell_dark)
        for b in (self.b_prev, self.b_next):
            b.setFixedSize(50, 42)
        ctr.addStretch(1)
        for w in (self.b_shuffle, self.b_prev, self.b_play, self.b_next, self.b_repeat):
            ctr.addWidget(w, 0, Qt.AlignmentFlag.AlignVCenter)
        ctr.addStretch(1)
        outer.addLayout(ctr)
        self.progress = OtterSlider()
        self.progress.setFixedHeight(28)
        self.progress.released.connect(self.seekTo)
        self.progress.moved.connect(lambda v: self._show_time(v))
        outer.addWidget(self.progress)

        self.b_play.clicked.connect(self.playPause)
        self.b_prev.clicked.connect(self.prevClicked)
        self.b_next.clicked.connect(self.nextClicked)
        self.b_shuffle.clicked.connect(lambda: self.shuffleToggled.emit(self.b_shuffle.isChecked()))
        self.b_repeat.clicked.connect(self._repeat_clicked)
        self.set_style(self.style_name)
        self.set_track("", "", 0, None)

    # --- window behaviour ------------------------------------------------------------
    def _apply_flags(self):
        flags = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        if self.on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def set_on_top(self, on: bool):
        self.on_top = on
        visible = self.isVisible()
        self._apply_flags()
        if visible:
            self.show()

    def set_style(self, style: str):
        self.style_name = style if style in STYLES else "classic"
        self.art.setCurrentWidget(self.reels if self.style_name == "cassette" else self.cover)
        self.update()

    def close_by_user(self):
        self.hide()
        self.shownChanged.emit(False)

    def contextMenuEvent(self, e):
        m = QMenu(self)
        styles = {}
        for st, label in (("classic", "classic style"), ("cassette", "cassette style")):
            a = m.addAction(label)
            a.setCheckable(True)
            a.setChecked(self.style_name == st)
            styles[a] = st
        m.addSeparator()
        top = m.addAction("always on top")
        top.setCheckable(True)
        top.setChecked(self.on_top)
        auto = m.addAction("pop up when the big player is minimized")
        auto.setCheckable(True)
        auto.setChecked(self.on_minimize)
        m.addSeparator()
        big = m.addAction("open the big player")
        close = m.addAction("close mini-player")
        act = m.exec(e.globalPos())
        if act in styles:
            self.set_style(styles[act])
            self.prefsChanged.emit()
        elif act is top:
            self.set_on_top(not self.on_top)
            self.prefsChanged.emit()
        elif act is auto:
            self.on_minimize = not self.on_minimize
            self.prefsChanged.emit()
        elif act is big:
            self.restoreMain.emit()
        elif act is close:
            self.close_by_user()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Space:
            self.playPause.emit()
        elif e.key() == Qt.Key.Key_Right:
            self.nextClicked.emit()
        elif e.key() == Qt.Key.Key_Left:
            self.prevClicked.emit()
        else:
            super().keyPressEvent(e)

    def wheelEvent(self, e):
        if not self.volume.isEnabled():
            return
        step = 5 if e.angleDelta().y() > 0 else -5
        v = max(0, min(100, self.volume.value() + step))
        self.volume.set_value(v)
        self.volumeTo.emit(v)

    def moveEvent(self, e):
        super().moveEvent(e)
        if self.isVisible():
            self.moved.emit()

    def _repeat_clicked(self):
        self.b_repeat.setChecked(self._repeat != "off")   # the main window decides
        self.repeatClicked.emit()

    def _show_time(self, ms: int):
        self.time.setText(f"{fmt_ms(ms)} / {fmt_ms(self._duration)}")

    # --- same update API as the deck (the main window broadcasts to both) ----------
    def set_track(self, title: str, artist: str, duration_ms: int, pixmap,
                  album: str = "", year: str = ""):
        self.title.setText(title or "nothing playing")
        self.artist.setText(artist or "pick a song, cutie ♡")
        self._duration = duration_ms
        self.progress.set_maximum(max(1, duration_ms))
        self._show_time(0)
        self.set_cover(pixmap)

    def set_cover(self, pm):
        self._pix = pm
        self.reels.set_cover(pm)
        size = ART
        out = QPixmap(size * 2, size * 2)
        out.setDevicePixelRatio(2)
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        frame = QRectF(2, 2, size - 4, size - 4)
        p.setPen(QPen(QColor(C.lav_mid), 2))
        p.setBrush(QColor(C.white))
        p.drawRoundedRect(frame, 10, 10)
        art = frame.adjusted(5, 5, -5, -5)
        clip = QPainterPath()
        clip.addRoundedRect(art, 6, 6)
        p.setClipPath(clip)
        if pm and not pm.isNull():
            p.drawPixmap(art, pm, QRectF(pm.rect()))
        else:
            p.fillRect(art, QColor(C.pink_soft))
            theme.draw_emoji(p, theme.OTTER, art.center().x(), art.center().y(), 34)
        p.end()
        self.cover.setPixmap(out)

    def set_progress(self, ms: int):
        if not self.progress.dragging:
            self.progress.set_value(ms)
            self._show_time(ms)

    def set_playing(self, on: bool):
        self.b_play.set_playing(on)
        self.reels.set_playing(on)

    def set_shuffle(self, on: bool):
        self.b_shuffle.setChecked(on)

    def set_repeat(self, mode: str):
        self._repeat = mode
        self.b_repeat.setChecked(mode != "off")
        self.b_repeat.badge = "1" if mode == "track" else ""
        self.b_repeat.setToolTip({"off": "Repeat: off", "context": "Repeat: all",
                                  "track": "Repeat: this song"}.get(mode, "Repeat"))
        self.b_repeat.update()

    def set_volume(self, v):
        self.volume.setEnabled(v is not None)
        if v is not None and not self.volume.dragging:
            self.volume.set_value(v)

    # --- window chrome --------------------------------------------------------------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(M, M, -M, -M)
        for i in range(M, 0, -2):
            c = QColor(C.plum)
            c.setAlpha(int(5 + (M - i) * 2))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(r.adjusted(-i / 2, -i / 2 + 3, i / 2, i / 2 + 3), 12 + i / 2,
                              12 + i / 2)
        if self.style_name == "cassette":
            self._paint_cassette(p, r)
        else:
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, QColor("#fff0f8"))
            g.setColorAt(1, QColor("#efe4ff"))
            p.setBrush(g)
            p.setPen(QPen(QColor(C.lav_dark), 2))
            p.drawRoundedRect(r, 12, 12)
        bar = QRectF(r.left() + 4, r.top() + 4, r.width() - 8, TITLE_H - 4)
        bg = QLinearGradient(bar.topLeft(), bar.topRight())
        bg.setColorAt(0, QColor("#ffc4e6"))
        bg.setColorAt(1, QColor("#cdb4ff"))
        p.setBrush(bg)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(bar, 8, 8)
        f = theme.heading(14, True)
        theme.draw_outlined(p, "Mini-Player", bar.left() + 36, bar.center().y() + 5, f,
                            C.plum, C.white, width=4)
        theme.draw_emoji(p, theme.OTTER, bar.left() + 18, bar.center().y(), 21)
        p.end()

    def _paint_cassette(self, p: QPainter, r: QRectF):
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor("#efe4ff"))
        g.setColorAt(1, QColor("#cbb6f7"))
        p.setBrush(g)
        p.setPen(QPen(QColor(C.lav_dark), 2.5))
        p.drawRoundedRect(r, 14, 14)
        # cream paper label behind the song info
        label = QRectF(r.left() + ART + 14, r.top() + TITLE_H + 2, r.width() - ART - 24, 90)
        p.setPen(QPen(QColor(C.lav_mid), 1.5))
        p.setBrush(QColor(C.cream))
        p.drawRoundedRect(label, 6, 6)
        p.setPen(QPen(QColor("#f3b6d3"), 1))
        for k in range(1, 4):
            y = label.top() + k * label.height() / 4
            p.drawLine(QPointF(label.left() + 6, y), QPointF(label.right() - 6, y))
        # screws in the corners
        p.setBrush(QColor("#dccbfb"))
        p.setPen(QPen(QColor(C.lav_dark), 1.2))
        for x, y in ((r.left() + 9, r.top() + TITLE_H + 6), (r.right() - 9, r.top() + TITLE_H + 6),
                     (r.left() + 9, r.bottom() - 9), (r.right() - 9, r.bottom() - 9)):
            p.drawEllipse(QPointF(x, y), 3.5, 3.5)
            p.drawLine(QPointF(x - 2, y), QPointF(x + 2, y))
