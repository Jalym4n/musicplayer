"""Title bar, sidebar, playlist header and the now-playing panel."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from .. import theme
from ..images import ImageLoader
from ..models import Device, Playlist, fmt_ms
from ..theme import C
from .controls import HeartSlider, MarqueeLabel, PixelButton
from .cover import VinylCover


class TitleBar(QWidget):
    """Custom draggable title bar (the window is frameless so it can be all pink)."""
    settingsClicked = Signal()

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.win = window
        self.setFixedHeight(46)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 6, 12, 2)
        lay.addStretch(1)
        self.btn_settings = PixelButton("gear", 26, 1.8, tooltip="Settings")
        self.btn_min = PixelButton("minus", 26, 2, fill=C.butter, tooltip="Minimize")
        self.btn_close = PixelButton("close", 26, 2, fill=C.mint, tooltip="Close")
        for b in (self.btn_settings, self.btn_min, self.btn_close):
            lay.addWidget(b)
        self.btn_settings.clicked.connect(self.settingsClicked)
        self.btn_min.clicked.connect(window.showMinimized)
        self.btn_close.clicked.connect(window.close)
        self._drag = None
        self._sparkle = 0
        t = QTimer(self)
        t.timeout.connect(self._twinkle)
        t.start(600)

    def _twinkle(self):
        self._sparkle = (self._sparkle + 1) % 4
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = theme.heading(22, True)
        p.setFont(f)
        text = "pinkie player"
        x = 52
        # sticker-style outlined title
        p.setPen(QColor(C.shell_dark))
        p.drawText(QPointF(x + 2, 34), text)
        p.setPen(QColor(C.white))
        p.drawText(QPointF(x, 32), text)
        theme.draw_icon(p, "heart", C.white, 30, 24, 2.4)
        tw = QFontMetrics(f).horizontalAdvance(text)
        for i, dx in enumerate((tw + 70, tw + 96, tw + 118)):
            col = C.white if (i + self._sparkle) % 3 else C.butter
            theme.draw_icon(p, "sparkle", col, dx, 24 + (i % 2) * 6, 1.6 + (i == self._sparkle % 3) * .6)
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


class Sidebar(QWidget):
    """Search box, Liked Songs, Recently Played and the user's playlists."""
    searchSubmitted = Signal(str)
    selected = Signal(object)  # Playlist

    def __init__(self, images: ImageLoader, parent=None):
        super().__init__(parent)
        self.images = images
        self.setFixedWidth(250)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 4, 10)
        lay.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("search songs...")
        self.search.addAction(theme.icon("search", C.hot, 2),
                              QLineEdit.ActionPosition.LeadingPosition)
        self.search.returnPressed.connect(
            lambda: self.search.text().strip() and self.searchSubmitted.emit(self.search.text().strip()))
        lay.addWidget(self.search)
        cap = QLabel("my mixtapes")
        cap.setFont(theme.heading(14, True))
        cap.setStyleSheet(f"color:{C.hot}; padding: 6px 6px 0 6px;")
        lay.addWidget(cap)
        self.list = QListWidget()
        self.list.setIconSize(QSize(38, 38))
        self.list.setFont(theme.body(21))
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.currentItemChanged.connect(self._changed)
        lay.addWidget(self.list, 1)
        self._items: dict[str, QListWidgetItem] = {}
        images.loaded.connect(self._image_ready)
        self.specials = [
            Playlist("__liked", "Liked Songs", kind="liked"),
            Playlist("__recent", "Recently Played", kind="recent"),
        ]
        self.set_playlists([])

    def set_playlists(self, playlists: list[Playlist]):
        self.list.blockSignals(True)
        cur = self.current()
        self.list.clear()
        self._items.clear()
        for pl in self.specials:
            name = "heart" if pl.kind == "liked" else "clock"
            ic = theme.still_icon(theme.pixmap(name, C.hot, 4))
            self._add(pl, ic)
        for pl in playlists:
            self._add(pl, theme.still_icon(self.images.get(pl.image_url, 38, 9)))
        if cur:
            self.select_id(cur.id)  # keep the selection without reloading the view
        self.list.blockSignals(False)

    def _add(self, pl: Playlist, ic: QIcon):
        it = QListWidgetItem(ic, pl.name)
        it.setData(Qt.ItemDataRole.UserRole, pl)
        it.setSizeHint(QSize(220, 48))
        tip = pl.name + (f"\nby {pl.owner}" if pl.owner else "")
        if pl.total:
            tip += f"\n{pl.total} songs"
        it.setToolTip(tip)
        self.list.addItem(it)
        self._items[pl.id] = it

    def _image_ready(self, url):
        for it in self._items.values():
            pl: Playlist = it.data(Qt.ItemDataRole.UserRole)
            if pl.image_url == url:
                it.setIcon(theme.still_icon(self.images.get(url, 38, 9)))

    def _changed(self, cur, _prev):
        if cur:
            self.selected.emit(cur.data(Qt.ItemDataRole.UserRole))

    def current(self) -> Playlist | None:
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def select_id(self, pid: str):
        it = self._items.get(pid)
        if it:
            self.list.setCurrentItem(it)


class PlaylistHeader(QWidget):
    """Big cover + title + play/shuffle-play buttons at the top of the song list."""
    playClicked = Signal()
    shuffleClicked = Signal()

    def __init__(self, images: ImageLoader, parent=None):
        super().__init__(parent)
        self.images = images
        self.pl: Playlist | None = None
        self.setFixedHeight(168)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 8)
        lay.setSpacing(18)
        self.cover = QLabel()
        self.cover.setFixedSize(140, 140)
        lay.addWidget(self.cover)
        col = QVBoxLayout()
        col.setSpacing(4)
        self.kicker = QLabel("PLAYLIST")
        self.kicker.setFont(theme.heading(12, True))
        self.kicker.setStyleSheet(f"color:{C.hot}; letter-spacing: 2px;")
        self.title = QLabel("")
        self.title.setFont(theme.heading(30, True))
        self.title.setStyleSheet(f"color:{C.plum};")
        self.meta = QLabel("")
        self.meta.setObjectName("hint")
        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_play = QPushButton("  play  ")
        self.btn_play.setObjectName("primary")
        self.btn_play.setIcon(theme.icon("play", C.white, 2))
        self.btn_shuffle = QPushButton("shuffle")
        self.btn_shuffle.setIcon(theme.icon("shuffle", C.hot, 2))
        for b in (self.btn_play, self.btn_shuffle):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(b)
        row.addStretch(1)
        self.btn_play.clicked.connect(self.playClicked)
        self.btn_shuffle.clicked.connect(self.shuffleClicked)
        col.addStretch(1)
        for w in (self.kicker, self.title, self.meta):
            col.addWidget(w)
        col.addSpacing(6)
        col.addLayout(row)
        col.addStretch(1)
        lay.addLayout(col, 1)
        images.loaded.connect(lambda u: self.pl and u == self.pl.image_url and self._cover())

    def show_playlist(self, pl: Playlist, count: int | None = None, note: str = ""):
        self.pl = pl
        kinds = {"liked": "YOUR FAVES", "recent": "ON REPEAT LATELY", "search": "SEARCH"}
        self.kicker.setText(kinds.get(pl.kind, "PLAYLIST"))
        fm = QFontMetrics(self.title.font())
        self.title.setText(fm.elidedText(pl.name, Qt.TextElideMode.ElideRight,
                                         max(200, self.width() - 220)))
        self.title.setToolTip(pl.name)
        bits = []
        if pl.owner:
            bits.append(f"by {pl.owner}")
        n = count if count is not None else pl.total
        if n:
            bits.append(f"{n} songs")
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
            pm = QPixmap(280, 280)
            pm.setDevicePixelRatio(2)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            col = {"liked": C.shell, "recent": C.lavender, "search": C.mint}[pl.kind]
            p.setBrush(QColor(col))
            p.setPen(QPen(QColor(C.white), 4))
            p.drawRoundedRect(QRectF(2, 2, 136, 136), 18, 18)
            icon = {"liked": "heart", "recent": "clock", "search": "search"}[pl.kind]
            theme.draw_icon(p, icon, C.white, 70, 70, 6)
            p.end()
            self.cover.setPixmap(pm)
        else:
            self.cover.setPixmap(self.images.get(pl.image_url, 140, 18))


class NowPlaying(QWidget):
    """Right-hand panel: vinyl cover, title, progress, transport, volume, speaker."""
    playPause = Signal()
    nextClicked = Signal()
    prevClicked = Signal()
    shuffleToggled = Signal(bool)
    repeatClicked = Signal()
    seekTo = Signal(int)
    volumeTo = Signal(int)
    deviceChosen = Signal(str)
    devicesOpened = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(320)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 12, 16, 14)
        lay.setSpacing(6)
        cap = QLabel("now playing")
        cap.setFont(theme.heading(14, True))
        cap.setStyleSheet(f"color:{C.hot};")
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(cap)
        self.cover = VinylCover(205)
        lay.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignHCenter)
        self.title = MarqueeLabel(theme.heading(19, True), C.plum)
        self.artist = MarqueeLabel(theme.body(22), C.plum_soft)
        lay.addWidget(self.title)
        lay.addWidget(self.artist)
        self.progress = HeartSlider(1000)
        self.progress.released.connect(self.seekTo)
        lay.addWidget(self.progress)
        times = QHBoxLayout()
        self.t_pos = QLabel("0:00")
        self.t_len = QLabel("0:00")
        for t in (self.t_pos, self.t_len):
            t.setFont(theme.body(18))
            t.setStyleSheet(f"color:{C.plum_soft};")
        times.setContentsMargins(12, 0, 12, 0)
        times.addWidget(self.t_pos)
        times.addStretch(1)
        times.addWidget(self.t_len)
        lay.addLayout(times)
        self.progress.moved.connect(lambda v: self.t_pos.setText(fmt_ms(v)))

        row = QHBoxLayout()
        row.setSpacing(2)
        self.b_shuffle = PixelButton("shuffle", 36, 2, tooltip="Shuffle")
        self.b_shuffle.setCheckable(True)
        self.b_prev = PixelButton("prev", 42, 2.4, tooltip="Previous (Ctrl+Left)")
        self.b_play = PixelButton("play", 58, 3.2, fill=C.hot, ink=C.hot, tooltip="Play / pause (Space)")
        self.b_play.setCheckable(True)
        self.b_next = PixelButton("next", 42, 2.4, tooltip="Next (Ctrl+Right)")
        self.b_repeat = PixelButton("repeat", 36, 2, tooltip="Repeat: off")
        self.b_repeat.setCheckable(True)
        row.addStretch(1)
        for b in (self.b_shuffle, self.b_prev, self.b_play, self.b_next, self.b_repeat):
            row.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)
        lay.addLayout(row)
        self.b_play.setChecked(True)
        self.b_play.clicked.connect(lambda: (self.b_play.setChecked(True), self.playPause.emit()))
        self.b_next.clicked.connect(self.nextClicked)
        self.b_prev.clicked.connect(self.prevClicked)
        self.b_shuffle.clicked.connect(lambda: self.shuffleToggled.emit(self.b_shuffle.isChecked()))
        self.b_repeat.clicked.connect(self.repeatClicked)

        vol = QHBoxLayout()
        vol.setContentsMargins(6, 4, 6, 0)
        spk = QLabel()
        spk.setPixmap(theme.pixmap("speaker", C.hot, 2))
        self.volume = HeartSlider(100, 24)
        self.volume.released.connect(self.volumeTo)
        vol.addWidget(spk)
        vol.addWidget(self.volume, 1)
        lay.addLayout(vol)

        dev = QHBoxLayout()
        dev.setContentsMargins(6, 2, 6, 0)
        dic = QLabel()
        dic.setPixmap(theme.pixmap("device", C.hot, 2))
        self.devices = _DeviceCombo()
        self.devices.setToolTip("Which speaker plays the music")
        self.devices.opened.connect(self.devicesOpened)
        self.devices.activated.connect(self._device_activated)
        dev.addWidget(dic)
        dev.addWidget(self.devices, 1)
        lay.addLayout(dev)
        lay.addStretch(1)
        self._repeat = "off"

    # --- updates from the controller ---
    def set_track(self, title: str, artist: str, duration_ms: int, pixmap):
        self.title.setText(title or "nothing playing")
        self.artist.setText(artist or "pick a song, cutie")
        self.progress.set_maximum(max(1, duration_ms))
        self.t_len.setText(fmt_ms(duration_ms))
        self.cover.set_pixmap(pixmap)

    def set_progress(self, ms: int):
        if not self.progress.dragging:
            self.progress.set_value(ms)
            self.t_pos.setText(fmt_ms(ms))

    def set_playing(self, playing: bool):
        self.b_play.set_icon("pause" if playing else "play")
        self.cover.set_playing(playing)

    def set_shuffle(self, on: bool):
        self.b_shuffle.setChecked(on)

    def set_repeat(self, mode: str):
        self._repeat = mode
        self.b_repeat.setChecked(mode != "off")
        self.b_repeat.badge = "1" if mode == "track" else ""
        self.b_repeat.setToolTip({"off": "Repeat: off", "context": "Repeat: all",
                                  "track": "Repeat: this song"}[mode])
        self.b_repeat.update()

    @property
    def repeat_mode(self) -> str:
        return self._repeat

    def set_volume(self, v: int | None):
        self.volume.setEnabled(v is not None)
        if v is not None and not self.volume.dragging:
            self.volume.set_value(v)

    def set_devices(self, devices: list[Device], active_id: str = ""):
        self.devices.blockSignals(True)
        self.devices.clear()
        if not devices:
            self.devices.addItem("no speakers found", "")
        for d in devices:
            label = f"{'♡ ' if d.id == active_id else ''}{d.name}"
            self.devices.addItem(label, d.id)
            if d.id == active_id:
                self.devices.setCurrentIndex(self.devices.count() - 1)
        if not active_id and devices:
            self.devices.insertItem(0, "choose a speaker...", "")
            self.devices.setCurrentIndex(0)
        self.devices.blockSignals(False)

    def _device_activated(self, idx: int):
        did = self.devices.itemData(idx)
        if did:
            self.deviceChosen.emit(did)


class _DeviceCombo(QComboBox):
    opened = Signal()

    def showPopup(self):
        self.opened.emit()
        super().showPopup()
