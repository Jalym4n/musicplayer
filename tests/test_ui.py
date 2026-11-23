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
    # MY LIBRARY + Liked, DISCOVER + Recent, PLAYLISTS + 8 demo playlists
    assert win.sidebar.list.count() == 2 + 2 + 1 + 8
    assert win.windowTitle().endswith("Aayusha's Music Player")
    assert win.tracks.tmodel.rowCount() > 0            # liked songs loaded

    win.sidebar.select_id("pl1")
    pump(app, 0.5)
    first = win.view_tracks[0]
    win.play_row(0)
    pump(app, 1.0)
    assert win.state.is_playing and win.state.track.uri == first.uri
    assert first.name.upper() in win.deck.lcd.text()
    assert win.mini.title.text() == first.name         # mini-player mirrors the deck
    win.notebook.show_page(0)
    win.refresh_queue()
    pump(app, 0.5)
    assert win.upnext_tracks and win.upnext_tracks[0].uri == win.view_tracks[1].uri

    win.mini.nextClicked.emit()                         # skip from the mini-player
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
    assert win.view_tracks
    assert all("kisses" in (t.name + t.artists).lower() for t in win.view_tracks)

    win.toggle_mini()
    assert win.mini.isVisible()
    win.mini.restoreMain.emit()
    assert not win.mini.isVisible()

    win.sidebar.favorites.append("pl2")                 # favorites get their own section
    win.sidebar._rebuild()
    from pinkie.widgets.side import ROLE_HEADER
    heads = [win.sidebar.list.item(i).data(ROLE_HEADER) for i in range(win.sidebar.list.count())]
    assert "FAVORITES" in heads

    win.sidebar.select_id("pl5")                       # someone else's playlist
    pump(app, 0.3)
    assert win.empty.isVisible() and "press play" in win.empty.text()
    win.close()



def test_personal_name_and_speaker_name():
    s = config.Settings(owner_name="Mia")
    assert s.her_name == "Mia" and s.speaker_name == "Mia's Player"
    assert config.Settings(device_name="Pinkie Player").speaker_name == "Aayusha's Player"
