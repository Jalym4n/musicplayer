"""The built-in speaker's login fallbacks, driven with a fake librespot program."""
import os
import stat
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pinkie import speaker as spk  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="fake binary is a shell script")

FAKE = r'''#!{python}
import os, sys, time, pathlib
args = sys.argv[1:]
log = pathlib.Path(os.environ["FAKE_LOG"])
token = os.environ.get("LIBRESPOT_ACCESS_TOKEN", "")
with log.open("a") as f:
    f.write(("oauth" if "--enable-oauth" in args else "token:" + token) + "\n")
cache = pathlib.Path(args[args.index("--cache") + 1])
if os.environ.get("FAKE_NO_AUDIO"):
    print("thread 'main' panicked at librespot_playback::audio_backend::rodio::mk_rodio", flush=True)
    sys.exit(101)
if (cache / "credentials.json").exists() or token == "good":
    (cache / "credentials.json").write_text("{{}}")
    print("[INFO librespot_core::session] Authenticated as 'bestie' !", flush=True)
    time.sleep(30)
elif token:
    print("[ERROR librespot] could not initialize spirc: BadCredentials", flush=True)
    sys.exit(1)
elif "--enable-oauth" in args:
    print("Browse to: https://accounts.spotify.com/authorize?client_id=x", flush=True)
    time.sleep(30)
'''


@pytest.fixture
def env(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("PINKIE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "calls.log"))
    fake = tmp_path / "librespot"
    fake.write_text(FAKE.format(python=sys.executable))
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    return qapp, str(fake), tmp_path / "calls.log"


def wait_for(app, cond, seconds=8.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not cond():
        app.processEvents()
        time.sleep(0.02)
    return cond()


def calls(log: Path):
    return log.read_text().split() if log.exists() else []


def test_args_keep_speaker_private_and_cached():
    args = spk.build_args("Pinkie Player", oauth=True)
    assert "--disable-discovery" in args and "--enable-oauth" in args
    assert args[args.index("--name") + 1] == "Pinkie Player"
    assert "--cache" in args


def test_app_token_signs_in_without_second_login(env):
    app, fake, log = env
    s = spk.Speaker()
    s.start(fake, "good", "streaming user-read-playback-state")
    assert wait_for(app, lambda: s.phase == spk.READY)
    assert calls(log) == ["token:good"]
    assert spk.has_cached_login()
    s.stop()
    s.start(fake, "good", "streaming")  # next launch reuses the cached login
    assert wait_for(app, lambda: s.phase == spk.READY)
    assert calls(log)[-1] == "token:"     # no token passed: cached credentials used
    s.stop()


def test_rejected_token_falls_back_to_browser_login(env):
    app, fake, log = env
    s = spk.Speaker()
    urls = []
    s.loginUrl.connect(urls.append)
    s.start(fake, "bad", "streaming")
    assert wait_for(app, lambda: s.phase == spk.LOGIN)
    assert calls(log) == ["token:bad", "oauth"]
    assert urls and urls[0].startswith("https://accounts.spotify.com/")
    s.stop()


def test_token_without_streaming_scope_goes_straight_to_browser(env):
    app, fake, log = env
    s = spk.Speaker()
    s.start(fake, "good", "user-read-playback-state")
    assert wait_for(app, lambda: s.phase == spk.LOGIN)
    assert calls(log) == ["oauth"]
    s.stop()


def test_no_sound_card_is_reported(env, monkeypatch):
    app, fake, log = env
    monkeypatch.setenv("FAKE_NO_AUDIO", "1")
    s = spk.Speaker()
    s.start(fake, "good", "streaming")
    assert wait_for(app, lambda: s.phase == spk.ERROR)
    assert "sound output" in s.detail


def test_missing_binary(env):
    s = spk.Speaker()
    s.start("")
    assert s.phase == spk.MISSING
