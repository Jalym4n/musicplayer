"""The main window and the logic that ties the UI to Spotify."""
from __future__ import annotations

import dataclasses
import random
import time
import webbrowser

from PySide6.QtCore import QEvent, QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QGuiApplication, QKeySequence, QLinearGradient, QPainter,
                           QPen, QShortcut)
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QSizeGrip,
                               QVBoxLayout, QWidget)

from . import config, personal, theme
from . import soloist
from . import speaker as spk
from .auth import AuthError, TokenManager, login
from .images import ImageLoader
from .models import Device, PlaybackState, Playlist, Track
from .nowplaying import NowPlayingBridge
from .spotify import NoActiveDevice, SpotifyClient, SpotifyError
from .theme import C
from .widgets.deck import Deck
from .widgets.dialogs import SettingsDialog
from .widgets.miniplayer import MiniPlayer
from .widgets.notebook import Heartbeat, Notebook
from .widgets.panels import TitleBar
from .widgets.side import Sidebar
from .worker import run_async

MARGIN = 14  # transparent space around the shell for the drop shadow
READY_TEXT = "music comes out of your speakers ♡"
SOLOIST_ACTIVE = "soloist:active"   # Soloist is playing but isn't in the Web API device list


class Fanout:
    """Calls a method on every view that has it (the deck and the mini-player)."""

    def __init__(self, *views):
        self.views = views

    def __getattr__(self, name):
        def call(*args, **kwargs):
            for v in self.views:
                fn = getattr(v, name, None)
                if fn:
                    fn(*args, **kwargs)
        return call


class DeckCard(QWidget):
    """Holographic lavender/pink panel behind the deck."""

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor("#efe2ff"))
        g.setColorAt(0.5, QColor("#ffe3f3"))
        g.setColorAt(1, QColor("#e3f1ff"))
        p.setPen(QPen(QColor(C.white), 3))
        p.setBrush(g)
        p.drawRoundedRect(r, 18, 18)
        p.setPen(QPen(QColor(C.lav_mid), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(-2, -2, 2, 2), 20, 20)
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
        self.speaker_id = ""          # Spotify device id of our built-in speaker
        self._finding_speaker = False
        self.view: Playlist | None = None
        self.view_tracks: list[Track] = []
        self.upnext_tracks: list[Track] = []
        self.track_cache: dict[str, list[Track]] = {}
        self._view_seq = 0
        self._polling = False
        self._poll_errors = 0
        self._vol_touched = 0.0
        self._last_track_uri = None
        self._closing = False
        self._live = False            # Soloist is pushing live playback events
        self._live_queue = False      # ...including the queue
        self._years: dict[str, str] = {}   # release years from the Web API (Soloist has none)

        self.title_text = personal.title(settings.her_name)
        self.setWindowTitle(self.title_text)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window
                            | Qt.WindowType.WindowMinimizeButtonHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(1280, 800)
        self.setMinimumSize(1100, 700)
        rnd = random.Random(8)
        self._bg_stars = [(rnd.random(), rnd.random(), rnd.choice(["sparkle", "star"]))
                          for _ in range(26)]

        self.images = ImageLoader(self)
        self.images.loaded.connect(self._image_loaded)
        self._speaker_url = ""
        self.speaker = self._make_speaker(self._engine())
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
        self.titlebar = TitleBar(self, self.title_text)
        self.titlebar.settingsClicked.connect(self.open_settings)
        self.titlebar.miniClicked.connect(self.toggle_mini)
        outer.addWidget(self.titlebar)

        body = QHBoxLayout()
        body.setContentsMargins(14, 8, 14, 14)
        body.setSpacing(12)

        self.sidebar = Sidebar(self.images, self.settings.her_name, self.settings.favorites)
        self.sidebar.selected.connect(self.open_view)
        self.sidebar.searchSubmitted.connect(self.search)
        self.sidebar.favoritesChanged.connect(self._save_favorites)
        body.addWidget(self.sidebar)

        card = DeckCard()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(4, 4, 4, 4)
        self.deck = Deck()
        cl.addWidget(self.deck)
        body.addWidget(card, 1)

        right = QVBoxLayout()
        right.setSpacing(10)
        self.notebook = Notebook(self.images)
        self.notebook.setFixedWidth(350)
        self.notebook.upNextPlay.connect(self.play_upnext)
        self.notebook.header.playClicked.connect(lambda: self.play_view(shuffle=False))
        self.notebook.header.shuffleClicked.connect(lambda: self.play_view(shuffle=True))
        self.notebook.tracks.playRequested.connect(self.play_row)
        self.notebook.tab_next.clicked.connect(self.refresh_queue)
        self.header, self.tracks, self.empty = (self.notebook.header, self.notebook.tracks,
                                                self.notebook.empty)
        self.heartbeat = Heartbeat()
        self.heartbeat.setFixedWidth(350)
        right.addWidget(self.notebook, 1)
        right.addWidget(self.heartbeat)
        body.addLayout(right)
        outer.addLayout(body, 1)

        self.mini = MiniPlayer(self.settings.mini_style, self.settings.mini_on_top,
                               self.settings.mini_on_minimize)
        self._mini_auto = False       # opened by itself because the big window was minimized
        self._mini_save = QTimer(self)
        self._mini_save.setSingleShot(True)
        self._mini_save.timeout.connect(self._save_mini)
        # media keys, AirPods buttons and the system Now Playing widget
        self.nowplaying = NowPlayingBridge(self)
        self.nowplaying.playPause.connect(self.toggle_play)
        self.nowplaying.play.connect(lambda: self.state.is_playing or self.toggle_play())
        self.nowplaying.pause.connect(lambda: self.state.is_playing and self.toggle_play())
        self.nowplaying.nextClicked.connect(lambda: self._cmd("next"))
        self.nowplaying.prevClicked.connect(lambda: self._cmd("previous"))
        self.nowplaying.seekTo.connect(self.seek)
        self.views = Fanout(self.deck, self.mini, self.nowplaying)
        for view in (self.deck, self.mini):
            view.playPause.connect(self.toggle_play)
            view.nextClicked.connect(lambda: self._cmd("next"))
            view.prevClicked.connect(lambda: self._cmd("previous"))
            view.seekTo.connect(self.seek)
        self.deck.shuffleToggled.connect(self.set_shuffle)
        self.deck.repeatClicked.connect(self.cycle_repeat)
        self.deck.volumeTo.connect(self.set_volume)
        self.deck.speakerClicked.connect(self._speaker_clicked)
        self.mini.restoreMain.connect(self.restore_from_mini)
        self.mini.shuffleToggled.connect(self.set_shuffle)
        self.mini.repeatClicked.connect(self.cycle_repeat)
        self.mini.volumeTo.connect(self.set_volume)
        self.mini.prefsChanged.connect(self._save_mini)
        self.mini.moved.connect(lambda: self._mini_save.start(600))
        self.mini.shownChanged.connect(lambda shown: self._save_mini())

        self.toast = QLabel(self)
        self.toast.setFont(theme.heading(14))
        self.toast.setStyleSheet(
            f"background:{C.plum}; color:{C.white}; border-radius: 16px; padding: 8px 18px;"
            f"border: 2px solid {C.pink_soft};")
        self.toast.hide()
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.toast.hide)

        self.grip = QSizeGrip(self)
        self.grip.setFixedSize(18, 18)
        self.grip.setStyleSheet("background: transparent;")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.grip.move(self.width() - MARGIN - 24, self.height() - MARGIN - 24)
        self._place_toast()

    def _place_toast(self):
        self.toast.adjustSize()
        self.toast.move((self.width() - self.toast.width()) // 2,
                        self.height() - MARGIN - self.toast.height() - 30)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        maxed = self.isMaximized() or self.isFullScreen()
        shell = QRectF(self.rect()) if maxed else \
            QRectF(self.rect()).adjusted(MARGIN, MARGIN, -MARGIN, -MARGIN)
        radius = 0 if maxed else 24
        if not maxed:
            for i in range(MARGIN, 0, -2):
                c = QColor(C.lav_dark)
                c.setAlpha(int(6 + (MARGIN - i) * 1.3))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(c)
                p.drawRoundedRect(shell.adjusted(-i / 2, -i / 2 + 3, i / 2, i / 2 + 3),
                                  radius + i / 2, radius + i / 2)
        g = QLinearGradient(shell.topLeft(), shell.bottomRight())
        g.setColorAt(0, QColor("#f6e9ff"))
        g.setColorAt(0.55, QColor("#fde6f4"))
        g.setColorAt(1, QColor("#e9e2ff"))
        p.setBrush(g)
        p.setPen(QPen(QColor(C.lav_dark), 2))
        p.drawRoundedRect(shell, radius, radius)
        for fx, fy, name in self._bg_stars:
            theme.draw_icon(p, name, "#80ffffff", shell.left() + fx * shell.width(),
                            shell.top() + 60 + fy * (shell.height() - 70), 1.4)
        # title strip
        strip = QRectF(shell.left() + 6, shell.top() + 6, shell.width() - 12, 50)
        sg = QLinearGradient(strip.topLeft(), strip.topRight())
        sg.setColorAt(0, QColor("#ffc9e6"))
        sg.setColorAt(0.5, QColor("#f2d4ff"))
        sg.setColorAt(1, QColor("#cfc0ff"))
        p.setBrush(sg)
        p.setPen(QPen(QColor(C.white), 3))
        p.drawRoundedRect(strip, radius - 6 if radius else 0, radius - 6 if radius else 0)
        p.end()

    def _shortcuts(self):
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self.toggle_play)
        QShortcut(QKeySequence("Ctrl+Right"), self, lambda: self._cmd("next"))
        QShortcut(QKeySequence("Ctrl+Left"), self, lambda: self._cmd("previous"))
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: (self.sidebar.search.setFocus(),
                                                         self.sidebar.search.selectAll()))
        QShortcut(QKeySequence("Ctrl+M"), self, self.toggle_mini)
        QShortcut(QKeySequence("Ctrl+Q"), self, self.close)

    # ------------------------------------------------------------------ mini-player
    def toggle_mini(self):
        if self.mini.isVisible():
            self.mini.close_by_user()
        else:
            self.show_mini()

    def show_mini(self, auto: bool = False):
        """Open the Mini-Player where she last left it (or bottom-right of the big one)."""
        self._mini_auto = auto
        pos = self.settings.mini_pos
        if len(pos) == 2 and QGuiApplication.screenAt(QPoint(int(pos[0]) + 40, int(pos[1]) + 20)):
            self.mini.move(int(pos[0]), int(pos[1]))
        else:
            geo = self.frameGeometry()
            self.mini.move(geo.right() - self.mini.width() - 20,
                           geo.bottom() - self.mini.height() - 20)
        self.mini.show()
        self.mini.raise_()
        if not auto:
            self._save_mini()

    def _save_mini(self):
        s = self.settings
        s.mini_style, s.mini_on_top = self.mini.style_name, self.mini.on_top
        s.mini_on_minimize = self.mini.on_minimize
        if self.mini.isVisible():
            p = self.mini.pos()
            s.mini_pos = [p.x(), p.y()]
        if not self._mini_auto:
            s.mini_open = self.mini.isVisible()
        s.save()

    def restore_from_mini(self):
        self._mini_auto = False
        self.mini.hide()
        self._save_mini()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() != QEvent.Type.WindowStateChange:
            return
        if self.isMinimized():
            if self.mini.on_minimize and not self.mini.isVisible():
                self.show_mini(auto=True)
        elif self._mini_auto:
            # back from the Dock: put the auto-opened mini-player away again
            self._mini_auto = False
            self.mini.hide()

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
            self.say("the speaker isn't ready yet, try again in a sec ♡", 5000)
            self.speaker_id = ""
            self._find_speaker()
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
            self._apply_name()
        token = config.load_token()
        if token:
            self.client = SpotifyClient(TokenManager(self.settings.client_id, token))
            self._after_login()
        else:
            self._login()
        return True

    def _login(self):
        self.notebook.show_page(1)
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
        if self.settings.mini_open and not self.mini.isVisible():
            QTimer.singleShot(300, self.show_mini)
        self.say(f"hi {self.settings.her_name}! {theme.OTTER}♡", 5000)
        self.refresh_playlists()
        self.sidebar.select_id("__liked")
        self._start_speaker()
        self.poll()
        self.poll_timer.start(int(self.settings.poll_seconds * 1000))

    def refresh_playlists(self):
        run_async(self.client.playlists, on_done=self.sidebar.set_playlists,
                  on_error=self._error)

    def _save_favorites(self, ids: list):
        self.settings.favorites = ids
        self.settings.save()

    def _apply_name(self):
        name = self.settings.her_name
        self.title_text = personal.title(name)
        self.titlebar.set_title(self.title_text)
        self.sidebar.pal.set_name(name)
        if not self.state.track:
            self.setWindowTitle(self.title_text)

    # ------------------------------------------------------------------ speaker
    def _engine(self) -> str:
        e = self.settings.speaker_engine
        if e in ("soloist", "librespot"):
            return e
        # automatic: Soloist once it's set up (or once Spotify blocked librespot here)
        if self.settings.soloist_key or self.settings.librespot_blocked:
            return "soloist"
        return "librespot"

    def _make_speaker(self, engine: str):
        cls = soloist.SoloistSpeaker if engine == "soloist" else spk.Speaker
        sp = cls(self.settings.speaker_name, self)
        sp.phaseChanged.connect(self._speaker_phase)
        sp.loginUrl.connect(self._speaker_login_url)
        if hasattr(sp, "playerEvent"):
            sp.playerEvent.connect(self._on_player_event)
        return sp

    def _start_speaker(self):
        """Start the built-in speaker so music plays straight out of this computer."""
        if self.demo:
            self.speaker_id = "dev-here"
            self.views.set_speaker(spk.READY, READY_TEXT)
            return
        engine = self._engine()
        if self.speaker.engine != engine:
            self.speaker.stop()
            self.speaker.phaseChanged.disconnect(self._speaker_phase)
            self.speaker.deleteLater()
            self.speaker = self._make_speaker(engine)
            self.speaker_id = ""
        self.speaker.name = self.settings.speaker_name
        if engine == "soloist":
            self.speaker.start(soloist.find_binary(self.settings.soloist_path),
                               self.settings.soloist_key)
        else:
            self.speaker.start(spk.find_binary(self.settings.librespot_path))

    def _pair_hint(self) -> str:
        return (f"one-time pairing: on your phone (same Wi-Fi) open Spotify → tap the "
                f"devices icon → pick {self.settings.speaker_name} ♡")

    def _speaker_phase(self, phase: str, detail: str):
        self.views.set_speaker(phase, detail)
        if phase == spk.READY:
            self._find_speaker()
        elif phase == spk.LOGIN:
            self.say("one quick login so this computer can play music ♡", 7000)
        elif phase == soloist.PAIR:
            self.speaker_id = ""
            self.say(self._pair_hint(), 10000)
        elif phase == spk.ERROR:
            self.speaker_id = ""
            if getattr(self.speaker, "blocked", False):
                self.settings.librespot_blocked = True
                self.settings.save()
                if self.settings.speaker_engine == "auto":
                    self.say("switching to Spotify Soloist, Spotify's own player ♡", 7000)
                    QTimer.singleShot(400, self._start_speaker)
                    return
            self.say(detail, 7000)
        elif phase == spk.MISSING:
            if self.speaker.engine == "soloist":
                self.say("one-time setup: Settings → download Soloist + add your key ♡", 9000)
            else:
                self.say("the built-in speaker is missing: see the README ♡", 8000)

    # ------------------------------------------------------------------ live events
    def _set_live(self, on: bool):
        """While Soloist streams events, Spotify polling only runs as a slow backup."""
        if on == self._live:
            return
        self._live = on
        if not on:
            self._live_queue = False
        if self.poll_timer.isActive():
            self.poll_timer.start(15000 if on else int(self.settings.poll_seconds * 1000))

    def _on_player_event(self, ev: dict):
        kind = ev.get("type")
        if kind == "device_changed":
            self._set_live(bool(ev.get("is_active")))
            if not ev.get("is_active"):
                self._refresh_soon(200)
            return
        if kind == "queue_changed":
            tracks = soloist.queue_tracks(ev)
            self._live_queue = True
            self.upnext_tracks = tracks
            self.notebook.set_upnext(tracks)
            self.notebook.upnext.tmodel.set_current(
                self.state.track.uri if self.state.track else "")
            return
        if kind == "playback_state":
            self._set_live(bool(ev.get("is_active", True)))
        if not self._live:
            return
        s = dataclasses.replace(self.state)
        s.progress_ms = self._current_pos()   # events without a position keep the clock
        if not soloist.apply_event(s, ev):
            return
        if s.track and not s.track.year:
            s.track.year = self._years.get(s.track.uri, "")
        s.device = Device(self.speaker_id or "soloist", self.settings.speaker_name,
                          "Computer", True, s.volume)
        self.apply_state(s, live=True)

    def _speaker_login_url(self, url: str):
        self._speaker_url = url  # librespot opens the browser itself; chip click reopens

    def _speaker_clicked(self):
        phase = self.speaker.phase if not self.demo else spk.READY
        if phase == spk.LOGIN and self._speaker_url:
            webbrowser.open(self._speaker_url)
        elif phase == soloist.PAIR:
            self.say(self._pair_hint(), 10000)
        elif phase == spk.MISSING or getattr(self.speaker, "blocked", False):
            self.open_settings()
        elif phase in (spk.ERROR, spk.OFF):
            self.speaker.stop()
            self.speaker_id = ""
            self._start_speaker()
        elif self.speaker_id and self.state.device and self.state.device.id != self.speaker_id:
            self.bring_here()

    def _find_speaker(self, attempt: int = 0):
        """Look up our speaker's Spotify device id (it takes a moment to register)."""
        if self.demo or not self.client or (self._finding_speaker and attempt == 0):
            return
        self._finding_speaker = True
        name = self.settings.speaker_name

        def done(devs):
            self.devices = devs
            me = next((d for d in devs if d.name == name), None)
            if me:
                self._finding_speaker = False
                first = not self.speaker_id
                self.speaker_id = me.id
                self.views.set_speaker(spk.READY, READY_TEXT)
                if first and not (self.state.device and self.state.device.is_active
                                  and self.state.is_playing):
                    # make this computer the active speaker, without blasting music
                    run_async(self.client.transfer, me.id, False, on_error=lambda e: None)
            elif self.speaker.engine == "soloist" and attempt >= 6:
                # Soloist is signed in but not listed by the Web API: make it the active
                # device through its own local control instead, right before playing.
                self._finding_speaker = False
                self.speaker_id = SOLOIST_ACTIVE
            elif attempt < 20:
                QTimer.singleShot(1500, lambda: self._find_speaker(attempt + 1))
            else:
                self._finding_speaker = False
                self.views.set_speaker(spk.ERROR, "speaker didn't show up on Spotify")

        def fail(_e):
            if attempt < 20:
                QTimer.singleShot(2000, lambda: self._find_speaker(attempt + 1))
            else:
                self._finding_speaker = False

        run_async(self.client.devices, on_done=done, on_error=fail)

    def bring_here(self):
        """Move whatever is playing on another device over to this computer."""
        if not self.speaker_id:
            return
        self.say("bringing the music here ♡")
        if self.speaker_id == SOLOIST_ACTIVE:
            run_async(self.speaker.activate, on_done=lambda _: self._refresh_soon(),
                      on_error=self._error)
            return
        run_async(self.client.transfer, self.speaker_id, True,
                  on_done=lambda _: self._refresh_soon(), on_error=self._error)

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
        self.notebook.show_page(1)
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
            self.empty.setText(f"loading {theme.OTTER}")
            self._show_empty(True)
        fetch = {"liked": self.client.liked_tracks,
                 "recent": self.client.recently_played}.get(pl.kind)
        if pl.kind == "search":
            query = pl.id.split(":", 1)[1]
            fetch = lambda: self.client.search(query)  # noqa: E731
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

    def refresh_queue(self):
        if not self.client:
            return

        def done(tracks):
            self.upnext_tracks = tracks
            self.notebook.set_upnext(tracks)
            self.notebook.upnext.tmodel.set_current(
                self.state.track.uri if self.state.track else "")

        run_async(self.client.queue, on_done=done, on_error=lambda e: None)

    # ------------------------------------------------------------------ playback
    def _play(self, **kw):
        if not self.speaker_id:
            phase = self.speaker.phase
            if phase == spk.MISSING:
                self.say("the built-in speaker is missing: see the README ♡", 6000)
            elif phase == spk.LOGIN:
                self.say("finish the one-time speaker login in your browser first ♡", 6000)
            elif phase == soloist.PAIR:
                self.say(self._pair_hint(), 10000)
            elif getattr(self.speaker, "blocked", False) or (
                    self.speaker.engine == "soloist" and phase == spk.MISSING):
                self.say("set up Spotify Soloist in Settings first ♡", 6000)
            else:
                self.say("the speaker is still warming up, one sec ♡")
                self._find_speaker()
            return
        client, device, speaker = self.client, self.speaker_id, self.speaker

        def job():
            # Always aim at our own speaker, so the sound comes out of this computer.
            if device == SOLOIST_ACTIVE:
                speaker.activate()
                time.sleep(0.6)
                client.play(**kw)
            else:
                client.play(device_id=device, **kw)

        self.state.is_playing = True
        self.views.set_playing(True)
        self.heartbeat.set_playing(True)
        run_async(job, on_done=lambda _: self._refresh_soon(), on_error=self._play_failed)

    def _play_failed(self, exc):
        self.state.is_playing = False
        self.views.set_playing(False)
        self.heartbeat.set_playing(False)
        self._error(exc)

    def play_row(self, row: int):
        if not self.view or row >= len(self.view_tracks):
            return
        t = self.view_tracks[row]
        if self.view.kind == "playlist" and self.view.uri:
            self._play(context_uri=self.view.uri, offset_uri=t.uri)
        else:
            self._play(uris=[x.uri for x in self.view_tracks[row:row + 100]])

    def play_upnext(self, row: int):
        if row >= len(self.upnext_tracks):
            return
        t = self.upnext_tracks[row]
        ctx = self.state.context_uri
        if ctx and (ctx.startswith("spotify:playlist:") or ctx.startswith("spotify:album:")):
            self._play(context_uri=ctx, offset_uri=t.uri)
        else:
            self._play(uris=[x.uri for x in self.upnext_tracks[row:]])

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
            self.views.set_shuffle(shuffle)
            self.state.shuffle = shuffle
            # shuffle needs an active device; if it fails, play() still starts the music
            sid = "" if self.speaker_id == SOLOIST_ACTIVE else self.speaker_id
            run_async(client.shuffle, shuffle, sid,
                      on_done=lambda _: go(), on_error=lambda _e: go())
        else:
            go()

    def toggle_play(self):
        if not self.client:
            return
        if self.state.is_playing:
            self.state.is_playing = False
            self.views.set_playing(False)
            self.heartbeat.set_playing(False)
            self._sync_progress()
            self._cmd("pause")
        elif self.state.track:
            self.state.is_playing = True
            self.state_at = time.monotonic()
            self.views.set_playing(True)
            self._play()
        elif self.view_tracks:
            self.play_row(0)
        else:
            self.say("pick a song first, cutie ♡")

    def _cmd(self, name: str, *args):
        if not self.client:
            return
        fn = getattr(self.client, name)
        run_async(fn, *args, on_done=lambda _: self._refresh_soon(), on_error=self._error)

    def set_shuffle(self, on: bool):
        self.state.shuffle = on
        self._cmd("shuffle", on)

    def cycle_repeat(self):
        nxt = {"off": "context", "context": "track", "track": "off"}[self.deck.repeat_mode]
        self.views.set_repeat(nxt)
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
            if state.track and state.track.year:
                self._years[state.track.uri] = state.track.year
            moved = state.device and state.device.id and self.speaker_id not in (
                "", SOLOIST_ACTIVE) and state.device.id != self.speaker_id
            if self._live and not moved:
                # live events are fresher; just fill in the release year for the LCD
                cur = self.state.track
                if cur and state.track and cur.uri == state.track.uri and not cur.year \
                        and state.track.year:
                    cur.year = state.track.year
                    self.views.set_track(cur.name, cur.artists, cur.duration_ms,
                                         self.images.raw(cur.image_url), cur.album, cur.year)
                return
            if moved:
                self._set_live(False)
            self.apply_state(state)

        def fail(exc):
            self._polling = False
            self._poll_errors += 1
            if isinstance(exc, AuthError) or self._poll_errors == 3:
                self._error(exc)

        run_async(self.client.playback, on_done=done, on_error=fail)

    def apply_state(self, s: PlaybackState, live: bool = False):
        if time.monotonic() - self._vol_touched < 2.5:
            s.volume = self.state.volume
        self.state = s
        self.state_at = time.monotonic()
        t = s.track
        uri = t.uri if t else ""
        if uri != self._last_track_uri:
            self._last_track_uri = uri
            pm = self.images.raw(t.image_url) if t else None
            if t:
                self.views.set_track(t.name, t.artists, t.duration_ms, pm, t.album, t.year)
            else:
                self.views.set_track("", "", 0, None)
            self.tracks.tmodel.set_current(uri)
            self.notebook.upnext.tmodel.set_current(uri)
            self.setWindowTitle(f"{t.name} ♡ {self.title_text}" if t else self.title_text)
            if not (live and self._live_queue):
                self.refresh_queue()
        self.views.set_playing(s.is_playing)
        self.heartbeat.set_playing(s.is_playing)
        self.views.set_shuffle(s.shuffle)
        self.views.set_repeat(s.repeat if s.repeat in ("off", "context", "track") else "off")
        self.views.set_volume(s.volume)
        self.views.set_progress(s.progress_ms)
        if self.speaker_id and self.speaker_id != SOLOIST_ACTIVE and s.device and \
                s.device.id and s.device.id != self.speaker_id:
            self.views.set_speaker("elsewhere", f"playing on {s.device.name}: tap to bring it here")
        elif self.speaker_id and self.deck.speaker_phase == "elsewhere":
            self.views.set_speaker(spk.READY, READY_TEXT)

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
        self.views.set_progress(pos)
        if self.state.is_playing and pos >= self.state.track.duration_ms and not self._polling:
            self._refresh_soon(300)

    def _image_loaded(self, url: str):
        t = self.state.track
        if t and t.image_url == url:
            self.views.set_cover(self.images.raw(url))

    # ------------------------------------------------------------------ settings
    def open_settings(self):
        old_id = self.settings.client_id
        old_speaker = (self.settings.speaker_name, self._engine(), self.settings.soloist_key,
                       self.settings.soloist_path)
        dlg = SettingsDialog(self.settings, parent=self)
        res = dlg.exec()
        if res == SettingsDialog.LOGOUT:
            config.clear_token()
            self.speaker.forget_login()
            self.say("logged out. see you soon ♡")
            QTimer.singleShot(1200, QApplication.instance().quit)
        elif res == SettingsDialog.RESET_SPEAKER and not self.demo:
            self.speaker.forget_login()
            self.speaker_id = ""
            self.say("speaker login reset: a Spotify login tab will open ♡", 6000)
            self._start_speaker()
        elif res == SettingsDialog.DialogCode.Accepted:
            self._apply_name()
            if self.demo:
                return
            if self.settings.client_id != old_id:
                config.clear_token()
                self._login()
            new_speaker = (self.settings.speaker_name, self._engine(), self.settings.soloist_key,
                           self.settings.soloist_path)
            if new_speaker != old_speaker or self.speaker.phase in (spk.MISSING, spk.ERROR,
                                                                    spk.OFF):
                self.speaker.stop()
                self.speaker_id = ""
                self._start_speaker()

    def closeEvent(self, e):
        self._closing = True
        self.poll_timer.stop()
        self.speaker.stop()
        self.nowplaying.shutdown()
        if self.mini.isVisible():
            self._save_mini()
        self.mini.close()
        super().closeEvent(e)
