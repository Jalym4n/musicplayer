"""User settings and token storage, kept in the OS's normal app-config folder."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import personal

APP_NAME = "Pinkie Player"
APP_SLUG = "pinkie-player"

REDIRECT_PORT = 8898
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback"

SCOPES = [
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-library-read",
    "user-read-recently-played",
]


def config_dir() -> Path:
    """Per-user config folder: %APPDATA% on Windows, ~/Library/Application Support on
    macOS, $XDG_CONFIG_HOME or ~/.config elsewhere."""
    override = os.environ.get("PINKIE_CONFIG_DIR")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_NAME
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_SLUG
    base.mkdir(parents=True, exist_ok=True)
    return base


def cache_dir() -> Path:
    d = config_dir() / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Settings:
    client_id: str = ""
    # Override for the built-in speaker binary (librespot). Empty = use the bundled one.
    librespot_path: str = ""
    device_name: str = ""        # empty = "<name>'s Player"
    owner_name: str = ""         # empty = personal.NAME
    favorites: list = field(default_factory=list)   # starred playlist ids
    # Built-in speaker: "auto" (Soloist when set up, else librespot), "soloist", "librespot"
    speaker_engine: str = "auto"
    soloist_path: str = ""        # empty = auto-detect (app folder, Homebrew, PATH)
    soloist_key: str = ""         # the user's own key from developer.spotify.com/dashboard/soloist
    librespot_blocked: bool = False   # Spotify refused song keys to librespot here
    # Mini-Player
    mini_open: bool = False           # reopen it on launch
    mini_pos: list = field(default_factory=list)   # [x, y] where she last put it
    mini_style: str = "classic"       # classic | cassette
    mini_on_top: bool = True
    mini_on_minimize: bool = True     # pop it up when the big window is minimized
    poll_seconds: float = 2.5
    extra: dict = field(default_factory=dict)

    @property
    def her_name(self) -> str:
        return (self.owner_name or personal.NAME).strip() or personal.NAME

    @property
    def speaker_name(self) -> str:
        # Older builds saved "Pinkie Player" here; treat that as "use the default".
        if self.device_name and self.device_name != APP_NAME:
            return self.device_name
        return personal.speaker_name(self.her_name)

    @classmethod
    def path(cls) -> Path:
        return config_dir() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        p = cls.path()
        if not p.exists():
            return cls()
        try:
            data = json.loads(p.read_text("utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def save(self) -> None:
        _write_private(self.path(), json.dumps(asdict(self), indent=2))


def _write_private(path: Path, text: str) -> None:
    """Write a file readable only by the current user (tokens live here)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, "utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def token_path() -> Path:
    return config_dir() / "token.json"


def load_token() -> dict | None:
    p = token_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def save_token(token: dict) -> None:
    _write_private(token_path(), json.dumps(token, indent=2))


def clear_token() -> None:
    try:
        token_path().unlink()
    except FileNotFoundError:
        pass
