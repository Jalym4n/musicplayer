"""First-run setup and settings dialog."""
from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout)

from .. import config, soloist, theme
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

        name = settings.her_name
        title = QLabel(f"hi {name}! let's connect Spotify \U0001F9A6" if first_run
                       else "settings \u2661")
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

        nrow = QHBoxLayout()
        nrow.addWidget(QLabel("who's this player for?"))
        self.owner = QLineEdit(settings.owner_name or name)
        self.owner.setPlaceholderText(name)
        nrow.addWidget(self.owner, 1)
        lay.addLayout(nrow)

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
        erow = QHBoxLayout()
        erow.addWidget(QLabel("play through"))
        self.engine = QComboBox()
        self.engine.addItem("automatic (recommended)", "auto")
        self.engine.addItem("Spotify Soloist (official)", "soloist")
        self.engine.addItem("librespot (open source)", "librespot")
        self.engine.setCurrentIndex(max(0, self.engine.findData(settings.speaker_engine)))
        erow.addWidget(self.engine, 1)
        lay.addLayout(erow)

        sol = soloist.find_binary(settings.soloist_path)
        hint = QLabel(
            "<b>Spotify Soloist</b> is Spotify's own player with no window. It works on every "
            "account. One-time setup: download it, paste your free Soloist key, then pick "
            f"<b>{settings.speaker_name}</b> once in the Spotify app on your phone. "
            + ("<b>Soloist found \u2661</b>" if sol else "<b>Soloist not installed yet.</b>"))
        hint.setObjectName("hint")
        hint.setTextFormat(Qt.TextFormat.RichText)
        _wrap(hint)
        lay.addWidget(hint)
        krow = QHBoxLayout()
        self.sol_key = QLineEdit(settings.soloist_key)
        self.sol_key.setPlaceholderText("Soloist key")
        self.sol_key.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        b_key = QPushButton("get my key")
        b_key.setToolTip("Opens Spotify for Developers. Log in with the Premium account.")
        b_key.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(soloist.KEY_PAGE)))
        krow.addWidget(self.sol_key, 1)
        krow.addWidget(b_key)
        lay.addLayout(krow)
        drow = QHBoxLayout()
        self.b_dl = QPushButton("update Soloist" if sol else "download Soloist from Spotify")
        self.b_dl.setToolTip("Downloads the official build straight from Spotify's servers")
        self.b_dl.clicked.connect(self._download_soloist)
        self.dl_status = QLabel("")
        self.dl_status.setObjectName("hint")
        b_page = QPushButton("Spotify's download page")
        b_page.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(soloist.DOWNLOADS_PAGE)))
        drow.addWidget(self.b_dl)
        drow.addWidget(b_page)
        drow.addStretch(1)
        lay.addLayout(drow)
        lay.addWidget(self.dl_status)
        if not soloist.build_name():
            self.b_dl.setEnabled(False)
            self.dl_status.setText("Soloist needs an Apple Silicon Mac, 64-bit Windows or Linux.")

        row = QHBoxLayout()
        self.lib_path = QLineEdit(settings.librespot_path)
        found = find_binary(settings.librespot_path)
        self.lib_path.setPlaceholderText(found or "librespot location (advanced)")
        browse = QPushButton("browse")
        browse.clicked.connect(self._browse)
        row.addWidget(QLabel("librespot"))
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

    def _download_soloist(self):
        from ..worker import run_async
        self.b_dl.setEnabled(False)
        self.dl_status.setText("downloading Spotify Soloist from Spotify \u2661 ...")

        def done(path):
            self.settings.soloist_path = ""
            self.dl_status.setText(f"Soloist installed \u2661  ({path})")
            self.b_dl.setText("update Soloist")
            self.b_dl.setEnabled(True)

        def fail(exc):
            self.dl_status.setText(f"download failed: {exc}")
            self.b_dl.setEnabled(True)

        run_async(soloist.download, on_done=done, on_error=fail)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Find librespot")
        if path:
            self.lib_path.setText(path)

    def _accept(self):
        self.settings.client_id = self.client_id.text().strip()
        self.settings.owner_name = self.owner.text().strip()
        self.settings.speaker_engine = self.engine.currentData()
        self.settings.soloist_key = self.sol_key.text().strip()
        self.settings.librespot_path = self.lib_path.text().strip()
        self.settings.save()
        self.accept()
