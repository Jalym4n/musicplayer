"""Smoke test: the whole window runs in demo mode and responds to controls."""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from pinkie import config, theme  # noqa: E402


@pytest.fixture(scope="module")
def app(tmp_path_factory, qapp):
    os.environ["PINKIE_CONFIG_DIR"] = str(tmp_path_factory.mktemp("cfg"))
    a = qapp
    theme.load_fonts()
    a.setStyleSheet(theme.stylesheet())
    return a


def pump(app, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def test_demo_window_plays_and_skips(app):
    from pinkie.main_window import MainWindow
    win = MainWindow(config.Settings(), demo=True)
    win.show()
    assert win.start()
    pump(app, 0.8)
    assert win.sidebar.list.count() == 2 + 8           # specials + demo playlists
    assert win.tracks.tmodel.rowCount() > 0            # liked songs loaded

    win.sidebar.select_id("pl1")
    pump(app, 0.5)
    first = win.view_tracks[0]
    win.play_row(0)
    pump(app, 1.0)
    assert win.state.is_playing and win.state.track.uri == first.uri
    assert win.np.title.text() == first.name

    win.np.nextClicked.emit()
    pump(app, 1.0)
    assert win.state.track.uri == win.view_tracks[1].uri

    win.toggle_play()
    pump(app, 1.0)
    assert not win.state.is_playing
    paused_uri = win.state.track.uri
    win.toggle_play()                                  # resume keeps the same song
    pump(app, 1.0)
    assert win.state.is_playing and win.state.track.uri == paused_uri

    win.search("Kisses")
    pump(app, 0.6)
    assert all("kisses" in (t.name + t.artists).lower() for t in win.view_tracks)

    win.sidebar.select_id("pl5")                       # someone else's playlist
    pump(app, 0.3)
    assert win.empty.isVisible() and "press play" in win.empty.text()
    win.close()

