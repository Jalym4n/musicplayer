"""Spotify Soloist speaker, driven with a fake `soloist` that follows the documented CLI:
daemon flags, `ctl trace` streaming "<ms> <json>" auth_state events, `ctl activate`,
exit code 10 for an expired build."""
import os
import stat
import sys
import time

import pytest

from pinkie import soloist
from pinkie import speaker as spk

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="fake binary is a script")

FAKE = r'''#!{python}
import json, os, sys, time, pathlib
args = sys.argv[1:]
def opt(name):
    return args[args.index(name) + 1] if name in args else None
data = pathlib.Path(opt("--data-dir") or opt("-D"))
log = pathlib.Path(os.environ["FAKE_LOG"])
if args and args[0] == "ctl":
    cmd = args[1]
    with log.open("a") as f:
        f.write("ctl " + cmd + "\n")
    if cmd == "activate":
        (data / "active").write_text("1")
        sys.exit(0)
    if cmd == "trace":
        while True:
            ev = {{"type": "auth_state", "logged_in": (data / "session").exists(),
                  "is_active": (data / "active").exists(), "device_name": "x"}}
            print(int(time.time() * 1000), json.dumps(ev), flush=True)
            time.sleep(0.3)
    sys.exit(1)
with log.open("a") as f:
    f.write("daemon " + " ".join(a for a in args if a != opt("--api-key")) + "\n")
assert opt("--api-key") == "key123", "missing key"
if os.environ.get("FAKE_EXPIRED"):
    print("build expired", flush=True)
    sys.exit(10)
data.mkdir(parents=True, exist_ok=True)
(data / "ws.port").write_text("4242")
if os.environ.get("FAKE_PAIR_AFTER"):
    time.sleep(float(os.environ["FAKE_PAIR_AFTER"]))
    (data / "session").write_text("paired")
time.sleep(60)
'''


@pytest.fixture
def env(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("PINKIE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "calls.log"))
    fake = tmp_path / "soloist"
    fake.write_text(FAKE.format(python=sys.executable))
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    return qapp, str(fake), tmp_path / "calls.log"


def wait_for(app, cond, seconds=12.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not cond():
        app.processEvents()
        time.sleep(0.02)
    return cond()


def test_args_keep_local_api_on_loopback():
    args = soloist.build_args("Aayusha's Player", "k")
    assert args[args.index("--device-name") + 1] == "Aayusha's Player"
    assert args[args.index("--ws") + 1].startswith("127.0.0.1:")
    assert "--data-dir" in args and "--cache-dir" in args


def test_parse_trace_line():
    ev = soloist.parse_event('1732300000000 {"type":"auth_state","logged_in":false}')
    assert ev == {"type": "auth_state", "logged_in": False}
    assert soloist.parse_event("garbage") is None


def test_needs_pairing_then_ready_once_paired(env, monkeypatch):
    app, fake, log = env
    monkeypatch.setenv("FAKE_PAIR_AFTER", "2.0")
    s = soloist.SoloistSpeaker("Aayusha's Player")
    phases = []
    s.phaseChanged.connect(lambda p, d: phases.append(p))
    s.start(fake, "key123")
    assert wait_for(app, lambda: s.phase == soloist.PAIR)
    assert "Aayusha's Player" in s.detail
    assert wait_for(app, lambda: s.phase == spk.READY)
    assert s.activate()
    assert (soloist.data_dir() / "active").exists()
    calls = log.read_text()
    assert "key123" not in calls                       # key never logged
    assert "key123" not in spk.log_path().read_text()
    s.stop()
    assert phases[0] == spk.STARTING


def test_expired_build_is_reported(env, monkeypatch):
    app, fake, _ = env
    monkeypatch.setenv("FAKE_EXPIRED", "1")
    s = soloist.SoloistSpeaker("x")
    s.start(fake, "key123")
    assert wait_for(app, lambda: s.phase == spk.ERROR)
    assert "expired" in s.detail


def test_missing_binary_or_key(env):
    s = soloist.SoloistSpeaker("x")
    s.start("", "key123")
    assert s.phase == spk.MISSING
    s.start("/bin/true", "")
    assert s.phase == spk.MISSING and "key" in s.detail


def test_librespot_key_refusal_stops_instead_of_looping(env, tmp_path):
    app, _, log = env
    fake = tmp_path / "librespot"
    fake.write_text(f"#!{sys.executable}\n" + r'''
import sys, time, pathlib, os
with pathlib.Path(os.environ["FAKE_LOG"]).open("a") as f:
    f.write("librespot\n")
print("[INFO librespot_core::session] Authenticated as 'x' !", flush=True)
for _ in range(3):
    print("[ERROR librespot_core::audio_key] error audio key 0 1", flush=True)
    time.sleep(0.2)
time.sleep(30)
''')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    (spk.cache_dir() / "credentials.json").write_text("{}")
    (spk.cache_dir() / spk.MARKER).write_text("{}")
    s = spk.Speaker("x")
    s.start(str(fake))
    assert wait_for(app, lambda: s.phase == spk.ERROR)
    assert s.blocked and "Soloist" in s.detail
    app.processEvents()
    time.sleep(1.5)
    app.processEvents()
    assert log.read_text().count("librespot") == 1      # no restart loop
