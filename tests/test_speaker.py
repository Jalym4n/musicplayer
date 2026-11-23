"""The built-in speaker's login and restart logic, driven with a fake librespot program."""
import os
import stat
import sys
import time
from pathlib import Path

import pytest

from pinkie import speaker as spk

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="fake binary is a script")

# Fake librespot. Behaviour is picked with FAKE_* environment variables.
FAKE = r'''#!{python}
import os, signal, sys, time, pathlib
args = sys.argv[1:]
cache = pathlib.Path(args[args.index("--cache") + 1])
creds = cache / "credentials.json"
with pathlib.Path(os.environ["FAKE_LOG"]).open("a") as f:
    f.write(("cached" if creds.exists() else "oauth") + "\n")
if os.environ.get("FAKE_CRASH"):
    os.kill(os.getpid(), signal.SIGKILL)
if os.environ.get("FAKE_NO_AUDIO"):
    print("thread 'main' panicked at librespot_playback::audio_backend::rodio::mk_rodio", flush=True)
    sys.exit(101)
if creds.exists():
    if os.environ.get("FAKE_BAD_CACHE"):
        print("[INFO librespot_core::session] Authenticated as 'bestie' !", flush=True)
        print("[ERROR librespot] Spirc shut down too often. Not reconnecting automatically.", flush=True)
        sys.exit(1)
    print("[INFO librespot_core::session] Authenticated as 'bestie' !", flush=True)
    time.sleep(30)
    sys.exit(0)
assert "--enable-oauth" in args
print("Browse to: https://accounts.spotify.com/authorize?client_id=x", flush=True)
if os.environ.get("FAKE_AUTO_LOGIN"):
    time.sleep(0.2)
    creds.write_text("{{}}")
    print("[INFO librespot_core::session] Authenticated as 'bestie' !", flush=True)
time.sleep(30)
'''


@pytest.fixture
def env(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("PINKIE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "calls.log"))
    monkeypatch.setattr(spk.Speaker, "MAX_FAILURES", 2)
    fake = tmp_path / "librespot"
    fake.write_text(FAKE.format(python=sys.executable))
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    return qapp, str(fake), tmp_path / "calls.log"


def wait_for(app, cond, seconds=10.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not cond():
        app.processEvents()
        time.sleep(0.02)
    return cond()


def calls(log: Path):
    return log.read_text().split() if log.exists() else []


def test_args_keep_speaker_private_and_use_its_own_login():
    args = spk.build_args("Pinkie Player")
    assert "--disable-discovery" in args and "--enable-oauth" in args
    assert args[args.index("--name") + 1] == "Pinkie Player"
    assert "--access-token" not in args


def test_first_run_browser_login_then_saved_login(env, monkeypatch):
    app, fake, log = env
    monkeypatch.setenv("FAKE_AUTO_LOGIN", "1")
    s = spk.Speaker()
    urls = []
    s.loginUrl.connect(urls.append)
    s.start(fake)
    assert wait_for(app, lambda: s.phase == spk.READY)
    assert urls and urls[0].startswith("https://accounts.spotify.com/")
    assert spk.has_cached_login()                     # marker written after real login
    s.stop()
    s.start(fake)
    assert wait_for(app, lambda: s.phase == spk.READY)
    assert calls(log) == ["oauth", "cached"]
    s.stop()


def test_stale_login_from_old_build_is_dropped(env):
    app, fake, log = env
    (spk.cache_dir() / "credentials.json").write_text("{}")   # no marker = old token login
    s = spk.Speaker()
    s.start(fake)
    assert wait_for(app, lambda: s.phase == spk.LOGIN)
    assert calls(log) == ["oauth"]
    assert "removed an old saved speaker login" in spk.log_path().read_text()
    s.stop()


def test_saved_login_that_keeps_failing_asks_for_fresh_login(env, monkeypatch):
    app, fake, log = env
    monkeypatch.setenv("FAKE_BAD_CACHE", "1")
    (spk.cache_dir() / "credentials.json").write_text("{}")
    (spk.cache_dir() / spk.MARKER).write_text("{}")
    s = spk.Speaker()
    s.start(fake)
    assert wait_for(app, lambda: s.phase == spk.LOGIN)
    assert calls(log)[0] == "cached" and calls(log)[-1] == "oauth"
    assert not spk.has_cached_login()
    s.stop()


def test_crash_loop_stops_with_error_instead_of_looping(env, monkeypatch):
    app, fake, log = env
    monkeypatch.setenv("FAKE_CRASH", "1")
    s = spk.Speaker()
    s.start(fake)
    assert wait_for(app, lambda: s.phase == spk.ERROR, seconds=15)
    assert len(calls(log)) == spk.Speaker.MAX_FAILURES + 1
    assert "crashed right away" in s.detail
    assert "crashed" in spk.log_path().read_text()


def test_no_sound_card_is_reported(env, monkeypatch):
    app, fake, log = env
    monkeypatch.setenv("FAKE_NO_AUDIO", "1")
    s = spk.Speaker()
    s.start(fake)
    assert wait_for(app, lambda: s.phase == spk.ERROR)
    assert "sound output" in s.detail


def test_missing_binary(env):
    s = spk.Speaker()
    s.start("")
    assert s.phase == spk.MISSING
