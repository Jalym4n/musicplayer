"""The built-in speaker: Pinkie Player plays Spotify straight out of this computer.

Spotify doesn't let apps fetch audio through its public API, so the app ships with
librespot (https://github.com/librespot-org/librespot), an open-source Spotify Connect
player that needs Premium. Pinkie Player starts it in the background, registers it on
your account as "Pinkie Player", and sends every song to it. No official Spotify app,
phone or browser is involved in playback.

Login: the first time, librespot opens its own Spotify login page in the browser
(``--enable-oauth``). It then saves reusable credentials in its cache folder, and every
later launch signs in silently with those.

Everything librespot prints goes to ``speaker.log`` in the app's config folder, so
problems can be diagnosed (Settings -> open speaker log).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from . import config

EXE = "librespot.exe" if sys.platform == "win32" else "librespot"

# Phases the UI shows
MISSING, STARTING, LOGIN, READY, ERROR, OFF = (
    "missing", "starting", "login", "ready", "error", "off")

# Written next to librespot's credentials once its own browser login has worked.
# Credentials without it were saved by older builds (which signed the speaker in with
# the app's Web API token, which Spotify doesn't fully accept) and get thrown away.
MARKER = "pinkie-login.json"
LOG_MAX_BYTES = 512 * 1024
STABLE_SECONDS = 60      # a run this long counts as healthy and resets the failure count


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


def log_path() -> Path:
    return config.config_dir() / "speaker.log"


def has_cached_login() -> bool:
    return (cache_dir() / "credentials.json").is_file() and (cache_dir() / MARKER).is_file()


def forget_cached_login() -> None:
    for name in ("credentials.json", MARKER):
        try:
            (cache_dir() / name).unlink()
        except FileNotFoundError:
            pass


def drop_stale_login() -> bool:
    """Delete credentials saved by an older build's token sign-in. True if removed."""
    creds = cache_dir() / "credentials.json"
    if creds.is_file() and not (cache_dir() / MARKER).is_file():
        forget_cached_login()
        return True
    return False


def build_args(name: str) -> list[str]:
    return [
        "--name", name,
        "--device-type", "computer",
        "--cache", str(cache_dir()),
        "--cache-size-limit", "1G",
        "--disable-discovery",          # only your account can see this speaker
        "--bitrate", "320",
        "--initial-volume", "70",
        "--enable-volume-normalisation",
        "--enable-oauth",               # first run: browser login; later: cached login
    ]


_AUTH_FAIL = re.compile(r"(BadCredentials|bad credentials|Invalid Credentials|"
                        r"authentication failed|could not initialize spirc|"
                        r"Spirc shut down too often|login5|PermissionDenied|"
                        r"Failed to get Spotify access token)", re.I)
_NO_AUDIO = re.compile(r"(mk_rodio|NoDeviceAvailable|DeviceNotAvailable|"
                       r"no output device|Unable to open audio)", re.I)
_AUTH_OK = re.compile(r"Authenticated as", re.I)
_URL = re.compile(r"https://accounts\.spotify\.com/\S+")
_NOISE = re.compile(r"^\s*(\d+:|at |note:|stack backtrace)", re.I)


class Speaker(QObject):
    phaseChanged = Signal(str, str)   # phase, human-readable detail
    loginUrl = Signal(str)

    MAX_FAILURES = 3

    def __init__(self, name: str = config.APP_NAME, parent=None):
        super().__init__(parent)
        self.name = name
        self.binary = ""
        self.proc: QProcess | None = None
        self.phase = OFF
        self.detail = ""
        self._failures = 0
        self._ready_at = 0.0
        self._tail: list[str] = []
        self._stopping = False

    # -- public -----------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.state() != QProcess.ProcessState.NotRunning

    def start(self, binary: str) -> None:
        self.binary = binary
        if not binary:
            self._set(MISSING, "the built-in speaker (librespot) isn't installed")
            return
        if self.running:
            return
        if drop_stale_login():
            self._log("removed an old saved speaker login; a fresh login is needed")
        self._failures = 0
        self._launch()

    def restart(self) -> None:
        self.stop()
        self.start(self.binary)

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
        forget_cached_login()

    # -- internals ----------------------------------------------------------------------
    def _set(self, phase: str, detail: str = "") -> None:
        self.phase, self.detail = phase, detail
        self.phaseChanged.emit(phase, detail)

    def _log(self, line: str) -> None:
        try:
            with log_path().open("a", encoding="utf-8") as f:
                f.write(line.rstrip("\n") + "\n")
        except OSError:
            pass
        if os.environ.get("PINKIE_DEBUG"):
            print("[speaker]", line, file=sys.stderr)

    def _launch(self) -> None:
        self._tail = []
        self._ready_at = 0.0
        try:
            if log_path().exists() and log_path().stat().st_size > LOG_MAX_BYTES:
                log_path().unlink()
        except OSError:
            pass
        args = build_args(self.name)
        self._log(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} starting {self.binary} "
                  f"({'saved login' if has_cached_login() else 'browser login'})")
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(self._proc_error)
        self._set(STARTING, "warming up the speaker")
        self.proc.start(self.binary, args)

    def _read(self) -> None:
        if not self.proc:
            return
        text = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        for line in text.splitlines():
            self._tail = (self._tail + [line])[-40:]
            self._log(line)
            if _AUTH_OK.search(line):
                self._ready_at = time.monotonic()
                self._write_marker()
                self._set(READY, "music comes out of your speakers ♡")
            m = _URL.search(line)
            if m and self.phase != READY:
                self._set(LOGIN, "one-time login for the speaker: check your browser")
                self.loginUrl.emit(m.group(0))

    def _write_marker(self) -> None:
        if (cache_dir() / MARKER).exists():
            return
        try:
            (cache_dir() / MARKER).write_text(json.dumps({"method": "librespot-oauth"}))
        except OSError:
            pass

    def _proc_error(self, err) -> None:
        if err == QProcess.ProcessError.FailedToStart:
            self._log(f"failed to start: {self.proc.errorString() if self.proc else ''}")
            self._failures = self.MAX_FAILURES
            self._set(ERROR, f"couldn't start the speaker: "
                             f"{self.proc.errorString() if self.proc else self.binary}")

    def _finished(self, code: int = 0, status=None) -> None:
        crashed = status == QProcess.ExitStatus.CrashExit
        self._log(f"--- speaker exited (code {code}{', crashed' if crashed else ''})")
        if self._stopping:
            self._set(OFF, "speaker off")
            return
        if self.phase == ERROR and self._failures >= self.MAX_FAILURES:
            return  # FailedToStart already reported
        log = "\n".join(self._tail)
        if _NO_AUDIO.search(log):
            self._set(ERROR, "no sound output found: plug in speakers or headphones, "
                             "then tap here")
            return
        healthy = self._ready_at and time.monotonic() - self._ready_at > STABLE_SECONDS
        self._failures = 0 if healthy else self._failures + 1
        # A saved login that keeps failing is useless: drop it so the next start asks
        # for a fresh browser login instead of looping.
        if not healthy and has_cached_login() and (_AUTH_FAIL.search(log)
                                                   or self._failures >= 2):
            self._log("saved speaker login isn't working; asking for a fresh login")
            forget_cached_login()
        if self._failures > self.MAX_FAILURES:
            last = next((ln.strip() for ln in reversed(self._tail)
                         if ln.strip() and not _NOISE.search(ln)), "")
            if crashed and not last:
                detail = "the speaker crashed right away (see Settings > speaker log)"
            else:
                detail = f"speaker stopped: {last[-140:]}" if last else \
                    f"speaker stopped (code {code})"
            self._set(ERROR, detail + "  · tap to retry")
            return
        self._set(STARTING, "restarting the speaker")
        QTimer.singleShot(1200 * self._failures, self._launch)
