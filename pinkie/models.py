"""Plain data objects the UI works with, independent of Spotify's JSON shapes."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Track:
    id: str
    uri: str
    name: str
    artists: str
    album: str
    image_url: str = ""
    duration_ms: int = 0
    is_local: bool = False
    year: str = ""

    @property
    def duration_text(self) -> str:
        return fmt_ms(self.duration_ms)


@dataclass
class Playlist:
    id: str
    name: str
    uri: str = ""
    image_url: str = ""
    total: int = 0
    owner: str = ""
    # Spotify only lets third-party apps list the songs of playlists you own or
    # collaborate on. Others can still be played as a whole.
    readable: bool = True
    kind: str = "playlist"  # playlist | liked | recent | search


@dataclass
class Device:
    id: str
    name: str
    type: str = ""
    is_active: bool = False
    volume: int | None = None


@dataclass
class PlaybackState:
    is_playing: bool = False
    track: Track | None = None
    progress_ms: int = 0
    shuffle: bool = False
    repeat: str = "off"  # off | context | track
    volume: int | None = None
    device: Device | None = None
    context_uri: str = ""
    extra: dict = field(default_factory=dict)


def fmt_ms(ms: int) -> str:
    s = max(0, int(ms) // 1000)
    return f"{s // 60}:{s % 60:02d}"
