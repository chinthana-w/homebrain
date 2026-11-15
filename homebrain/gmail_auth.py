"""Obtain a Gmail metadata-only refresh token through a local OAuth callback."""

from __future__ import annotations

import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

REDIRECT_URI = "http://localhost:8765/callback"
GMAIL_METADATA_SCOPE = "https://www.googleapis.com/auth/gmail.metadata"


def _load_local_env() -> None:
    env_path = Path(".env")
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key in {"HOMEBRAIN_GMAIL_CLIENT_ID", "HOMEBRAIN_GMAIL_CLIENT_SECRET"}:
            os.environ.setdefault(key, value)


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlsplit(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        expected_state = self.server.oauth_state  # type: ignore[attr-defined]
        received_state = params.get("state", [""])[0]
        if parsed.path != "/callback" or not secrets.compare_digest(
            received_state, expected_state
        ):
            self.send_error(400, "Invalid OAuth callback")
            return
        error = params.get("error", [""])[0]
        code = params.get("code", [""])[0]
        self.server.oauth_result = (code, error)  # type: ignore[attr-defined]
        message = (
            "Authorization received. You can close this tab and return to the terminal."
            if code and not error
            else "Authorization was not completed. Return to the terminal."
        )
        raw = (
            "<!doctype html><meta charset=utf-8><title>Homebrain Gmail setup</title>"
            f"<p>{message}</p>"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args: Any) -> None:
        return


def _exchange_code(code: str, client_id: str, client_secret: str) -> dict[str, Any]:
    request = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=urllib.parse.urlencode(
            {
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            }
        ).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read(64_000))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Google OAuth code exchange failed (HTTP {exc.code})") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError("Could not reach Google OAuth") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Google OAuth returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Google OAuth returned an invalid response")
    return result


def run() -> None:
    _load_local_env()
    client_id = os.getenv("HOMEBRAIN_GMAIL_CLIENT_ID", "").strip()
    client_secret = os.getenv("HOMEBRAIN_GMAIL_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise SystemExit(
            "Set HOMEBRAIN_GMAIL_CLIENT_ID and HOMEBRAIN_GMAIL_CLIENT_SECRET in .env first."
        )

    state = secrets.token_urlsafe(32)
    server = HTTPServer(("127.0.0.1", 8765), _CallbackHandler)
    server.timeout = 1
    server.oauth_state = state  # type: ignore[attr-defined]
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": GMAIL_METADATA_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
    )
    authorization_url = "https://accounts.google.com/o/oauth2/v2/auth?" + query
    print("Opening Google sign-in in your browser. This callback listens only on localhost.")
    if not webbrowser.open(authorization_url):
        print(f"Open this URL in your browser:\n{authorization_url}")
    deadline = time.monotonic() + 300
    try:
        while time.monotonic() < deadline and not getattr(server, "oauth_result", None):
            server.handle_request()
    finally:
        server.server_close()
    result = getattr(server, "oauth_result", None)
    if not result:
        raise SystemExit("Timed out waiting for Google authorization.")
    code, error = result
    if error or not code:
        raise SystemExit("Google authorization was denied or incomplete.")

    tokens = _exchange_code(code, client_id, client_secret)
    refresh_token = tokens.get("refresh_token")
    granted_scopes = set(str(tokens.get("scope", "")).split())
    if not isinstance(refresh_token, str) or not refresh_token:
        raise SystemExit(
            "Google did not issue a refresh token. Revoke Homebrain's consent in your Google "
            "account and rerun this command."
        )
    scope_response = tokens.get("scope")
    if scope_response and GMAIL_METADATA_SCOPE not in granted_scopes:
        raise SystemExit("Google did not grant the required Gmail metadata-only scope.")
    print(
        "\nCopy this refresh token into HOMEBRAIN_GMAIL_REFRESH_TOKEN in your local .env file. "
        "Do not paste it into chat or commit it:\n"
    )
    print(refresh_token)


if __name__ == "__main__":
    run()
