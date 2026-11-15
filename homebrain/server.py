"""Homebrain dashboard, chat API, and local analysis agent."""

from __future__ import annotations

import json
import os
import re
from hmac import compare_digest
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

from .agent import (
    AnalysisAgent,
    DashboardStore,
    chat_with_model,
    load_agent_config,
    load_builtin_source_configs,
    load_weather_config,
    validate_source,
)
from .modules import load_modules

MAX_BODY_BYTES = 32 * 1024
WEB_ROOT = Path(__file__).with_name("web")
SOURCE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


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


def _public_source(source: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in source.items() if key != "value"}
    if source["type"] in {"url", "weather"}:
        parsed = urlsplit(source["value"])
        result["location"] = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    elif source["type"] == "gmail":
        result["location"] = "Gmail inbox metadata"
    elif source["type"] == "github":
        result["location"] = f"GitHub · {source['value']}"
    elif source["type"] == "traffic":
        result["location"] = (
            "Traffic near home"
            if source["value"] == "home"
            else f"Traffic at {source['value']}"
        )
    elif source["type"] == "stocks":
        result["location"] = f"Symbols · {source['value']}"
    elif source["type"] == "news":
        result["location"] = f"News · {source['value']}"
    elif source["type"] == "events":
        home_location = os.getenv("HOMEBRAIN_WEATHER_LOCATION", "Austin, TX").strip()
        result["location"] = f"Within {source['value']} mi of {home_location}"
    else:
        result["location"] = "Text note"
    return result


class HomebrainHandler(BaseHTTPRequestHandler):
    server_version = "homebrain/0.2"

    def _send(self, status: int, raw: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'",
        )
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _json(self, status: int, body: dict[str, Any]) -> None:
        self._send(status, json.dumps(body).encode("utf-8"), "application/json; charset=utf-8")

    def _require_token(self) -> bool:
        expected = os.getenv("HOMEBRAIN_API_TOKEN", "").strip()
        if not expected:
            return True
        provided = self.headers.get("X-Homebrain-Token", "")
        return compare_digest(provided, expected)

    def _read_json(self) -> dict[str, Any]:
        try:
            content_length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError as exc:
            raise ValueError("invalid content length") from exc
        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            raise ValueError("invalid body size")
        try:
            payload = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("invalid JSON body") from exc
        if not isinstance(payload, dict):
            raise ValueError("Payload must be a JSON object")
        return payload

    def _static(self, path: str) -> bool:
        files = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/static/app.css": ("app.css", "text/css; charset=utf-8"),
            "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
        }
        asset = files.get(path)
        if not asset:
            return False
        filename, content_type = asset
        try:
            raw = (WEB_ROOT / filename).read_bytes()
        except OSError:
            self._json(500, {"error": "web application asset is unavailable"})
            return True
        self._send(200, raw, content_type)
        return True

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if self._static(path):
            return

        modules = self.server.modules  # type: ignore[attr-defined]
        store = self.server.store  # type: ignore[attr-defined]
        agent = self.server.agent  # type: ignore[attr-defined]
        if path == "/api/v1/health":
            self._json(
                200,
                {
                    "status": "ok",
                    "name": "homebrain",
                    "agent": "running" if agent.is_running() else "idle",
                },
            )
        elif path == "/api/v1/modules":
            self._json(200, {"modules": modules})
        elif path == "/api/v1/dashboard":
            self._json(200, store.dashboard())
        elif path == "/api/v1/sources":
            self._json(
                200,
                {"sources": [_public_source(item) for item in store.list_sources()]},
            )
        elif path == "/api/v1/agent/status":
            self._json(
                200,
                {
                    "running": agent.is_running(),
                    "interval_seconds": agent.interval_seconds,
                    **store.dashboard(),
                },
            )
        elif path == "/api/v1/agent/runs":
            self._json(200, {"runs": store.list_runs()})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._require_token():
            self._json(401, {"error": "unauthorized"})
            return
        path = urlsplit(self.path).path
        try:
            payload = self._read_json()
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
            return

        if path == "/api/v1/chat":
            try:
                api_base, model, _, _ = self.server.agent_config  # type: ignore[attr-defined]
                response = chat_with_model(
                    payload.get("messages"),
                    api_base,
                    model,
                    self.server.store.dashboard().get("dashboard"),  # type: ignore[attr-defined]
                )
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            except RuntimeError as exc:
                self._json(502, {"error": str(exc)})
                return
            self._json(200, response)
        elif path == "/api/v1/sources":
            try:
                name, source_type, value = validate_source(
                    payload.get("name"), payload.get("type"), payload.get("value")
                )
                source = self.server.store.add_source(  # type: ignore[attr-defined]
                    name, source_type, value
                )
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(201, {"source": _public_source(source)})
        elif path == "/api/v1/agent/run":
            if not self.server.agent.request_run():  # type: ignore[attr-defined]
                self._json(409, {"error": "an analysis run is already queued or running"})
                return
            self._json(202, {"status": "queued"})
        elif path == "/api/v1/bridge":
            try:
                response = build_bridge_response(
                    payload, self.server.modules  # type: ignore[attr-defined]
                )
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, response)
        else:
            self._json(404, {"error": "not found"})

    def do_PATCH(self) -> None:  # noqa: N802
        if not self._require_token():
            self._json(401, {"error": "unauthorized"})
            return
        path = urlsplit(self.path).path
        match = re.fullmatch(r"/api/v1/sources/([^/]+)", path)
        if not match:
            self._json(404, {"error": "not found"})
            return
        source_id = unquote(match.group(1))
        if not SOURCE_ID_PATTERN.fullmatch(source_id):
            self._json(404, {"error": "source not found"})
            return
        try:
            payload = self._read_json()
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
            return
        enabled = payload.get("enabled")
        if not isinstance(enabled, bool):
            self._json(400, {"error": "'enabled' must be a boolean"})
            return
        if not self.server.store.set_source_enabled(source_id, enabled):  # type: ignore[attr-defined]
            self._json(404, {"error": "source not found"})
            return
        self._json(200, {"status": "updated"})

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._require_token():
            self._json(401, {"error": "unauthorized"})
            return
        path = urlsplit(self.path).path
        match = re.fullmatch(r"/api/v1/sources/([^/]+)", path)
        if not match:
            self._json(404, {"error": "not found"})
            return
        source_id = unquote(match.group(1))
        if not SOURCE_ID_PATTERN.fullmatch(source_id):
            self._json(404, {"error": "source not found"})
            return
        if not self.server.store.delete_source(source_id):  # type: ignore[attr-defined]
            self._json(404, {"error": "source not found"})
            return
        self._json(200, {"status": "deleted"})


class HomebrainHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


def run() -> None:
    host = os.getenv("HOMEBRAIN_HOST", "0.0.0.0")
    port = int(os.getenv("HOMEBRAIN_PORT", "8787"))
    api_base, model, interval, database_path = load_agent_config()
    weather_location, weather_url = load_weather_config()

    server = HomebrainHTTPServer((host, port), HomebrainHandler)
    server.modules = load_modules()  # type: ignore[attr-defined]
    server.store = DashboardStore(database_path)  # type: ignore[attr-defined]
    server.store.ensure_weather_source(weather_location, weather_url)  # type: ignore[attr-defined]
    for source_id, name, source_type, value, seed_key in load_builtin_source_configs(
        weather_location
    ):
        server.store.ensure_builtin_source(  # type: ignore[attr-defined]
            source_id, source_type, name, value, seed_key
        )
    server.agent_config = (api_base, model, interval, database_path)  # type: ignore[attr-defined]
    server.agent = AnalysisAgent(  # type: ignore[attr-defined]
        server.store, api_base=api_base, model=model, interval_seconds=interval
    )
    server.agent.start()  # type: ignore[attr-defined]
    print(f"homebrain listening on http://{host}:{port}")
    try:
        server.serve_forever()
    finally:
        server.agent.stop()  # type: ignore[attr-defined]
        server.server_close()


if __name__ == "__main__":
    run()
