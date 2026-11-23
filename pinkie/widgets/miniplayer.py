"""The Mini-Player: a tiny always-on-top window in retro desktop style."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import theme
from ..models import fmt_ms
from ..theme import C
from .controls import MarqueeLabel
from .deck import CandyButton, HeartButton, OtterSlider
from .panels import RetroButton

TITLE_H = 30
M = 10  # shadow margin


class MiniPlayer(QWidget):
    playPause = Signal()
    nextClicked = Signal()
    prevClicked = Signal()
    seekTo = Signal(int)
    restoreMain = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Mini-Player")
        self.setFixedSize(370 + 2 * M, 176 + 2 * M)
        self._pix: QPixmap | None = None
        self._drag: QPoint | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(M + 6, M + 2, M + 8, M + 8)
        outer.setSpacing(6)
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
        self.b_close.clicked.connect(self.hide)
        outer.addLayout(bar)

        body = QHBoxLayout()
        body.setSpacing(10)
        self.cover = QLabel()
        self.cover.setFixedSize(92, 92)
        body.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.title = MarqueeLabel(theme.heading(15, True), C.plum)
        self.artist = MarqueeLabel(theme.body(19), C.plum_soft)
        col.addWidget(self.title)
        col.addWidget(self.artist)
        ctr = QHBoxLayout()
        ctr.setSpacing(2)
        self.b_prev = CandyButton("rewind", "Previous")
        self.b_play = HeartButton(64)
        self.b_next = CandyButton("ffwd", "Next")
        for b in (self.b_prev, self.b_next):
            b.setFixedSize(50, 44)
        ctr.addStretch(1)
        ctr.addWidget(self.b_prev)
        ctr.addWidget(self.b_play)
        ctr.addWidget(self.b_next)
        ctr.addStretch(1)
        col.addLayout(ctr)
        body.addLayout(col, 1)
        outer.addLayout(body)
        self.progress = OtterSlider()
        self.progress.setFixedHeight(28)
        self.progress.released.connect(self.seekTo)
        outer.addWidget(self.progress)
        self.b_play.clicked.connect(self.playPause)
        self.b_prev.clicked.connect(self.prevClicked)
        self.b_next.clicked.connect(self.nextClicked)
        self.set_track("", "", 0, None)

    # --- same update API as the deck (the main window broadcasts to both) ----------
    def set_track(self, title: str, artist: str, duration_ms: int, pixmap,
                  album: str = "", year: str = ""):
        self.title.setText(title or "nothing playing")
        self.artist.setText(artist or "pick a song, cutie ♡")
        self.progress.set_maximum(max(1, duration_ms))
        self.progress.setToolTip(fmt_ms(duration_ms))
        self.set_cover(pixmap)

    def set_cover(self, pm):
        self._pix = pm
        size = 92
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

    def set_playing(self, on: bool):
        self.b_play.set_playing(on)

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
            p.drawRoundedRect(r.adjusted(-i / 2, -i / 2 + 3, i / 2, i / 2 + 3), 12 + i / 2, 12 + i / 2)
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
        theme.draw_outlined(p, "Mini-Player", bar.left() + 32, bar.center().y() + 5, f,
                            C.plum, C.white, width=4)
        theme.draw_emoji(p, theme.OTTER, bar.left() + 16, bar.center().y(), 18)
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and e.position().y() < M + TITLE_H + 4:
            handle = self.windowHandle()
            if handle and handle.startSystemMove():
                return
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None
