"""Spotify login using Authorization Code + PKCE.

No client secret is needed, so nothing sensitive ships inside the app. The login page
opens once in the system browser; Spotify then redirects to a tiny one-shot server on
127.0.0.1 that hands the code back to the app. Tokens are refreshed automatically.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import secrets
import socketserver
import threading
import time
import urllib.parse
from typing import Callable

import requests

from . import config

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"


class AuthError(Exception):
    pass


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


_DONE_PAGE = """<!doctype html><meta charset="utf-8"><title>Pinkie Player</title>
<body style="background:#ffd6e8;font-family:monospace;color:#6b2d5c;text-align:center;padding-top:15vh">
<h1>&#9825; {title} &#9825;</h1><p>{body}</p></body>"""


class _LoopbackServer(http.server.HTTPServer):
    """HTTPServer without the reverse-DNS lookup in server_bind().

    The stock version calls socket.getfqdn(), which can stall for 30s+ on macOS before
    the socket starts listening, so Spotify's redirect would arrive too early.
    """

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def _wait_for_code(state: str, timeout: float) -> str:
    result: dict[str, str] = {}
    got = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (http.server naming)
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            qs = urllib.parse.parse_qs(parsed.query)
            if qs.get("state", [""])[0] != state:
                result["error"] = "state_mismatch"
            elif "error" in qs:
                result["error"] = qs["error"][0]
            else:
                result["code"] = qs.get("code", [""])[0]
            ok = "code" in result
            page = _DONE_PAGE.format(
                title="you're in!" if ok else "oops",
                body="You can close this tab and go back to Pinkie Player."
                if ok else f"Login failed: {result.get('error')}",
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page.encode("utf-8"))
            got.set()

        def log_message(self, *args):  # keep the console quiet
            pass

    try:
        server = _LoopbackServer(("127.0.0.1", config.REDIRECT_PORT), Handler)
    except OSError as exc:
        raise AuthError(
            f"Port {config.REDIRECT_PORT} is busy. Close whatever is using it and try again."
        ) from exc
    server.timeout = 0.5
    deadline = time.monotonic() + timeout
    try:
        while not got.is_set() and time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()
    if "code" in result:
        return result["code"]
    if "error" in result:
        raise AuthError(f"Spotify login failed: {result['error']}")
    raise AuthError("Login timed out. Please try again.")


def login(client_id: str, open_url: Callable[[str], None], timeout: float = 300) -> dict:
    """Run the full browser login. Blocking: call from a worker thread."""
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": config.REDIRECT_URI,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "scope": " ".join(config.SCOPES),
        "state": state,
    }
    open_url(f"{AUTH_URL}?{urllib.parse.urlencode(params)}")
    code = _wait_for_code(state, timeout)
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.REDIRECT_URI,
            "code_verifier": verifier,
        },
        timeout=20,
    )
    if resp.status_code != 200:
        raise AuthError(f"Token exchange failed ({resp.status_code}): {resp.text[:200]}")
    token = _stamp(resp.json())
    config.save_token(token)
    return token


def _stamp(token: dict) -> dict:
    token["expires_at"] = int(time.time()) + int(token.get("expires_in", 3600)) - 60
    return token


class TokenManager:
    """Thread-safe holder that refreshes the access token when it is about to expire."""

    def __init__(self, client_id: str, token: dict):
        self.client_id = client_id
        self._token = token
        self._lock = threading.Lock()

    def access_token(self) -> str:
        with self._lock:
            if time.time() >= self._token.get("expires_at", 0):
                self._refresh()
            return self._token["access_token"]

    @property
    def scope(self) -> str:
        return self._token.get("scope", "")

    def force_refresh(self) -> None:
        with self._lock:
            self._refresh()

    def _refresh(self) -> None:
        refresh = self._token.get("refresh_token")
        if not refresh:
            raise AuthError("Session expired. Please log in again.")
        resp = requests.post(
            TOKEN_URL,
            data={"client_id": self.client_id, "grant_type": "refresh_token",
                  "refresh_token": refresh},
            timeout=20,
        )
        if resp.status_code != 200:
            config.clear_token()
            raise AuthError("Session expired. Please log in again.")
        new = _stamp(resp.json())
        # PKCE refresh tokens rotate; keep the old one only if Spotify sent none.
        new.setdefault("refresh_token", refresh)
        self._token = new
        config.save_token(new)
