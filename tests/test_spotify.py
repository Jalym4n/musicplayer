"""Tests for the Spotify client against canned responses (no network)."""
import json
import time

import pytest

from pinkie import spotify
from pinkie.auth import TokenManager


class FakeResp:
    def __init__(self, status=200, body=None, headers=None, raw=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.content = raw if raw is not None else (
            b"" if body is None else json.dumps(body).encode())
        self.text = self.content.decode()

    def json(self):
        return json.loads(self.content)


class FakeSession:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        self.calls.append((method, url, params, json))
        path = url.replace(spotify.API, "")
        resp = self.routes.get((method, path.split("?")[0]))
        if callable(resp):
            resp = resp(params, json)
        return resp or FakeResp(404, {"error": {"status": 404, "message": "nope"}})


def make_client(routes):
    tm = TokenManager("cid", {"access_token": "tok", "expires_at": time.time() + 999,
                              "refresh_token": "r"})
    c = spotify.SpotifyClient(tm)
    c.session = FakeSession(routes)
    return c


TRACK = {"type": "track", "id": "t1", "uri": "spotify:track:t1", "name": "Song",
         "duration_ms": 61000, "artists": [{"name": "A"}, {"name": "B"}],
         "album": {"name": "Alb", "images": [{"url": "big", "width": 640},
                                              {"url": "mid", "width": 300},
                                              {"url": "small", "width": 64}]}}


def test_parse_track_picks_300px_cover_and_joins_artists():
    t = spotify.parse_track(TRACK)
    assert t.artists == "A, B"
    assert t.image_url == "mid"
    assert t.duration_text == "1:01"


def test_parse_track_skips_podcast_episodes():
    assert spotify.parse_track({"type": "episode", "name": "x"}) is None


def test_playlist_items_uses_new_endpoint_and_item_field():
    routes = {("GET", "/playlists/p1/items"): FakeResp(200, {
        "items": [{"item": TRACK}, {"track": dict(TRACK, id="t2", uri="u2")},
                  {"item": dict(TRACK, is_local=True)}],
        "next": None})}
    c = make_client(routes)
    tracks = c.playlist_tracks("p1")
    assert [t.id for t in tracks] == ["t1", "t2"]  # local file dropped, legacy field ok
    assert c.session.calls[0][1].endswith("/playlists/p1/items")


def test_playlist_readable_only_when_owned_or_collaborative():
    mine = spotify.parse_playlist({"id": "a", "owner": {"id": "me"}, "items": {"total": 3}}, "me")
    theirs = spotify.parse_playlist({"id": "b", "owner": {"id": "x"}, "tracks": {"total": 9}}, "me")
    collab = spotify.parse_playlist({"id": "c", "owner": {"id": "x"}, "collaborative": True}, "me")
    assert (mine.readable, mine.total) == (True, 3)
    assert (theirs.readable, theirs.total) == (False, 9)
    assert collab.readable


def test_search_pages_ten_at_a_time():
    def page(params, _):
        n = 10 if params["offset"] < 20 else 4
        assert params["limit"] == 10
        return FakeResp(200, {"tracks": {"items": [TRACK] * n}})
    c = make_client({("GET", "/search"): page})
    assert len(c.search("hi")) == 24


def test_no_active_device_error():
    c = make_client({("PUT", "/me/player/play"): FakeResp(404, {
        "error": {"status": 404, "message": "Player command failed: No active device found",
                  "reason": "NO_ACTIVE_DEVICE"}})})
    with pytest.raises(spotify.NoActiveDevice):
        c.play(context_uri="spotify:playlist:x")


def test_play_body_with_offset_and_device():
    c = make_client({("PUT", "/me/player/play"): FakeResp(204)})
    c.play(context_uri="spotify:playlist:x", offset_uri="spotify:track:t1", device_id="d1")
    method, url, params, body = c.session.calls[0]
    assert params == {"device_id": "d1"}
    assert body == {"context_uri": "spotify:playlist:x", "offset": {"uri": "spotify:track:t1"}}


def test_playback_empty_204_means_nothing_playing():
    c = make_client({("GET", "/me/player"): FakeResp(204)})
    s = c.playback()
    assert s.track is None and not s.is_playing


def test_401_triggers_one_refresh_then_retry(monkeypatch):
    calls = {"n": 0}

    def me(params, body):
        calls["n"] += 1
        return FakeResp(401, {"error": {"status": 401, "message": "expired"}}) \
            if calls["n"] == 1 else FakeResp(200, {"id": "me"})
    c = make_client({("GET", "/me"): me})
    refreshed = []
    monkeypatch.setattr(c.tokens, "force_refresh", lambda: refreshed.append(1))
    assert c.me()["id"] == "me"
    assert refreshed == [1]


def test_player_command_with_non_json_200_body_is_ok():
    # Spotify sometimes answers player commands with 200 and a non-JSON body
    c = make_client({("PUT", "/me/player/shuffle"): FakeResp(200, raw=b"a1b2c3"),
                     ("PUT", "/me/player/repeat"): FakeResp(200, raw=b" ")})
    c.shuffle(True)
    c.repeat("context")
