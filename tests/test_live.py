"""Live Soloist events drive the UI; media-key bridge behaves on every OS."""
import os
import sys
import time

import pytest

from pinkie import config, soloist


def pump(app, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def entity(uri, name, artist="Ari", album="Alb", dur=180000):
    return {"uri": uri, "entity_type": "track", "decorations": {
        "identity": {"name": name},
        "creators": [{"decorations": {"identity": {"name": artist}}}],
        "parent": {"entity": {"entity_type": "album", "decorations": {
            "identity": {"name": album},
            "visual_identity": {"cover": [{"url": "spotify:image:abc", "size": "large"}]}}}},
        "playback": {"duration_ms": dur}}}


def test_entity_and_position_parsing():
    t = soloist.entity_track(entity("spotify:track:1", "Song"))
    assert (t.name, t.artists, t.album, t.duration_ms) == ("Song", "Ari", "Alb", 180000)
    assert t.image_url == "https://i.scdn.co/image/abc"
    now_ms = time.time() * 1000
    pos = soloist.position_now({"position_ms": 1000, "timestamp_ms": now_ms - 2000, "speed": 1.0})
    assert 2900 <= pos <= 3300
    assert soloist.position_now({"position_ms": 500, "timestamp_ms": 0, "speed": 0}) == 500


def test_live_events_update_window(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("PINKIE_CONFIG_DIR", str(tmp_path))
    from pinkie.main_window import MainWindow
    win = MainWindow(config.Settings(), demo=True)
    win.show()
    win.start()
    pump(qapp, 0.5)
    win._on_player_event({"type": "playback_state", "status": "playing", "is_active": True,
                          "item": entity("spotify:track:9", "Otter Love"),
                          "position": {"position_ms": 4000, "timestamp_ms": time.time() * 1000,
                                       "speed": 1.0},
                          "volume": 42, "options": {"shuffle": True, "repeat": "track"}})
    assert win._live
    assert "OTTER LOVE" in win.deck.lcd.text() and win.mini.title.text() == "Otter Love"
    assert win.state.is_playing and win.deck.b_shuffle.isChecked()
    assert win.deck.repeat_mode == "track" and win.deck.volume.value() == 42
    win._on_player_event({"type": "playback_changed", "status": "paused"})
    assert not win.state.is_playing and not win.deck.b_play.playing
    win._on_player_event({"type": "track_changed", "item": entity("spotify:track:10", "Next One")})
    assert "NEXT ONE" in win.deck.lcd.text()
    win._on_player_event({"type": "queue_changed", "previous": [], "upcoming": [
        {"uid": "a", "source": "context", "item": entity("spotify:track:11", "Up 1")},
        {"uid": "b", "source": "queue", "item": entity("spotify:track:12", "Up 2")}]})
    assert [t.name for t in win.upnext_tracks] == ["Up 1", "Up 2"]
    win._on_player_event({"type": "device_changed", "is_active": False, "device_name": "x"})
    assert not win._live
    win.close()


def test_media_key_bridge(qapp):
    from pinkie.nowplaying import NowPlayingBridge
    b = NowPlayingBridge()
    if sys.platform == "darwin":
        assert b.available, b.reason
    else:
        assert not b.available
    # safe to call everywhere
    b.set_track("Song", "Ari", 180000, None, "Alb", "2001")
    b.set_playing(True)
    b.set_progress(5000)
    b.set_playing(False)
    b.set_track("", "", 0, None)
    b.shutdown()
