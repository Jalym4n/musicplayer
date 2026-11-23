"""Spotify Soloist: Spotify's official headless player, used as the built-in speaker.

Some Spotify accounts (mostly newer ones) can no longer play through librespot,
because Spotify stopped giving it song decryption keys ("error audio key 0 1").
Soloist is Spotify's own player, so it isn't affected.

* Soloist may not be bundled inside other apps. Users download it from Spotify:
  the Settings "download from Spotify" button fetches the official build from Spotify's
  servers, or install with Homebrew:  brew install --cask spotify-soloist
* Each user needs their own Soloist API key (developer.spotify.com/dashboard/soloist).
* First run: pick the speaker once in the Spotify app on a phone on the same Wi-Fi.
  Soloist stores that session and signs in by itself afterwards.
* Builds expire 90 days after they're built (exit code 10). Download again to update.

Docs: https://developer.spotify.com/documentation/soloist
"""
from __future__ import annotations

import io
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from . import config
from .models import PlaybackState, Track
from .speaker import ERROR, MISSING, OFF, READY, STARTING, log_path

PAIR = "pair"            # running, but needs its one-time pairing from a Spotify app
EXE = "soloist.exe" if sys.platform == "win32" else "soloist"
DOWNLOADS_PAGE = "https://developer.spotify.com/documentation/soloist/reference/downloads-and-updates"
KEY_PAGE = "https://developer.spotify.com/dashboard/soloist"
CDN = "https://soloist-builds.spotifycdn.com/"
EXIT_EXPIRED = 10


def build_name() -> str | None:
    """The official build for this computer, or None if Soloist doesn't support it."""
    machine = platform.machine().lower()
    if sys.platform == "darwin":
        return "soloist_release_osx_arm64.tar.gz" if machine in ("arm64", "aarch64") else None
    if sys.platform == "win32":
        return "soloist_release_windows_x86_64.zip" if machine in ("amd64", "x86_64") else None
    if sys.platform.startswith("linux"):
        return {"x86_64": "soloist_release_x86_64.tar.gz", "amd64": "soloist_release_x86_64.tar.gz",
                "aarch64": "soloist_release_arm64.tar.gz", "arm64": "soloist_release_arm64.tar.gz",
                "armv7l": "soloist_release_arm32.tar.gz"}.get(machine)
    return None


def install_dir() -> Path:
    d = config.config_dir() / "soloist"
    d.mkdir(parents=True, exist_ok=True)
    return d


def data_dir() -> Path:
    d = config.config_dir() / "soloist-data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir() -> Path:
    d = config.cache_dir() / "soloist"
    d.mkdir(parents=True, exist_ok=True)
    return d


def find_binary(configured: str = "") -> str:
    if configured and Path(configured).is_file():
        return configured
    candidates = [install_dir() / EXE, Path("/opt/homebrew/bin") / EXE,
                  Path("/usr/local/bin") / EXE]
    for c in candidates:
        if c.is_file():
            return str(c)
    return shutil.which(EXE) or ""


def download(progress=None) -> str:
    """Download the official build from Spotify's servers into the app's folder.

    Blocking: call from a worker thread. Returns the path to the executable."""
    import requests
    name = build_name()
    if not name:
        raise RuntimeError("Spotify Soloist isn't available for this computer "
                           "(it needs an Apple Silicon Mac, 64-bit Windows or Linux).")
    resp = requests.get(CDN + name, timeout=60)
    resp.raise_for_status()
    data = resp.content
    target = install_dir()
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            member = next(m for m in z.namelist() if m.endswith(EXE))
            (target / EXE).write_bytes(z.read(member))
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
            member = next(m for m in t.getmembers()
                          if m.isfile() and Path(m.name).name == EXE)
            (target / EXE).write_bytes(t.extractfile(member).read())
    exe = target / EXE
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    out = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=20)
    if out.returncode not in (0, EXIT_EXPIRED):
        raise RuntimeError(f"downloaded Soloist didn't start: {out.stderr or out.stdout}")
    return str(exe)


def build_args(name: str, key: str) -> list[str]:
    return ["--device-name", name, "--api-key", key,
            "--data-dir", str(data_dir()), "--cache-dir", str(cache_dir()),
            "--cache-size", "500", "--ws", "127.0.0.1:0"]


def parse_event(line: str) -> dict | None:
    """One `soloist ctl trace` line: "<unix_epoch_ms> <json_event>"."""
    line = line.strip()
    if not line:
        return None
    brace = line.find("{")
    if brace < 0:
        return None
    try:
        ev = json.loads(line[brace:])
    except ValueError:
        return None
    return ev if isinstance(ev, dict) else None


# --- turning Soloist's live events into the app's models ------------------------------
_COVER_ORDER = ("large", "default", "xlarge", "small")


def _name(entity: dict | None) -> str:
    return (((entity or {}).get("decorations") or {}).get("identity") or {}).get("name") or ""


def _cover(entity: dict | None) -> str:
    covers = (((entity or {}).get("decorations") or {}).get("visual_identity") or {}).get("cover") or []
    by_size = {c.get("size"): c.get("url") for c in covers if c.get("url")}
    url = next((by_size[k] for k in _COVER_ORDER if by_size.get(k)), "")
    if url.startswith("spotify:image:"):
        url = "https://i.scdn.co/image/" + url.rsplit(":", 1)[1]
    return url


def entity_track(entity: dict | None) -> Track | None:
    """A Soloist Entity (track / episode) as a Track."""
    if not entity or not entity.get("uri") or entity.get("entity_type") not in ("track", "episode"):
        return None
    dec = entity.get("decorations") or {}
    parent = (dec.get("parent") or {}).get("entity") or {}
    artists = ", ".join(n for n in (_name(c) for c in dec.get("creators") or []) if n)
    uri = entity["uri"]
    return Track(id=uri.rsplit(":", 1)[-1], uri=uri, name=_name(entity) or "Untitled",
                 artists=artists or _name(parent) or "Unknown", album=_name(parent),
                 image_url=_cover(entity) or _cover(parent),
                 duration_ms=int((dec.get("playback") or {}).get("duration_ms") or 0))


def position_now(position: dict | None) -> int:
    """Current position from a {position_ms, timestamp_ms, speed} anchor."""
    if not position:
        return 0
    pos = float(position.get("position_ms") or 0)
    speed = float(position.get("speed") or 0)
    ts = position.get("timestamp_ms")
    if ts and speed:
        pos += max(0.0, time.time() * 1000 - float(ts)) * speed
    return int(pos)


def apply_event(state: PlaybackState, ev: dict) -> bool:
    """Update `state` in place from one Soloist event. Returns True if anything changed."""
    kind = ev.get("type")
    if kind == "playback_state":
        state.track = entity_track(ev.get("item")) or state.track
        status = ev.get("status")
        state.is_playing = status in ("playing", "buffering")
        state.progress_ms = position_now(ev.get("position"))
        if isinstance(ev.get("volume"), (int, float)):
            state.volume = int(ev["volume"])
        opts = ev.get("options") or {}
        state.shuffle = bool(opts.get("shuffle", state.shuffle))
        state.repeat = opts.get("repeat") or state.repeat
        ctx = ev.get("context") or {}
        state.context_uri = ctx.get("uri") or state.context_uri
        if status == "idle":
            state.track, state.is_playing = None, False
        return True
    if kind == "track_changed":
        t = entity_track(ev.get("item"))
        if t:
            state.track = t
            state.progress_ms = 0
            return True
        return False
    if kind == "playback_changed":
        state.is_playing = ev.get("status") in ("playing", "buffering")
        return True
    if kind == "position_sync":
        state.progress_ms = position_now(ev.get("position"))
        speed = (ev.get("position") or {}).get("speed")
        if speed is not None:
            state.is_playing = float(speed) > 0
        return True
    if kind == "volume_changed" and isinstance(ev.get("volume"), (int, float)):
        state.volume = int(ev["volume"])
        return True
    if kind == "options_changed":
        opts = ev.get("options") or {}
        state.shuffle = bool(opts.get("shuffle", state.shuffle))
        state.repeat = opts.get("repeat") or state.repeat
        return True
    if kind == "context_changed":
        state.context_uri = (ev.get("context") or {}).get("uri") or state.context_uri
        return True
    return False


def queue_tracks(ev: dict) -> list[Track]:
    """Upcoming songs from a queue_changed event (next first)."""
    out = []
    for entry in ev.get("upcoming") or []:
        t = entity_track(entry.get("item"))
        if t:
            out.append(t)
    return out


class SoloistSpeaker(QObject):
    """Runs Soloist in the background. Same signals and phases as speaker.Speaker."""
    phaseChanged = Signal(str, str)
    loginUrl = Signal(str)   # unused (Soloist pairs through a Spotify app), kept for parity
    playerEvent = Signal(dict)   # playback_state, track_changed, position_sync, ...

    MAX_FAILURES = 3
    engine = "soloist"

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.name = name
        self.binary = ""
        self.key = ""
        self.proc: QProcess | None = None
        self.phase = OFF
        self.detail = ""
        self.blocked = False      # parity with Speaker (librespot key refusal)
        self._failures = 0
        self._stopping = False
        self._started_at = 0.0
        self._tail: list[str] = []
        self._status_proc: QProcess | None = None
        self._buf = ""
        self._status = QTimer(self)
        self._status.timeout.connect(self._check_status)

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.state() != QProcess.ProcessState.NotRunning

    def start(self, binary: str, key: str = "") -> None:
        self.binary, self.key = binary, key.strip()
        if not binary:
            self._set(MISSING, "Spotify Soloist isn't installed yet: tap to set it up")
            return
        if not self.key:
            self._set(MISSING, "add your Soloist key in Settings")
            return
        if self.running:
            return
        self._failures = 0
        self._launch()

    def restart(self) -> None:
        self.stop()
        self.start(self.binary, self.key)

    def stop(self) -> None:
        self._stopping = True
        self._status.stop()
        if self._status_proc and self._status_proc.state() != QProcess.ProcessState.NotRunning:
            self._status_proc.kill()
        if self.running:
            self.proc.terminate()
            if not self.proc.waitForFinished(3000):
                self.proc.kill()
                self.proc.waitForFinished(1000)
        self._stopping = False

    def forget_login(self) -> None:
        """Drop the stored pairing; the next start asks to pair again."""
        self.stop()
        shutil.rmtree(data_dir(), ignore_errors=True)

    def activate(self) -> bool:
        """Make Soloist the active Spotify device (blocking; call from a worker)."""
        try:
            out = subprocess.run([self.binary, "ctl", "activate", "--data-dir", str(data_dir())],
                                 capture_output=True, text=True, timeout=8)
            return out.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    # -- internals ----------------------------------------------------------------------
    def _set(self, phase: str, detail: str = "") -> None:
        if (phase, detail) == (self.phase, self.detail):
            return
        self.phase, self.detail = phase, detail
        self.phaseChanged.emit(phase, detail)

    def _log(self, line: str) -> None:
        if self.key:
            line = line.replace(self.key, "<api-key>")
        try:
            with log_path().open("a", encoding="utf-8") as f:
                f.write(line.rstrip("\n") + "\n")
        except OSError:
            pass
        if os.environ.get("PINKIE_DEBUG"):
            print("[soloist]", line, file=sys.stderr)

    def _launch(self) -> None:
        self._tail = []
        self._log(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} starting Spotify Soloist "
                  f"{self.binary} as '{self.name}'")
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(self._proc_error)
        self._started_at = time.monotonic()
        self._set(STARTING, "warming up Spotify Soloist")
        self.proc.start(self.binary, build_args(self.name, self.key))
        self._status.start(1000)

    def _read(self) -> None:
        if not self.proc:
            return
        text = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        for line in text.splitlines():
            self._tail = (self._tail + [line])[-40:]
            self._log(line)

    def _check_status(self) -> None:
        """Keep a `soloist ctl trace` running: it streams auth_state events as JSON."""
        if not self.running:
            return
        if self._status_proc and self._status_proc.state() != QProcess.ProcessState.NotRunning:
            if self.phase == STARTING and time.monotonic() - self._started_at > 20:
                self._set(PAIR, self._pair_text())
            return
        if not (data_dir() / "ws.port").exists() and not (data_dir() / "ws.addr").exists():
            return  # daemon hasn't opened its local API yet
        p = QProcess(self)
        p.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self._buf = ""
        p.readyReadStandardOutput.connect(lambda: self._trace_read(p))
        self._status_proc = p
        p.start(self.binary, ["ctl", "trace", "--data-dir", str(data_dir())])

    def _pair_text(self) -> str:
        return f"pair once: on your phone open Spotify \u2192 devices \u2192 {self.name}"

    def _trace_read(self, p: QProcess) -> None:
        self._buf += bytes(p.readAllStandardOutput()).decode("utf-8", "replace")
        *lines, self._buf = self._buf.split("\n")
        for line in lines:
            ev = parse_event(line)
            if not ev or not self.running:
                continue
            if ev.get("type") != "auth_state":
                self.playerEvent.emit(ev)   # live playback updates for the UI
                continue
            if ev.get("logged_in"):
                self._failures = 0
                self._set(READY, "music comes out of your speakers \u2661")
            else:
                self._set(PAIR, self._pair_text())

    def _proc_error(self, err) -> None:
        if err == QProcess.ProcessError.FailedToStart:
            self._failures = self.MAX_FAILURES + 1
            self._log(f"failed to start: {self.proc.errorString() if self.proc else ''}")
            self._set(ERROR, "couldn't start Spotify Soloist  · tap to retry")

    def _finished(self, code: int = 0, status=None) -> None:
        self._status.stop()
        if self._status_proc and self._status_proc.state() != QProcess.ProcessState.NotRunning:
            self._status_proc.kill()
        self._log(f"--- Soloist exited (code {code})")
        if self._stopping:
            self._set(OFF, "speaker off")
            return
        if self._failures > self.MAX_FAILURES:
            return
        log = "\n".join(self._tail)
        if code == EXIT_EXPIRED:
            self._set(ERROR, "this Soloist build expired: Settings → download from Spotify")
            return
        if "already using the data directory" in log:
            self._set(ERROR, "another Soloist is already running (close it, then tap)")
            return
        self._failures += 1
        if self._failures > self.MAX_FAILURES:
            last = next((ln.strip() for ln in reversed(self._tail) if ln.strip()), "")
            self._set(ERROR, (f"Soloist stopped: {last[-120:]}" if last else
                              f"Soloist stopped (code {code})") + "  · tap to retry")
            return
        self._set(STARTING, "restarting Spotify Soloist")
        QTimer.singleShot(1500 * self._failures, self._launch)
