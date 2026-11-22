"""Offline stand-in for SpotifyClient so the app can be previewed with no account.

Run with ``python -m pinkie --demo``. Covers are drawn locally (``demo:`` URLs).
"""
from __future__ import annotations

import random
import time

from .models import Device, PlaybackState, Playlist, Track

_WORDS_A = ["Strawberry", "Velvet", "Bubblegum", "Glitter", "Cherry", "Moonlit",
            "Pastel", "Sugar", "Daydream", "Lavender", "Peach", "Starry", "Honey"]
_WORDS_B = ["Kisses", "Skies", "Hearts", "Diaries", "Lullaby", "Rollerskates",
            "Polaroids", "Sundae", "Mixtape", "Valentine", "Sparkles", "Petals"]
_ARTISTS = ["The Lovebirds", "Kitty Cassette", "Mila Moon", "Sugar Static",
            "Pixel Princess", "Bunny Hop Club", "Cherry Cola", "Daisy Dial-Up"]
_PLAYLISTS = ["sleepover songs", "pink cassette", "main character era",
              "rainy day cuddles", "roller rink 1999", "glitter gel pens",
              "study w/ me", "heartbreak hotel"]


class DemoClient:
    def __init__(self, seed: int = 7):
        rnd = random.Random(seed)
        self._tracks: dict[str, list[Track]] = {}
        self._playlists: list[Playlist] = []
        n = 0
        for i, name in enumerate(_PLAYLISTS):
            pid = f"pl{i}"
            tracks = []
            for _ in range(rnd.randint(9, 16)):
                n += 1
                album_seed = rnd.randint(0, 40)
                tracks.append(Track(
                    id=f"t{n}", uri=f"spotify:track:t{n}",
                    name=f"{rnd.choice(_WORDS_A)} {rnd.choice(_WORDS_B)}",
                    artists=rnd.choice(_ARTISTS),
                    album=f"{rnd.choice(_WORDS_B)} Vol. {album_seed % 4 + 1}",
                    image_url=f"demo:{album_seed}",
                    duration_ms=rnd.randint(140, 260) * 1000,
                ))
            self._tracks[pid] = tracks
            self._playlists.append(Playlist(
                id=pid, name=name, uri=f"spotify:playlist:{pid}",
                image_url=f"demo:{100 + i}", total=len(tracks), owner="you",
                readable=i != 5,
            ))
        self._all = [t for ts in self._tracks.values() for t in ts]
        self._devices = [Device("dev-here", "Pinkie Player", "Computer", True, 70),
                         Device("dev-phone", "My Phone", "Smartphone", False, 50)]
        self._queue: list[Track] = self._tracks["pl0"]
        self._index = 0
        self._playing = False
        self._started_at = time.monotonic()
        self._offset_ms = 0
        self._shuffle = False
        self._repeat = "off"
        self._volume = 70
        self._context = "spotify:playlist:pl0"
        self.my_id = "demo"

    # library
    def me(self):
        return {"id": "demo", "display_name": "Demo Girl"}

    def playlists(self):
        return list(self._playlists)

    def playlist_tracks(self, pid):
        return list(self._tracks.get(pid, []))

    def liked_tracks(self, limit=500):
        return self._all[::3][:limit]

    def recently_played(self):
        return self._all[5:25]

    def search(self, query, pages=3):
        q = query.lower()
        hits = [t for t in self._all if q in t.name.lower() or q in t.artists.lower()]
        return hits[:30] or self._all[:6]

    # player
    def _pos(self) -> int:
        if not self._playing:
            return self._offset_ms
        return self._offset_ms + int((time.monotonic() - self._started_at) * 1000)

    def playback(self):
        cur = self._queue[self._index] if self._queue else None
        if cur and self._pos() >= cur.duration_ms:
            self.next()
            cur = self._queue[self._index]
        active = next((d for d in self._devices if d.is_active), None)
        return PlaybackState(self._playing, cur, self._pos(), self._shuffle, self._repeat,
                             self._volume, active, self._context)

    def devices(self):
        return list(self._devices)

    def transfer(self, device_id, play=True):
        for d in self._devices:
            d.is_active = d.id == device_id
        if play:
            self.resume()

    def _set_pos(self, ms):
        self._offset_ms = ms
        self._started_at = time.monotonic()

    def play(self, *, context_uri="", uris=None, offset_uri="", offset_pos=None,
             device_id=""):
        if not context_uri and not uris:
            return self.resume()
        if context_uri.startswith("spotify:playlist:"):
            pid = context_uri.rsplit(":", 1)[1]
            self._queue = self._tracks.get(pid, self._queue)
            self._context = context_uri
        elif uris:
            by_uri = {t.uri: t for t in self._all}
            self._queue = [by_uri[u] for u in uris if u in by_uri] or self._queue
            self._context = ""
        self._index = 0
        if offset_uri:
            self._index = next((i for i, t in enumerate(self._queue)
                                if t.uri == offset_uri), 0)
        elif offset_pos is not None:
            self._index = min(offset_pos, len(self._queue) - 1)
        self._playing = True
        self._set_pos(0)

    def resume(self, device_id=""):
        self._set_pos(self._pos())
        self._playing = True

    def pause(self):
        self._set_pos(self._pos())
        self._playing = False

    def next(self):
        self._index = (self._index + 1) % len(self._queue)
        self._set_pos(0)

    def previous(self):
        if self._pos() > 3000:
            self._set_pos(0)
            return
        self._index = (self._index - 1) % len(self._queue)
        self._set_pos(0)

    def seek(self, ms):
        self._set_pos(int(ms))

    def shuffle(self, on):
        self._shuffle = on

    def repeat(self, mode):
        self._repeat = mode

    def volume(self, pct):
        self._volume = int(pct)
