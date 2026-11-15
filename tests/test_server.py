from __future__ import annotations

import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from homebrain.agent import DashboardStore
from homebrain.modules import DEFAULT_MODULES, load_modules
from homebrain.server import (
    HomebrainHandler,
    HomebrainHTTPServer,
    _public_source,
    build_bridge_response,
)


class LoadModulesTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("HOMEBRAIN_MODULES_JSON", None)

    def test_defaults_are_present(self) -> None:
        modules = load_modules()
        self.assertEqual(modules, DEFAULT_MODULES)

    def test_env_override_requires_shape(self) -> None:
        os.environ["HOMEBRAIN_MODULES_JSON"] = '{"id":"bad"}'
        with self.assertRaises(ValueError):
            load_modules()


class BridgeTests(unittest.TestCase):
    def test_valid_request(self) -> None:
        payload = {"target": "llm", "message": "summarize this"}
        response = build_bridge_response(payload, DEFAULT_MODULES)
        self.assertEqual(response["status"], "accepted")
        self.assertEqual(response["target"], "llm")
        self.assertEqual(response["target_endpoint"], "http://llama-cpp:8080/v1")

    def test_unknown_target_rejected(self) -> None:
        payload = {"target": "missing", "message": "hi"}
        with self.assertRaises(ValueError):
            build_bridge_response(payload, DEFAULT_MODULES)


class _IdleAgent:
    interval_seconds = 3600

    def is_running(self) -> bool:
        return False

    def request_run(self) -> bool:
        return True


class HTTPAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.server = HomebrainHTTPServer(("127.0.0.1", 0), HomebrainHandler)
        self.server.modules = DEFAULT_MODULES
        self.server.store = DashboardStore(
            str(Path(self.tempdir.name) / "homebrain.sqlite3")
        )
        self.server.agent = _IdleAgent()
        self.server.agent_config = (
            "http://localhost:8080/v1",
            "homebrain-coder",
            3600,
            "",
        )
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.base = f"127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.tempdir.cleanup()

    def request(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> tuple[int, dict[str, object] | str]:
        connection = http.client.HTTPConnection(*self.base.split(":"))
        raw = json.dumps(payload) if payload is not None else None
        headers = {"Content-Type": "application/json"} if raw else {}
        connection.request(method, path, body=raw, headers=headers)
        response = connection.getresponse()
        body = response.read()
        status = response.status
        connection.close()
        if response.getheader("Content-Type", "").startswith("application/json"):
            return status, json.loads(body)
        return status, body.decode("utf-8")

    def test_dashboard_app_serves_responsive_subsections(self) -> None:
        status, page = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn('name="viewport"', page)
        self.assertIn('id="page-chat"', page)
        self.assertIn('id="page-sources"', page)
        self.assertIn('id="page-activity"', page)
        self.assertIn('id="page-settings"', page)
        self.assertIn('<option value="gmail">', page)
        self.assertIn('<option value="github">', page)
        for source_type in ("traffic", "stocks", "news", "events"):
            self.assertIn(f'<option value="{source_type}">', page)
        css_status, css = self.request("GET", "/static/app.css")
        self.assertEqual(css_status, 200)
        self.assertIn("@media (max-width: 600px)", css)

    def test_chat_api_forwards_chat_to_local_model(self) -> None:
        messages = [{"role": "user", "content": "Hello"}]
        with patch(
            "homebrain.server.chat_with_model",
            return_value={"role": "assistant", "content": "Hi"},
        ) as chat:
            status, response = self.request(
                "POST", "/api/v1/chat", {"messages": messages}
            )
        self.assertEqual(status, 200)
        self.assertEqual(response["content"], "Hi")
        self.assertEqual(chat.call_args.args[:3], (messages, "http://localhost:8080/v1", "homebrain-coder"))
        self.assertIsNone(chat.call_args.args[3])

    def test_source_api_does_not_return_url_query_secrets(self) -> None:
        status, created = self.request(
            "POST",
            "/api/v1/sources",
            {
                "name": "Private feed",
                "type": "url",
                "value": "http://127.0.0.1:8123/feed?token=secret",
            },
        )
        self.assertEqual(status, 201)
        self.assertNotIn("secret", json.dumps(created))
        status, listing = self.request("GET", "/api/v1/sources")
        self.assertEqual(status, 200)
        self.assertNotIn("secret", json.dumps(listing))
        source_id = listing["sources"][0]["id"]
        status, _ = self.request(
            "PATCH", f"/api/v1/sources/{source_id}", {"enabled": False}
        )
        self.assertEqual(status, 200)
        status, listing = self.request("GET", "/api/v1/sources")
        self.assertFalse(listing["sources"][0]["enabled"])

    def test_protected_api_requires_configured_token(self) -> None:
        with patch.dict(os.environ, {"HOMEBRAIN_API_TOKEN": "secret"}):
            status, response = self.request(
                "POST", "/api/v1/agent/run", {}
            )
        self.assertEqual(status, 401)
        self.assertEqual(response["error"], "unauthorized")

    def test_weather_source_location_hides_api_query_parameters(self) -> None:
        public = _public_source(
            {
                "id": "weather-source",
                "name": "Austin, TX",
                "type": "weather",
                "value": "https://api.open-meteo.com/v1/forecast?latitude=30&secret=value",
                "enabled": True,
            }
        )
        self.assertEqual(
            public["location"], "https://api.open-meteo.com/v1/forecast"
        )
        self.assertNotIn("secret", json.dumps(public))

    def test_live_source_metadata_explains_configured_target(self) -> None:
        with patch.dict(os.environ, {"HOMEBRAIN_WEATHER_LOCATION": "Austin, TX"}):
            traffic = _public_source(
                {"id": "1", "name": "Traffic", "type": "traffic", "value": "home", "enabled": True}
            )
            stocks = _public_source(
                {"id": "2", "name": "Markets", "type": "stocks", "value": "SPY, QQQ", "enabled": True}
            )
            news = _public_source(
                {"id": "3", "name": "News", "type": "news", "value": "Austin, TX", "enabled": True}
            )
            events = _public_source(
                {"id": "4", "name": "Events", "type": "events", "value": "25", "enabled": True}
            )

        self.assertEqual(traffic["location"], "Traffic near home")
        self.assertEqual(stocks["location"], "Symbols · SPY, QQQ")
        self.assertEqual(news["location"], "News · Austin, TX")
        self.assertEqual(events["location"], "Within 25 mi of Austin, TX")
        for public in (traffic, stocks, news, events):
            self.assertNotIn("value", public)

    def test_authenticated_source_records_never_include_provider_tokens(self) -> None:
        with patch.dict(
            os.environ,
            {
                "HOMEBRAIN_GITHUB_TOKEN": "github-secret",
                "HOMEBRAIN_GMAIL_REFRESH_TOKEN": "google-secret",
            },
        ):
            status, github = self.request(
                "POST",
                "/api/v1/sources",
                {
                    "name": "Work repositories",
                    "type": "github",
                    "value": "octo/homebrain",
                },
            )
            self.assertEqual(status, 201)
            self.assertEqual(github["source"]["location"], "GitHub · octo/homebrain")
            status, gmail = self.request(
                "POST",
                "/api/v1/sources",
                {"name": "Inbox", "type": "gmail", "value": "inbox"},
            )
            self.assertEqual(status, 201)
            self.assertEqual(gmail["source"]["location"], "Gmail inbox metadata")
            status, listing = self.request("GET", "/api/v1/sources")

        self.assertEqual(status, 200)
        self.assertNotIn("github-secret", json.dumps(listing))
        self.assertNotIn("google-secret", json.dumps(listing))


if __name__ == "__main__":
    unittest.main()
