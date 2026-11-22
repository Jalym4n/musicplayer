"""Optional: make Pinkie Player itself a Spotify speaker using librespot.

librespot (https://github.com/librespot-org/librespot) is an open-source Spotify Connect
receiver that needs Premium. When its binary is installed, the app starts it in the
background, so music plays straight out of this computer without the official Spotify
app. Without it, Pinkie Player remote-controls any Spotify device (phone, desktop app,
speaker) through Spotify Connect.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal

from . import config

_URL_RE = re.compile(r"https://accounts\.spotify\.com/\S+")


def find_binary(configured: str = "") -> str:
    if configured and Path(configured).is_file():
        return configured
    name = "librespot.exe" if sys.platform == "win32" else "librespot"
    found = shutil.which(name)
    if found:
        return found
    for cand in (Path.home() / ".cargo" / "bin" / name, Path("/opt/homebrew/bin") / name,
                 Path("/usr/local/bin") / name):
        if cand.is_file():
            return str(cand)
    return ""


class LibrespotManager(QObject):
    loginUrl = Signal(str)   # first run: librespot wants a one-time browser login
    log = Signal(str)
    stopped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc: QProcess | None = None
        self.device_name = config.APP_NAME
        self._tail: list[str] = []

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.state() != QProcess.ProcessState.NotRunning

    def start(self, binary: str, device_name: str) -> bool:
        if self.running or not binary:
            return self.running
        self.device_name = device_name
        cache = config.config_dir() / "librespot"
        cache.mkdir(parents=True, exist_ok=True)
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._finished)
        args = [
            "--name", device_name,
            "--cache", str(cache),
            "--enable-oauth",       # one-time browser login, then cached credentials
            "--bitrate", "320",
            "--initial-volume", "70",
            "--device-type", "computer",
        ]
        self.proc.start(binary, args)
        return self.proc.waitForStarted(3000)

    def stop(self) -> None:
        if self.running:
            self.proc.terminate()
            if not self.proc.waitForFinished(2000):
                self.proc.kill()

    def _read(self):
        text = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        for line in text.splitlines():
            self._tail = (self._tail + [line])[-20:]
            self.log.emit(line)
            m = _URL_RE.search(line)
            if m:
                self.loginUrl.emit(m.group(0))

    def _finished(self, *_):
        self.stopped.emit("\n".join(self._tail[-5:]))
