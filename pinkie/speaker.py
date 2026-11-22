"""The built-in speaker: Pinkie Player plays Spotify straight out of this computer.

Spotify doesn't let apps fetch audio through its public API, so the app ships with
librespot (https://github.com/librespot-org/librespot), an open-source Spotify Connect
player that needs Premium. Pinkie Player starts it in the background, registers it on
your account as "Pinkie Player", and sends every song to it. No official Spotify app,
phone or browser is involved in playback.

Login, in order of preference:
1. credentials librespot cached on an earlier run (normal case after the first time);
2. the access token from Pinkie Player's own login (no second browser tab), passed via
   an environment variable so it never shows up in the process list;
3. librespot's own one-time browser login (``--enable-oauth``), used only if Spotify
   rejects option 2.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from . import config

EXE = "librespot.exe" if sys.platform == "win32" else "librespot"

# Phases the UI shows
MISSING, STARTING, LOGIN, READY, ERROR, OFF = (
    "missing", "starting", "login", "ready", "error", "off")


def bundled_dirs() -> list[Path]:
    dirs = []
    if getattr(sys, "frozen", False):  # PyInstaller bundle
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        dirs += [base / "librespot", base, Path(sys.executable).parent]
    dirs.append(Path(__file__).resolve().parent / "bin")  # scripts/build_librespot.py
    return dirs


def find_binary(configured: str = "") -> str:
    if configured and Path(configured).is_file():
        return configured
    for d in bundled_dirs():
        if (d / EXE).is_file():
            return str(d / EXE)
    found = shutil.which(EXE)
    if found:
        return found
    for cand in (Path.home() / ".cargo" / "bin" / EXE, Path("/opt/homebrew/bin") / EXE,
                 Path("/usr/local/bin") / EXE):
        if cand.is_file():
            return str(cand)
    return ""


def cache_dir() -> Path:
    d = config.config_dir() / "librespot"
    d.mkdir(parents=True, exist_ok=True)
    return d


def has_cached_login() -> bool:
    return (cache_dir() / "credentials.json").is_file()


def build_args(name: str, oauth: bool) -> list[str]:
    args = [
        "--name", name,
        "--device-type", "computer",
        "--cache", str(cache_dir()),
        "--cache-size-limit", "1G",
        "--disable-discovery",          # only your account can see this speaker
        "--bitrate", "320",
        "--initial-volume", "70",
        "--enable-volume-normalisation",
    ]
    if oauth:
        args.append("--enable-oauth")   # cached credentials still win when present
    return args


_AUTH_FAIL = re.compile(r"(BadCredentials|bad credentials|authentication failed|"
                        r"could not initialize spirc|Failed to get Spotify access token|"
                        r"PermissionDenied|Login failed)", re.I)
_NO_AUDIO = re.compile(r"(mk_rodio|NoDeviceAvailable|DeviceNotAvailable|"
                       r"no output device|Unable to open audio)", re.I)
_AUTH_OK = re.compile(r"Authenticated as", re.I)
_URL = re.compile(r"https://accounts\.spotify\.com/\S+")


class Speaker(QObject):
    phaseChanged = Signal(str, str)   # phase, human-readable detail
    loginUrl = Signal(str)

    MAX_RESTARTS = 3

    def __init__(self, name: str = config.APP_NAME, parent=None):
        super().__init__(parent)
        self.name = name
        self.binary = ""
        self.proc: QProcess | None = None
        self.phase = OFF
        self.detail = ""
        self._mode = ""            # cached | token | oauth
        self._token = ""
        self._restarts = 0
        self._started_at = 0.0
        self._tail: list[str] = []
        self._stopping = False

    # -- public -----------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.state() != QProcess.ProcessState.NotRunning

    def start(self, binary: str, access_token: str = "", token_scopes: str = "") -> None:
        self.binary = binary
        if not binary:
            self._set(MISSING, "the built-in speaker (librespot) isn't installed")
            return
        if self.running:
            return
        self._token = access_token if "streaming" in token_scopes.split() else ""
        if has_cached_login():
            self._launch("cached")
        elif self._token:
            self._launch("token")
        else:
            self._launch("oauth")

    def stop(self) -> None:
        self._stopping = True
        if self.running:
            self.proc.terminate()
            if not self.proc.waitForFinished(2500):
                self.proc.kill()
                self.proc.waitForFinished(1000)
        self._stopping = False

    def forget_login(self) -> None:
        self.stop()
        try:
            (cache_dir() / "credentials.json").unlink()
        except FileNotFoundError:
            pass

    # -- internals ----------------------------------------------------------------------
    def _set(self, phase: str, detail: str = "") -> None:
        self.phase, self.detail = phase, detail
        self.phaseChanged.emit(phase, detail)

    def _launch(self, mode: str) -> None:
        self._mode = mode
        self._tail = []
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        env = QProcessEnvironment.systemEnvironment()
        env.remove("LIBRESPOT_ACCESS_TOKEN")
        if mode == "token":
            env.insert("LIBRESPOT_ACCESS_TOKEN", self._token)
        self.proc.setProcessEnvironment(env)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(self._proc_error)
        self._started_at = time.monotonic()
        self._set(STARTING, "warming up the speaker")
        self.proc.start(self.binary, build_args(self.name, oauth=(mode == "oauth")))
        if mode == "token":
            proc = self.proc
            QTimer.singleShot(25000, lambda: self._token_timeout(proc))

    def _token_timeout(self, proc: QProcess) -> None:
        # Token login neither worked nor failed loudly: fall back to the browser login.
        if proc is self.proc and self._mode == "token" and self.phase != READY:
            self._mode = "token-timeout"
            proc.kill()

    def _read(self) -> None:
        if not self.proc:
            return
        text = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        for line in text.splitlines():
            self._tail = (self._tail + [line])[-30:]
            if os.environ.get("PINKIE_DEBUG"):
                print("[librespot]", line, file=sys.stderr)
            if _AUTH_OK.search(line):
                self._restarts = 0
                self._set(READY, "music comes out of your speakers ♡")
            m = _URL.search(line)
            if m and self.phase != READY:
                self._set(LOGIN, "one-time login for the speaker: check your browser")
                self.loginUrl.emit(m.group(0))

    def _proc_error(self, err) -> None:
        if err == QProcess.ProcessError.FailedToStart:
            self._set(ERROR, f"couldn't start the speaker ({self.binary})")

    def _finished(self, *_):
        if self._stopping:
            self._set(OFF)
            return
        log = "\n".join(self._tail)
        if _NO_AUDIO.search(log):
            self._set(ERROR, "no sound output found: plug in speakers or headphones, "
                             "then tap here")
            return
        auth_failed = bool(_AUTH_FAIL.search(log))
        if self._mode in ("token", "token-timeout"):
            # Spotify didn't accept the app's token for streaming: use librespot's own
            # one-time browser login instead.
            QTimer.singleShot(300, lambda: self._launch("oauth"))
            return
        if self._mode == "cached" and auth_failed:
            self.forget_login()
            QTimer.singleShot(300, lambda: self._launch("token" if self._token else "oauth"))
            return
        if self._restarts < self.MAX_RESTARTS and self.phase != ERROR:
            self._restarts += 1
            delay = 1000 * self._restarts
            self._set(STARTING, "the speaker hiccuped, restarting")
            QTimer.singleShot(delay, lambda: self._launch(
                "cached" if has_cached_login() else ("token" if self._token else "oauth")))
            return
        last = next((ln for ln in reversed(self._tail) if ln.strip()), "")
        self._set(ERROR, f"speaker stopped: {last[-160:]}" if last else "speaker stopped")
