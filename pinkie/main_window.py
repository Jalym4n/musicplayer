"""The main window and the logic that ties the UI to Spotify."""
from __future__ import annotations

import time
import webbrowser

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QSizeGrip,
                               QVBoxLayout, QWidget)

from . import config, theme
from .auth import AuthError, TokenManager, login
from .images import ImageLoader
from .librespot import LibrespotManager, find_binary
from .models import Device, PlaybackState, Playlist, Track
from .spotify import NoActiveDevice, SpotifyClient, SpotifyError
from .theme import C
from .widgets.controls import gingham, rounded_path
from .widgets.dialogs import SettingsDialog
from .widgets.panels import NowPlaying, PlaylistHeader, Sidebar, TitleBar
from .widgets.tracklist import TrackList
from .worker import run_async

MARGIN = 14  # transparent space around the shell for the drop shadow


def pick_device(devices: list[Device], preferred_id: str = "",
                librespot_name: str = "") -> Device | None:
    """Choose a speaker: the one you picked last, else this computer's built-in
    librespot speaker, else whatever is active, else a computer, else anything."""
    if not devices:
        return None
    by_id = {d.id: d for d in devices}
    if preferred_id in by_id:
        return by_id[preferred_id]
    if librespot_name:
        for d in devices:
            if d.name == librespot_name:
                return d
    return next((d for d in devices if d.is_active), None) or \
        next((d for d in devices if d.type.lower() == "computer"), devices[0])


class Card(QWidget):
    def __init__(self, fill: str = "#b8ffffff", border: str = C.white, radius: int = 22,
                 parent=None):
        super().__init__(parent)
        self.fill, self.border, self.radius = QColor(fill), QColor(border), radius

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        p.setPen(QPen(self.border, 3))
        p.setBrush(self.fill)
        p.drawRoundedRect(r, self.radius, self.radius)
        p.end()


class MainWindow(QWidget):
    def __init__(self, settings: config.Settings, demo: bool = False):
        super().__init__()
        self.settings = settings
        self.demo = demo
        self.client = None
        self.state = PlaybackState()
        self.state_at = time.monotonic()
        self.devices: list[Device] = []
        self.view: Playlist | None = None
        self.view_tracks: list[Track] = []
        self.track_cache: dict[str, list[Track]] = {}
        self._view_seq = 0
        self._polling = False
        self._poll_errors = 0
        self._vol_touched = 0.0
        self._last_track_uri = None
        self._closing = False

        self.setWindowTitle(config.APP_NAME)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window
                            | Qt.WindowType.WindowMinimizeButtonHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(1180, 760)
        self.setMinimumSize(980, 640)

        self.images = ImageLoader(self)
        self.images.loaded.connect(self._image_loaded)
        self.librespot = LibrespotManager(self)
        self.librespot.loginUrl.connect(self._librespot_login)
        self._build()
        self._shortcuts()

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll)
        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self._tick)
        self.tick_timer.start(250)

    # ------------------------------------------------------------------ layout
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        outer.setSpacing(0)
        self.titlebar = TitleBar(self)
        self.titlebar.settingsClicked.connect(self.open_settings)
        outer.addWidget(self.titlebar)

        body = QHBoxLayout()
        body.setContentsMargins(14, 4, 14, 14)
        body.setSpacing(12)

        side_card = Card()
        sl = QVBoxLayout(side_card)
        sl.setContentsMargins(4, 10, 4, 6)
        self.sidebar = Sidebar(self.images)
        self.sidebar.selected.connect(self.open_view)
        self.sidebar.searchSubmitted.connect(self.search)
        sl.addWidget(self.sidebar)
        body.addWidget(side_card)

        center = Card(fill="#e6fff7fb")  # Qt reads 8-digit hex as #AARRGGBB
        cl = QVBoxLayout(center)
        cl.setContentsMargins(6, 6, 6, 10)
        cl.setSpacing(0)
        self.header = PlaylistHeader(self.images)
        self.header.playClicked.connect(lambda: self.play_view(shuffle=False))
        self.header.shuffleClicked.connect(lambda: self.play_view(shuffle=True))
        cl.addWidget(self.header)
        self.tracks = TrackList(self.images)
        self.tracks.playRequested.connect(self.play_row)
        cl.addWidget(self.tracks, 1)
        self.empty = QLabel("")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.setFont(theme.body(24))
        self.empty.setStyleSheet(f"color:{C.plum_soft}; padding: 30px;")
        cl.addWidget(self.empty, 1)
        self.empty.hide()
        body.addWidget(center, 1)

        np_card = Card()
        nl = QVBoxLayout(np_card)
        nl.setContentsMargins(4, 4, 0, 4)
        self.np = NowPlaying()
        nl.addWidget(self.np)
        body.addWidget(np_card)
        self.np.set_track("", "", 0, None)
        self.np.playPause.connect(self.toggle_play)
        self.np.nextClicked.connect(lambda: self._cmd("next"))
        self.np.prevClicked.connect(lambda: self._cmd("previous"))
        self.np.shuffleToggled.connect(self.set_shuffle)
        self.np.repeatClicked.connect(self.cycle_repeat)
        self.np.seekTo.connect(self.seek)
        self.np.volumeTo.connect(self.set_volume)
        self.np.deviceChosen.connect(self.transfer)
        self.np.devicesOpened.connect(self.refresh_devices)
        outer.addLayout(body, 1)

        self.toast = QLabel(self)
        self.toast.setFont(theme.heading(14))
        self.toast.setStyleSheet(
            f"background:{C.plum}; color:{C.white}; border-radius: 16px; padding: 8px 18px;")
        self.toast.hide()
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.toast.hide)

        self.grip = QSizeGrip(self)
        self.grip.setFixedSize(18, 18)
        self.grip.setStyleSheet("background: transparent;")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.grip.move(self.width() - MARGIN - 26, self.height() - MARGIN - 26)
        self._place_toast()

    def _place_toast(self):
        self.toast.adjustSize()
        self.toast.move((self.width() - self.toast.width()) // 2,
                        self.height() - MARGIN - self.toast.height() - 26)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        shell = QRectF(self.rect()).adjusted(MARGIN, MARGIN, -MARGIN, -MARGIN)
        maxed = self.isMaximized() or self.isFullScreen()
        if maxed:
            shell = QRectF(self.rect())
        radius = 0 if maxed else 30
        # soft shadow
        if not maxed:
            for i in range(MARGIN, 0, -2):
                c = QColor(C.plum)
                c.setAlpha(int(6 + (MARGIN - i) * 1.2))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(c)
                p.drawRoundedRect(shell.adjusted(-i / 2, -i / 2 + 3, i / 2, i / 2 + 3),
                                  radius + i / 2, radius + i / 2)
        # pink plastic shell
        p.setBrush(QColor(C.shell))
        p.setPen(QPen(QColor(C.shell_dark), 3))
        p.drawRoundedRect(shell, radius, radius)
        # gingham "screen"
        inner = shell.adjusted(10, 46, -10, -10)
        p.save()
        p.setClipPath(rounded_path(inner, 22))
        gingham(p, inner)
        p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(C.white), 4))
        p.drawRoundedRect(inner, 22, 22)
        p.end()

    def _shortcuts(self):
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self.toggle_play)
        QShortcut(QKeySequence("Ctrl+Right"), self, lambda: self._cmd("next"))
        QShortcut(QKeySequence("Ctrl+Left"), self, lambda: self._cmd("previous"))
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: (self.sidebar.search.setFocus(),
                                                         self.sidebar.search.selectAll()))
        QShortcut(QKeySequence("Ctrl+Q"), self, self.close)

    # ------------------------------------------------------------------ toasts
    def say(self, text: str, ms: int = 3500):
        self.toast.setText(text)
        self._place_toast()
        self.toast.show()
        self.toast.raise_()
        self.toast_timer.start(ms)

    def _error(self, exc: Exception):
        if isinstance(exc, AuthError):
            self.say(str(exc), 6000)
            config.clear_token()
            QTimer.singleShot(800, self._login)
            return
        if isinstance(exc, NoActiveDevice):
            self.say("no speaker yet! open Spotify on your phone or laptop, "
                     "then pick it below ♡", 6000)
            self.refresh_devices()
            return
        if isinstance(exc, SpotifyError):
            self.say(str(exc), 5000)
            return
        self.say(f"oops: {exc}", 5000)

    # ------------------------------------------------------------------ startup
    def start(self) -> bool:
        if self.demo:
            from .demo import DemoClient
            self.client = DemoClient()
            self._after_login()
            return True
        if not self.settings.client_id:
            dlg = SettingsDialog(self.settings, first_run=True, parent=None)
            if dlg.exec() != SettingsDialog.DialogCode.Accepted:
                return False
        token = config.load_token()
        if token:
            self.client = SpotifyClient(TokenManager(self.settings.client_id, token))
            self._after_login()
        else:
            self._login()
        return True

    def _login(self):
        self.empty.setText("a Spotify login page just opened in your browser.\n"
                           "log in there, then come right back ♡")
        self._show_empty(True)
        cid = self.settings.client_id

        def done(token):
            self.client = SpotifyClient(TokenManager(cid, token))
            self._after_login()

        def fail(exc):
            self.empty.setText(f"{exc}\n\nopen settings (gear icon) to check your Client ID.")
            self.say("login didn't work", 4000)

        run_async(login, cid, webbrowser.open, on_done=done, on_error=fail)

    def _after_login(self):
        def got_me(me):
            name = (me or {}).get("display_name") or "cutie"
            self.say(f"hi {name}! ♡")
        run_async(self.client.me, on_done=got_me, on_error=self._error)
        self.refresh_playlists()
        self.sidebar.select_id("__liked")
        self._maybe_start_librespot()
        self.refresh_devices()
        self.poll()
        self.poll_timer.start(int(self.settings.poll_seconds * 1000))

    def refresh_playlists(self):
        run_async(self.client.playlists, on_done=self.sidebar.set_playlists,
                  on_error=self._error)

    # ------------------------------------------------------------------ librespot
    def _maybe_start_librespot(self):
        if self.demo or not self.settings.librespot_autostart:
            return
        binary = find_binary(self.settings.librespot_path)
        if binary and self.librespot.start(binary, self.settings.device_name):
            QTimer.singleShot(3500, self.refresh_devices)

    def _librespot_login(self, url: str):
        self.say("one-time login so this computer can be a speaker ♡", 6000)
        webbrowser.open(url)

    # ------------------------------------------------------------------ views
    def _show_empty(self, on: bool):
        self.empty.setVisible(on)
        self.tracks.setVisible(not on)

    def open_view(self, pl: Playlist):
        if not self.client or pl is None:
            return
        self.view = pl
        self._view_seq += 1
        seq = self._view_seq
        self.header.show_playlist(pl)
        if pl.kind == "playlist" and not pl.readable:
            self.view_tracks = []
            self.tracks.tmodel.set_tracks([])
            self.empty.setText("Spotify only shares the song list of playlists you made "
                               "or collaborate on.\n\nyou can still press play ♡")
            self._show_empty(True)
            return
        cached = self.track_cache.get(pl.id)
        if cached is not None:
            self._show_tracks(pl, cached)
            if pl.kind not in ("recent",):
                return
        else:
            self.tracks.tmodel.set_tracks([])
            self.empty.setText("loading ♡")
            self._show_empty(True)
        fetch = {"liked": self.client.liked_tracks,
                 "recent": self.client.recently_played}.get(pl.kind)
        fn = fetch or (lambda: self.client.playlist_tracks(pl.id))

        def done(tracks):
            self.track_cache[pl.id] = tracks
            if seq == self._view_seq:
                self._show_tracks(pl, tracks)

        def fail(exc):
            if seq != self._view_seq:
                return
            if isinstance(exc, SpotifyError) and exc.status == 403:
                self.empty.setText("Spotify keeps this playlist's song list private.\n\n"
                                   "you can still press play ♡")
                self._show_empty(True)
            else:
                self.empty.setText("couldn't load these songs :(")
                self._error(exc)

        run_async(fn, on_done=done, on_error=fail)

    def _show_tracks(self, pl: Playlist, tracks: list[Track]):
        self.view_tracks = tracks
        self.tracks.tmodel.set_tracks(tracks)
        self.tracks.tmodel.set_current(self.state.track.uri if self.state.track else "")
        self.header.show_playlist(pl, len(tracks))
        if tracks:
            self._show_empty(False)
            self.tracks.scrollToTop()
        else:
            self.empty.setText("no songs here yet ♡")
            self._show_empty(True)

    def search(self, query: str):
        if not self.client:
            return
        self.sidebar.list.setCurrentItem(None)
        pl = Playlist(f"__search:{query}", f'"{query}"', kind="search")
        self.track_cache.pop(pl.id, None)
        self.open_view(pl)

    # ------------------------------------------------------------------ playback
    def _device_prefs(self) -> tuple[str, str]:
        """Snapshot (taken on the UI thread) of which speaker we'd like to use."""
        lib_name = self.settings.device_name if self.librespot.running else ""
        return self.settings.preferred_device_id, lib_name

    def _play(self, **kw):
        client = self.client
        active = self.state.device and self.state.device.is_active
        prefs = self._device_prefs()

        def job():
            if not active:
                dev = pick_device(client.devices(), *prefs)
                if dev:
                    kw["device_id"] = dev.id
            try:
                client.play(**kw)
            except NoActiveDevice:
                dev = pick_device(client.devices(), *prefs)
                if not dev:
                    raise
                kw["device_id"] = dev.id
                client.play(**kw)

        self.state.is_playing = True
        self.np.set_playing(True)
        run_async(job, on_done=lambda _: self._refresh_soon(), on_error=self._play_failed)

    def _play_failed(self, exc):
        self.state.is_playing = False
        self.np.set_playing(False)
        self._error(exc)

    def play_row(self, row: int):
        if not self.view or row >= len(self.view_tracks):
            return
        t = self.view_tracks[row]
        if self.view.kind == "playlist" and self.view.uri:
            self._play(context_uri=self.view.uri, offset_uri=t.uri)
        else:
            self._play(uris=[x.uri for x in self.view_tracks[row:row + 100]])

    def play_view(self, shuffle: bool):
        if not self.view:
            return
        client = self.client

        def go():
            if self.view.kind == "playlist" and self.view.uri:
                self._play(context_uri=self.view.uri)
            elif self.view_tracks:
                self._play(uris=[x.uri for x in self.view_tracks[:100]])

        if shuffle or self.state.shuffle != shuffle:
            self.np.set_shuffle(shuffle)
            self.state.shuffle = shuffle
            # shuffle needs a device; ignore failure here, play() will sort out devices
            run_async(client.shuffle, shuffle, on_done=lambda _: go(), on_error=lambda _e: go())
        else:
            go()

    def toggle_play(self):
        if not self.client:
            return
        if self.state.is_playing:
            self.state.is_playing = False
            self.np.set_playing(False)
            self._sync_progress()
            self._cmd("pause")
        elif self.state.track:
            self.state.is_playing = True
            self.state_at = time.monotonic()
            self.np.set_playing(True)
            self._play()
        elif self.view_tracks:
            self.play_row(0)
        else:
            self.say("pick a song first ♡")

    def _cmd(self, name: str, *args):
        if not self.client:
            return
        fn = getattr(self.client, name)
        run_async(fn, *args, on_done=lambda _: self._refresh_soon(), on_error=self._error)

    def set_shuffle(self, on: bool):
        self.state.shuffle = on
        self._cmd("shuffle", on)

    def cycle_repeat(self):
        nxt = {"off": "context", "context": "track", "track": "off"}[self.np.repeat_mode]
        self.np.set_repeat(nxt)
        self.state.repeat = nxt
        self._cmd("repeat", nxt)

    def seek(self, ms: int):
        self.state.progress_ms = ms
        self.state_at = time.monotonic()
        self._cmd("seek", ms)

    def set_volume(self, v: int):
        self._vol_touched = time.monotonic()
        self.state.volume = v
        self._cmd("volume", v)

    def transfer(self, device_id: str):
        self.settings.preferred_device_id = device_id
        self.settings.save()
        name = next((d.name for d in self.devices if d.id == device_id), "speaker")
        self.say(f"now playing on {name} ♡")
        run_async(self.client.transfer, device_id, True,
                  on_done=lambda _: (self._refresh_soon(), QTimer.singleShot(900, self.refresh_devices)),
                  on_error=self._error)

    def refresh_devices(self):
        if not self.client:
            return

        def done(devs):
            self.devices = devs
            active = next((d.id for d in devs if d.is_active), "")
            self.np.set_devices(devs, active)

        run_async(self.client.devices, on_done=done, on_error=lambda e: None)

    # ------------------------------------------------------------------ state sync
    def _refresh_soon(self, ms: int = 450):
        QTimer.singleShot(ms, self.poll)

    def poll(self):
        if not self.client or self._polling or self._closing:
            return
        self._polling = True

        def done(state: PlaybackState):
            self._polling = False
            self._poll_errors = 0
            self.apply_state(state)

        def fail(exc):
            self._polling = False
            self._poll_errors += 1
            if isinstance(exc, AuthError) or self._poll_errors == 3:
                self._error(exc)

        run_async(self.client.playback, on_done=done, on_error=fail)

    def apply_state(self, s: PlaybackState):
        if time.monotonic() - self._vol_touched < 2.5:
            s.volume = self.state.volume
        self.state = s
        self.state_at = time.monotonic()
        t = s.track
        uri = t.uri if t else ""
        if uri != self._last_track_uri:
            self._last_track_uri = uri
            pm = self.images.raw(t.image_url) if t else None
            self.np.set_track(t.name if t else "", t.artists if t else "",
                              t.duration_ms if t else 0, pm)
            self.tracks.tmodel.set_current(uri)
            self.setWindowTitle(f"{t.name} - {config.APP_NAME}" if t else config.APP_NAME)
        self.np.set_playing(s.is_playing)
        self.np.set_shuffle(s.shuffle)
        self.np.set_repeat(s.repeat if s.repeat in ("off", "context", "track") else "off")
        self.np.set_volume(s.volume)
        self.np.set_progress(s.progress_ms)
        if s.device and s.device.id and not any(d.id == s.device.id and d.is_active
                                                for d in self.devices):
            self.refresh_devices()

    def _sync_progress(self):
        self.state.progress_ms = self._current_pos()
        self.state_at = time.monotonic()

    def _current_pos(self) -> int:
        s = self.state
        if not s.is_playing:
            return s.progress_ms
        pos = s.progress_ms + int((time.monotonic() - self.state_at) * 1000)
        return min(pos, s.track.duration_ms) if s.track else pos

    def _tick(self):
        if not self.state.track:
            return
        pos = self._current_pos()
        self.np.set_progress(pos)
        if self.state.is_playing and pos >= self.state.track.duration_ms and not self._polling:
            self._refresh_soon(300)

    def _image_loaded(self, url: str):
        t = self.state.track
        if t and t.image_url == url:
            self.np.cover.set_pixmap(self.images.raw(url))

    # ------------------------------------------------------------------ settings
    def open_settings(self):
        old_id = self.settings.client_id
        dlg = SettingsDialog(self.settings, parent=self)
        res = dlg.exec()
        if res == SettingsDialog.LOGOUT:
            config.clear_token()
            self.say("logged out. see you soon ♡")
            QTimer.singleShot(1200, QApplication.instance().quit)
        elif res == SettingsDialog.DialogCode.Accepted and not self.demo:
            if self.settings.client_id != old_id:
                config.clear_token()
                self._login()
            self._maybe_start_librespot()

    def closeEvent(self, e):
        self._closing = True
        self.poll_timer.stop()
        self.librespot.stop()
        super().closeEvent(e)
