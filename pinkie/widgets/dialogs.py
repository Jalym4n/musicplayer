"""First-run setup and settings dialog."""
from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout)

from .. import config, theme
from ..speaker import find_binary, log_path
from ..theme import C

DASHBOARD = "https://developer.spotify.com/dashboard"


def _wrap(label: QLabel, width: int = 548) -> None:
    """Word-wrap and reserve the real wrapped height (Qt under-sizes rich text)."""
    label.setWordWrap(True)
    label.setMinimumHeight(label.heightForWidth(width) + 4)


class SettingsDialog(QDialog):
    LOGOUT = 2
    RESET_SPEAKER = 3

    def __init__(self, settings: config.Settings, first_run: bool = False, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Pinkie Player setup" if first_run else "Pinkie Player settings")
        self.setFixedWidth(600)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 22)
        lay.setSpacing(10)

        title = QLabel("hi bestie! let's connect Spotify ♡" if first_run else "settings ♡")
        title.setFont(theme.heading(22, True))
        title.setStyleSheet(f"color:{C.hot};")
        lay.addWidget(title)

        steps = QLabel(
            "1. Open the Spotify Developer Dashboard and click <b>Create app</b>.<br>"
            "2. Any name works. Tick <b>Web API</b>.<br>"
            "3. Add this exact <b>Redirect URI</b>:<br>"
            f"&nbsp;&nbsp;&nbsp;<b style='color:{C.hot}'>{config.REDIRECT_URI}</b><br>"
            "4. Save, then copy the app's <b>Client ID</b> into the box below.<br>"
            "<i>Your Spotify account must be Premium. No client secret needed.</i>")
        steps.setTextFormat(Qt.TextFormat.RichText)
        _wrap(steps)
        lay.addWidget(steps)
        links = QHBoxLayout()
        b_dash = QPushButton("open dashboard")
        b_dash.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(DASHBOARD)))
        b_copy = QPushButton("copy redirect URI")
        b_copy.clicked.connect(lambda: (QGuiApplication.clipboard().setText(config.REDIRECT_URI),
                                        b_copy.setText("copied ♡")))
        links.addWidget(b_dash)
        links.addWidget(b_copy)
        links.addStretch(1)
        lay.addLayout(links)

        lay.addWidget(QLabel("Client ID"))
        self.client_id = QLineEdit(settings.client_id)
        self.client_id.setPlaceholderText("32 letters and numbers")
        self.client_id.textChanged.connect(self._validate)
        lay.addWidget(self.client_id)

        lay.addSpacing(6)
        sp = QLabel("built-in speaker")
        sp.setFont(theme.heading(15, True))
        sp.setStyleSheet(f"color:{C.hot};")
        lay.addWidget(sp)
        found = find_binary(settings.librespot_path)
        hint = QLabel(
            "Music plays straight out of this computer's speakers or headphones. "
            + ("<b>Ready ♡</b>" if found else
               "<b>Not found.</b> Use the downloadable app, or run "
               "<b>python scripts/build_librespot.py</b> once."))
        hint.setObjectName("hint")
        hint.setTextFormat(Qt.TextFormat.RichText)
        _wrap(hint)
        lay.addWidget(hint)
        row = QHBoxLayout()
        self.lib_path = QLineEdit(settings.librespot_path)
        self.lib_path.setPlaceholderText(found or "librespot location (advanced)")
        browse = QPushButton("browse")
        browse.clicked.connect(self._browse)
        row.addWidget(self.lib_path, 1)
        row.addWidget(browse)
        lay.addLayout(row)
        if not first_run:
            tools = QHBoxLayout()
            b_log = QPushButton("open speaker log")
            b_log.setToolTip(str(log_path()))
            b_log.clicked.connect(self._open_log)
            b_reset = QPushButton("reset speaker login")
            b_reset.setToolTip("Forget the speaker's saved login and sign it in again")
            b_reset.clicked.connect(lambda: self.done(self.RESET_SPEAKER))
            tools.addWidget(b_log)
            tools.addWidget(b_reset)
            tools.addStretch(1)
            lay.addLayout(tools)

        lay.addSpacing(8)
        btns = QHBoxLayout()
        if not first_run:
            logout = QPushButton("log out")
            logout.clicked.connect(lambda: self.done(self.LOGOUT))
            btns.addWidget(logout)
        btns.addStretch(1)
        cancel = QPushButton("cancel")
        cancel.clicked.connect(self.reject)
        self.ok = QPushButton("let's go!" if first_run else "save")
        self.ok.setObjectName("primary")
        self.ok.clicked.connect(self._accept)
        btns.addWidget(cancel)
        btns.addWidget(self.ok)
        lay.addLayout(btns)
        self._validate()

    def _validate(self):
        ok = bool(re.fullmatch(r"[0-9a-fA-F]{32}", self.client_id.text().strip()))
        self.ok.setEnabled(ok)

    def _open_log(self):
        path = log_path()
        if not path.exists():
            path.write_text("(the speaker hasn't written anything yet)\n", "utf-8")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Find librespot")
        if path:
            self.lib_path.setText(path)

    def _accept(self):
        self.settings.client_id = self.client_id.text().strip()
        self.settings.librespot_path = self.lib_path.text().strip()
        self.settings.save()
        self.accept()
