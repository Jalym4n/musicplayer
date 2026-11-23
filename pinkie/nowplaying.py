"""Media keys and the system "Now Playing" widget.

macOS: registers with MPRemoteCommandCenter / MPNowPlayingInfoCenter (via PyObjC), so
the keyboard's play/pause, next and previous keys, AirPods and headphone buttons, the
Control Center / menu-bar Now Playing widget and the lock screen all control the app
and show the current song with its cover.

Other systems: does nothing for now (the bridge reports `available = False`).

The bridge has the same update methods as the deck and mini-player, so the main window
just adds it to the list of views it broadcasts to.
"""
from __future__ import annotations

import os
import sys
import time

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, Signal

PLAYING, PAUSED, STOPPED = 1, 2, 3          # MPNowPlayingPlaybackState
HANDLED, NO_CONTENT = 0, 100                # MPRemoteCommandHandlerStatus...


def _debug(msg: str) -> None:
    if os.environ.get("PINKIE_DEBUG"):
        print("[now playing]", msg, file=sys.stderr)


class NowPlayingBridge(QObject):
    playPause = Signal()
    play = Signal()
    pause = Signal()
    nextClicked = Signal()
    prevClicked = Signal()
    seekTo = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.available = False
        self.reason = "only supported on macOS so far"
        self._mp = None
        self._info: dict = {}
        self._handlers: list = []          # keep PyObjC blocks alive
        self._playing = False
        self._duration_ms = 0
        self._sent_pos_ms = 0
        self._sent_at = 0.0
        if sys.platform == "darwin":
            try:
                self._setup_macos()
                self.available = True
                self.reason = "macOS Now Playing"
            except Exception as exc:  # noqa: BLE001 - never break the app over this
                self.reason = f"macOS Now Playing unavailable: {exc}"
                _debug(self.reason)

    # -- macOS --------------------------------------------------------------------------
    def _setup_macos(self):
        import MediaPlayer as mp  # pyobjc-framework-MediaPlayer
        self._mp = mp
        cc = mp.MPRemoteCommandCenter.sharedCommandCenter()

        def hook(command, emit):
            def handler(event):
                try:
                    emit(event)
                except Exception as exc:  # noqa: BLE001
                    _debug(f"handler failed: {exc}")
                return HANDLED
            command.setEnabled_(True)
            token = command.addTargetWithHandler_(handler)
            self._handlers.append((command, token, handler))

        hook(cc.togglePlayPauseCommand(), lambda e: self.playPause.emit())
        hook(cc.playCommand(), lambda e: self.play.emit())
        hook(cc.pauseCommand(), lambda e: self.pause.emit())
        hook(cc.nextTrackCommand(), lambda e: self.nextClicked.emit())
        hook(cc.previousTrackCommand(), lambda e: self.prevClicked.emit())
        hook(cc.changePlaybackPositionCommand(),
             lambda e: self.seekTo.emit(int(float(e.positionTime()) * 1000)))
        for name in ("skipForwardCommand", "skipBackwardCommand", "seekForwardCommand",
                     "seekBackwardCommand", "ratingCommand", "likeCommand", "dislikeCommand",
                     "bookmarkCommand"):
            cmd = getattr(cc, name, None)
            if cmd:
                cmd().setEnabled_(False)
        self._center().setPlaybackState_(STOPPED)

    def _center(self):
        return self._mp.MPNowPlayingInfoCenter.defaultCenter()

    def _key(self, name: str, fallback: str) -> str:
        return getattr(self._mp, name, fallback)

    def _push(self):
        if not self.available:
            return
        try:
            mp = self._mp
            info = dict(self._info)
            info[self._key("MPNowPlayingInfoPropertyElapsedPlaybackTime",
                           "MPNowPlayingInfoPropertyElapsedPlaybackTime")] = self._sent_pos_ms / 1000.0
            info[self._key("MPNowPlayingInfoPropertyPlaybackRate",
                           "MPNowPlayingInfoPropertyPlaybackRate")] = 1.0 if self._playing else 0.0
            center = self._center()
            center.setNowPlayingInfo_(info if self._info else None)
            center.setPlaybackState_(PLAYING if self._playing else
                                     (PAUSED if self._info else STOPPED))
            _ = mp  # keep module referenced
        except Exception as exc:  # noqa: BLE001
            _debug(f"update failed: {exc}")

    def _artwork(self, pixmap):
        if pixmap is None or pixmap.isNull():
            return None
        try:
            from AppKit import NSImage
            from Foundation import NSData
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            pixmap.save(buf, "PNG")
            raw = bytes(ba.data())
            image = NSImage.alloc().initWithData_(NSData.dataWithBytes_length_(raw, len(raw)))
            if image is None:
                return None
            handler = lambda size: image  # noqa: E731
            self._art_handler = handler    # keep the block alive
            return self._mp.MPMediaItemArtwork.alloc().initWithBoundsSize_requestHandler_(
                image.size(), handler)
        except Exception as exc:  # noqa: BLE001
            _debug(f"artwork failed: {exc}")
            return None

    # -- same update API as the deck / mini-player ----------------------------------------
    def set_track(self, title: str, artist: str, duration_ms: int, pixmap,
                  album: str = "", year: str = ""):
        if not self.available:
            return
        self._duration_ms = duration_ms
        self._sent_pos_ms, self._sent_at = 0, time.monotonic()
        if not title:
            self._info = {}
            self._push()
            return
        k = self._key
        self._info = {
            k("MPMediaItemPropertyTitle", "title"): title,
            k("MPMediaItemPropertyArtist", "artist"): artist,
            k("MPMediaItemPropertyAlbumTitle", "albumTitle"): album or "",
            k("MPMediaItemPropertyPlaybackDuration", "playbackDuration"): duration_ms / 1000.0,
        }
        art = self._artwork(pixmap)
        if art is not None:
            self._info[k("MPMediaItemPropertyArtwork", "artwork")] = art
        self._push()

    def set_cover(self, pixmap):
        if not self.available or not self._info:
            return
        art = self._artwork(pixmap)
        if art is not None:
            self._info[self._key("MPMediaItemPropertyArtwork", "artwork")] = art
            self._push()

    def set_playing(self, on: bool):
        if not self.available or on == self._playing:
            return
        now = time.monotonic()
        if self._playing:   # re-anchor the position before macOS stops extrapolating
            self._sent_pos_ms += int((now - self._sent_at) * 1000)
        self._sent_at = now
        self._playing = on
        self._push()

    def set_progress(self, ms: int):
        """Called often; only tell macOS when the position jumps (it extrapolates)."""
        if not self.available or not self._info:
            return
        expected = self._sent_pos_ms + (
            (time.monotonic() - self._sent_at) * 1000 if self._playing else 0)
        if abs(expected - ms) > 2000:
            self._sent_pos_ms, self._sent_at = ms, time.monotonic()
            self._push()
        elif not self._playing:
            self._sent_pos_ms, self._sent_at = ms, time.monotonic()

    def shutdown(self):
        if not self.available:
            return
        try:
            for command, token, _h in self._handlers:
                command.removeTarget_(token)
            self._center().setNowPlayingInfo_(None)
            self._center().setPlaybackState_(STOPPED)
        except Exception as exc:  # noqa: BLE001
            _debug(f"shutdown failed: {exc}")
