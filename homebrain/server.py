"""Minimal Homebrain LAN gateway with web UI and JSON API."""

from __future__ import annotations

import json
import os
from hmac import compare_digest
from html import escape
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .modules import load_modules

MAX_BODY_BYTES = 32 * 1024


def _module_index(modules: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {module["id"]: module for module in modules}


def build_bridge_response(payload: dict[str, Any], modules: list[dict[str, Any]]) -> dict[str, Any]:
    target = str(payload.get("target", "")).strip()
    message = str(payload.get("message", "")).strip()

    if not target:
        raise ValueError("'target' is required")
    if not message:
        raise ValueError("'message' is required")

    index = _module_index(modules)
    if target not in index:
        raise ValueError(f"Unknown target module: {target}")

    return {
        "status": "accepted",
        "target": target,
        "target_endpoint": index[target]["endpoint"],
        "message": message,
        "timestamp": datetime.now(UTC).isoformat(),
    }


def _render_home(modules: list[dict[str, Any]]) -> bytes:
    items = "".join(
        f"<li><strong>{escape(m['name'])}</strong> ({escape(m['id'])}) - "
        f"<a href=\"{escape(m['endpoint'])}\">{escape(m['endpoint'])}</a><br>{escape(m['description'])}</li>"
        for m in modules
    )
    html = f"""<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <title>Homebrain</title>
    <style>
      body {{ font-family: sans-serif; margin: 2rem; max-width: 800px; }}
      code {{ background: #f2f2f2; padding: 0.1rem 0.3rem; }}
    </style>
  </head>
  <body>
    <h1>Homebrain Gateway</h1>
    <p>LAN-ready control plane for local smart-home modules.</p>
    <h2>Active modules</h2>
    <ul>{items}</ul>
    <h2>API</h2>
    <ul>
      <li><code>GET /api/v1/health</code></li>
      <li><code>GET /api/v1/modules</code></li>
      <li><code>POST /api/v1/bridge</code> (JSON: target, message)</li>
    </ul>
  </body>
</html>"""
    return html.encode("utf-8")


class HomebrainHandler(BaseHTTPRequestHandler):
    server_version = "homebrain/0.1"

    def _json(self, status: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _require_token(self) -> bool:
        expected = os.getenv("HOMEBRAIN_API_TOKEN", "").strip()
        if not expected:
            return True
        provided = self.headers.get("X-Homebrain-Token", "")
        return compare_digest(provided, expected)

    def do_GET(self) -> None:  # noqa: N802
        modules = self.server.modules  # type: ignore[attr-defined]
        if self.path == "/":
            raw = _render_home(modules)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return

        if self.path == "/api/v1/health":
            self._json(200, {"status": "ok", "name": "homebrain"})
            return

        if self.path == "/api/v1/modules":
            self._json(200, {"modules": modules})
            return

        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/v1/bridge":
            self._json(404, {"error": "not found"})
            return

        if not self._require_token():
            self._json(401, {"error": "unauthorized"})
            return

        content_length = int(self.headers.get("Content-Length", "0") or "0")
        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            self._json(400, {"error": "invalid body size"})
            return

        try:
            payload = json.loads(self.rfile.read(content_length))
            if not isinstance(payload, dict):
                raise ValueError("Payload must be a JSON object")
            modules = self.server.modules  # type: ignore[attr-defined]
            response = build_bridge_response(payload, modules)
        except (json.JSONDecodeError, ValueError) as exc:
            self._json(400, {"error": str(exc)})
            return

        self._json(200, response)


def run() -> None:
    host = os.getenv("HOMEBRAIN_HOST", "0.0.0.0")
    port = int(os.getenv("HOMEBRAIN_PORT", "8787"))

    server = ThreadingHTTPServer((host, port), HomebrainHandler)
    server.modules = load_modules()  # type: ignore[attr-defined]
    print(f"homebrain listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
