"""The PKCE login: browser redirect lands on the loopback server, code is exchanged."""
import threading
import time
import urllib.parse
import urllib.request

from pinkie import auth, config


class Resp:
    status_code = 200

    def json(self):
        return {"access_token": "A", "refresh_token": "R", "expires_in": 3600}


def test_login_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("PINKIE_CONFIG_DIR", str(tmp_path))
    posted = {}
    monkeypatch.setattr(auth.requests, "post",
                        lambda url, data, timeout: posted.update(data) or Resp())

    def fake_browser(url):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        assert q["redirect_uri"] == [config.REDIRECT_URI]
        assert q["code_challenge_method"] == ["S256"]

        def hit():
            time.sleep(0.3)
            cb = f"{config.REDIRECT_URI}?code=abc&state={q['state'][0]}"
            direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            direct.open(cb, timeout=5).read()
        threading.Thread(target=hit, daemon=True).start()

    token = auth.login("0" * 32, fake_browser, timeout=10)
    assert token["access_token"] == "A"
    assert posted["code"] == "abc" and posted["code_verifier"]
    assert config.load_token()["refresh_token"] == "R"
