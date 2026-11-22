"""Small Spotify Web API client, written against the 2026 Development Mode rules:

* playlist songs come from GET /playlists/{id}/items (old /tracks is gone), and each
  entry wraps its track in ``item`` (``track`` is kept only as a fallback);
* /items only works for playlists the user owns or collaborates on (403 otherwise);
* search returns at most 10 results per request.

All methods block, so the UI calls them from worker threads.
"""
from __future__ import annotations

import time

import requests

from .auth import TokenManager
from .models import Device, PlaybackState, Playlist, Track

API = "https://api.spotify.com/v1"


class SpotifyError(Exception):
    def __init__(self, message: str, status: int = 0, reason: str = ""):
        super().__init__(message)
        self.status = status
        self.reason = reason


class NoActiveDevice(SpotifyError):
    pass


def _best_image(images: list | None, prefer: int = 300) -> str:
    if not images:
        return ""
    sized = [i for i in images if i.get("url")]
    if not sized:
        return ""
    # Pick the smallest image at least `prefer` px wide, else the largest available.
    sized.sort(key=lambda i: i.get("width") or 0)
    for img in sized:
        if (img.get("width") or 0) >= prefer:
            return img["url"]
    return sized[-1]["url"]


def parse_track(obj: dict | None) -> Track | None:
    if not obj or obj.get("type", "track") != "track":
        return None
    album = obj.get("album") or {}
    return Track(
        id=obj.get("id") or "",
        uri=obj.get("uri") or "",
        name=obj.get("name") or "Untitled",
        artists=", ".join(a.get("name", "") for a in obj.get("artists") or []) or "Unknown",
        album=album.get("name") or "",
        image_url=_best_image(album.get("images")),
        duration_ms=obj.get("duration_ms") or 0,
        is_local=bool(obj.get("is_local")),
    )


def parse_playlist(obj: dict, my_id: str = "") -> Playlist:
    owner = obj.get("owner") or {}
    counts = obj.get("items") or obj.get("tracks") or {}
    total = counts.get("total", 0) if isinstance(counts, dict) else 0
    readable = (not my_id) or owner.get("id") == my_id or bool(obj.get("collaborative"))
    return Playlist(
        id=obj.get("id") or "",
        name=obj.get("name") or "Untitled",
        uri=obj.get("uri") or "",
        image_url=_best_image(obj.get("images")),
        total=total,
        owner=owner.get("display_name") or owner.get("id") or "",
        readable=readable,
    )


def parse_device(obj: dict | None) -> Device | None:
    if not obj:
        return None
    return Device(
        id=obj.get("id") or "",
        name=obj.get("name") or "Unknown device",
        type=obj.get("type") or "",
        is_active=bool(obj.get("is_active")),
        volume=obj.get("volume_percent"),
    )


def parse_playback(obj: dict | None) -> PlaybackState:
    if not obj:
        return PlaybackState()
    device = parse_device(obj.get("device"))
    return PlaybackState(
        is_playing=bool(obj.get("is_playing")),
        track=parse_track(obj.get("item")),
        progress_ms=obj.get("progress_ms") or 0,
        shuffle=bool(obj.get("shuffle_state")),
        repeat=obj.get("repeat_state") or "off",
        volume=device.volume if device else None,
        device=device,
        context_uri=(obj.get("context") or {}).get("uri") or "",
    )


class SpotifyClient:
    def __init__(self, tokens: TokenManager):
        self.tokens = tokens
        self.session = requests.Session()
        self.my_id = ""

    # -- plumbing -----------------------------------------------------------------
    def _req(self, method: str, path: str, *, params=None, json=None, _retry=True):
        url = path if path.startswith("http") else API + path
        headers = {"Authorization": f"Bearer {self.tokens.access_token()}"}
        resp = self.session.request(method, url, params=params, json=json,
                                    headers=headers, timeout=20)
        if resp.status_code == 401 and _retry:
            self.tokens.force_refresh()
            return self._req(method, path, params=params, json=json, _retry=False)
        if resp.status_code == 429 and _retry:
            wait = min(int(resp.headers.get("Retry-After", "2") or 2), 10)
            time.sleep(wait)
            return self._req(method, path, params=params, json=json, _retry=False)
        if resp.status_code in (200, 201):
            return resp.json() if resp.content else None
        if resp.status_code in (202, 204):
            return None
        reason, message = "", resp.text[:200]
        try:
            err = resp.json().get("error", {})
            if isinstance(err, dict):
                reason = err.get("reason", "") or ""
                message = err.get("message", message)
        except ValueError:
            pass
        if reason == "NO_ACTIVE_DEVICE" or (resp.status_code == 404
                                            and "device" in message.lower()):
            raise NoActiveDevice("No active Spotify device. Pick a speaker first.",
                                 resp.status_code, reason)
        if resp.status_code == 403 and reason == "PREMIUM_REQUIRED":
            raise SpotifyError("Playback control needs Spotify Premium.", 403, reason)
        if resp.status_code == 429:
            raise SpotifyError("Spotify says we're asking too often. Give it a minute.",
                               429, reason)
        raise SpotifyError(f"Spotify error {resp.status_code}: {message}",
                           resp.status_code, reason)

    def _paged(self, path: str, params: dict, max_items: int = 2000):
        params = dict(params)
        data = self._req("GET", path, params=params)
        while data:
            yield from data.get("items") or []
            max_items -= len(data.get("items") or [])
            nxt = data.get("next")
            if not nxt or max_items <= 0:
                break
            data = self._req("GET", nxt)

    # -- library --------------------------------------------------------------------
    def me(self) -> dict:
        me = self._req("GET", "/me") or {}
        self.my_id = me.get("id", "")
        return me

    def playlists(self) -> list[Playlist]:
        if not self.my_id:
            self.me()
        return [parse_playlist(p, self.my_id)
                for p in self._paged("/me/playlists", {"limit": 50}) if p]

    def playlist_tracks(self, playlist_id: str) -> list[Track]:
        out = []
        for entry in self._paged(f"/playlists/{playlist_id}/items",
                                 {"limit": 50, "additional_types": "track"}):
            t = parse_track(entry.get("item") or entry.get("track"))
            if t and not t.is_local:
                out.append(t)
        return out

    def liked_tracks(self, limit: int = 500) -> list[Track]:
        out = []
        for entry in self._paged("/me/tracks", {"limit": 50}, max_items=limit):
            t = parse_track(entry.get("track") or entry.get("item"))
            if t:
                out.append(t)
        return out

    def recently_played(self) -> list[Track]:
        data = self._req("GET", "/me/player/recently-played", params={"limit": 50}) or {}
        seen, out = set(), []
        for entry in data.get("items") or []:
            t = parse_track(entry.get("track"))
            if t and t.id not in seen:
                seen.add(t.id)
                out.append(t)
        return out

    def search(self, query: str, pages: int = 3) -> list[Track]:
        out = []
        for page in range(pages):  # Dev Mode caps search at 10 results per call
            data = self._req("GET", "/search", params={
                "q": query, "type": "track", "limit": 10, "offset": page * 10}) or {}
            items = (data.get("tracks") or {}).get("items") or []
            out.extend(t for t in map(parse_track, items) if t)
            if len(items) < 10:
                break
        return out

    # -- player ---------------------------------------------------------------------
    def playback(self) -> PlaybackState:
        return parse_playback(self._req("GET", "/me/player"))

    def devices(self) -> list[Device]:
        data = self._req("GET", "/me/player/devices") or {}
        return [d for d in map(parse_device, data.get("devices") or []) if d and d.id]

    def transfer(self, device_id: str, play: bool = True) -> None:
        self._req("PUT", "/me/player", json={"device_ids": [device_id], "play": play})

    def play(self, *, context_uri: str = "", uris: list[str] | None = None,
             offset_uri: str = "", offset_pos: int | None = None,
             device_id: str = "") -> None:
        body: dict = {}
        if context_uri:
            body["context_uri"] = context_uri
            if offset_uri:
                body["offset"] = {"uri": offset_uri}
            elif offset_pos is not None:
                body["offset"] = {"position": offset_pos}
        elif uris:
            body["uris"] = uris[:100]
            if offset_uri:
                body["offset"] = {"uri": offset_uri}
        params = {"device_id": device_id} if device_id else None
        self._req("PUT", "/me/player/play", params=params, json=body or None)

    def resume(self, device_id: str = "") -> None:
        params = {"device_id": device_id} if device_id else None
        self._req("PUT", "/me/player/play", params=params)

    def pause(self) -> None:
        self._req("PUT", "/me/player/pause")

    def next(self) -> None:
        self._req("POST", "/me/player/next")

    def previous(self) -> None:
        self._req("POST", "/me/player/previous")

    def seek(self, ms: int) -> None:
        self._req("PUT", "/me/player/seek", params={"position_ms": max(0, int(ms))})

    def shuffle(self, on: bool, device_id: str = "") -> None:
        params = {"state": "true" if on else "false"}
        if device_id:
            params["device_id"] = device_id
        self._req("PUT", "/me/player/shuffle", params=params)

    def repeat(self, mode: str) -> None:
        self._req("PUT", "/me/player/repeat", params={"state": mode})

    def volume(self, pct: int) -> None:
        self._req("PUT", "/me/player/volume",
                  params={"volume_percent": max(0, min(100, int(pct)))})
