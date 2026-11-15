import json
import os
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
from xml.etree import ElementTree

from homebrain.agent import (
    AnalysisAgent,
    DashboardStore,
    EVENTS_SOURCE_ID,
    MAX_SOURCES,
    NEWS_SOURCE_ID,
    STOCKS_SOURCE_ID,
    TRAFFIC_SOURCE_ID,
    WEATHER_SOURCE_ID,
    _format_weather_response,
    _fetch_events_source,
    _fetch_github_source,
    _fetch_gmail_source,
    _fetch_news_source,
    _fetch_stocks_source,
    _fetch_traffic_source,
    _github_request,
    _validate_dashboard,
    chat_with_model,
    load_agent_config,
    load_builtin_source_configs,
    load_weather_config,
    validate_source,
)


class SourceValidationTests(unittest.TestCase):
    def test_text_source_is_normalized(self) -> None:
        self.assertEqual(
            validate_source("  Notes  ", "text", "  Hello home  "),
            ("Notes", "text", "Hello home"),
        )

    def test_url_credentials_and_redirect_fragments_are_rejected(self) -> None:
        for value in (
            "file:///etc/passwd",
            "https://user:pass@example.com/feed",
            "https://example.com/feed#fragment",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_source("Feed", "url", value)

    def test_gmail_and_github_sources_are_narrowly_validated(self) -> None:
        self.assertEqual(
            validate_source(" Inbox ", "gmail", " INBOX "),
            ("Inbox", "gmail", "inbox"),
        )
        self.assertEqual(
            validate_source(" Repos ", "github", "octo/homebrain, octo/site"),
            ("Repos", "github", "octo/homebrain, octo/site"),
        )
        for source_type, value in (
            ("gmail", "all mail"),
            ("github", "https://github.com/octo/repo"),
            ("github", "../repo"),
            ("github", "octo/repo, octo/repo"),
            ("github", ","),
        ):
            with self.subTest(source_type=source_type, value=value), self.assertRaises(
                ValueError
            ):
                validate_source("Source", source_type, value)

    def test_live_feed_sources_are_normalized_and_bounded(self) -> None:
        self.assertEqual(validate_source("Traffic", "traffic", "HOME"), ("Traffic", "traffic", "home"))
        self.assertEqual(
            validate_source("Traffic", "traffic", "30.2672, -97.7431"),
            ("Traffic", "traffic", "30.2672,-97.7431"),
        )
        self.assertEqual(
            validate_source("Markets", "stocks", "spy, qqq, DIA"),
            ("Markets", "stocks", "SPY, QQQ, DIA"),
        )
        self.assertEqual(validate_source("News", "news", "Austin, TX"), ("News", "news", "Austin, TX"))
        self.assertEqual(validate_source("Events", "events", "025"), ("Events", "events", "25"))
        for source_type, value in (
            ("traffic", "91,0"),
            ("traffic", "0,nan"),
            ("stocks", "SPY,"),
            ("stocks", "SPY,spy"),
            ("events", "0"),
            ("events", "101"),
        ):
            with self.subTest(source_type=source_type, value=value), self.assertRaises(ValueError):
                validate_source("Source", source_type, value)

    def test_traffic_fetch_formats_one_nearby_segment(self) -> None:
        with (
            patch.dict(os.environ, {"HOMEBRAIN_TRAFFIC_API_KEY": "traffic-key"}),
            patch(
                "homebrain.agent._read_provider_json",
                return_value={
                    "flowSegmentData": {
                        "currentSpeed": 25,
                        "freeFlowSpeed": 50,
                        "confidence": 0.9,
                        "roadClosure": False,
                        "frc": "FRC2",
                    }
                },
            ) as provider_request,
        ):
            snapshot = _fetch_traffic_source("home")

        self.assertIn("Austin, TX", snapshot)
        self.assertIn("25 km/h", snapshot)
        self.assertIn("50% below free-flow speed", snapshot)
        query = parse_qs(urlsplit(provider_request.call_args.args[0].full_url).query)
        self.assertEqual(query["point"], ["30.2672,-97.7431"])
        self.assertEqual(query["key"], ["traffic-key"])

    def test_stock_fetch_formats_quotes_and_timestamps(self) -> None:
        with (
            patch.dict(os.environ, {"HOMEBRAIN_STOCKS_API_KEY": "stocks-key"}),
            patch(
                "homebrain.agent._read_provider_json",
                return_value={"c": 102.5, "d": 2.5, "dp": 2.5, "t": 1794506400},
            ) as provider_request,
        ):
            snapshot = _fetch_stocks_source("SPY")

        self.assertIn("SPY: $102.50", snapshot)
        self.assertIn("+2.50%", snapshot)
        query = parse_qs(urlsplit(provider_request.call_args.args[0].full_url).query)
        self.assertEqual(query["symbol"], ["SPY"])
        self.assertEqual(query["token"], ["stocks-key"])

    def test_stock_fetch_reports_missing_provider_quotes(self) -> None:
        with (
            patch.dict(os.environ, {"HOMEBRAIN_STOCKS_API_KEY": "stocks-key"}),
            patch(
                "homebrain.agent._read_provider_json",
                return_value={"c": 0, "d": None, "dp": None, "t": 0},
            ),
            self.assertRaisesRegex(ValueError, "no current quote"),
        ):
            _fetch_stocks_source("INVALID")

    def test_news_fetch_returns_recent_headlines_without_a_key(self) -> None:
        with patch(
            "homebrain.agent._read_provider_xml",
            return_value=ElementTree.fromstring(
                "<rss><channel><item><title>Austin transit update</title>"
                "<source>example.test</source><pubDate>Thu, 12 Nov 2026 12:00:00 GMT</pubDate>"
                "<link>https://example.test/article</link></item></channel></rss>"
            ),
        ) as provider_request:
            snapshot = _fetch_news_source("Austin, TX")

        self.assertIn("unverified", snapshot)
        self.assertIn("Austin transit update", snapshot)
        query = parse_qs(urlsplit(provider_request.call_args.args[0].full_url).query)
        self.assertEqual(query["q"], ["Austin, TX"])
        self.assertNotIn("key", query)

    def test_events_fetch_uses_home_location_and_radius(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "HOMEBRAIN_TICKETMASTER_API_KEY": "events-key",
                    "HOMEBRAIN_WEATHER_LOCATION": "Austin, TX",
                    "HOMEBRAIN_WEATHER_LATITUDE": "30.2672",
                    "HOMEBRAIN_WEATHER_LONGITUDE": "-97.7431",
                },
            ),
            patch(
                "homebrain.agent._read_provider_json",
                return_value={
                    "_embedded": {
                        "events": [
                            {
                                "name": "Local concert",
                                "dates": {"start": {"localDate": "2026-11-20", "localTime": "19:00:00"}},
                                "url": "https://example.test/event",
                                "_embedded": {
                                    "venues": [
                                        {"name": "Moody Center", "city": {"name": "Austin"}}
                                    ]
                                },
                            }
                        ]
                    }
                },
            ) as provider_request,
        ):
            snapshot = _fetch_events_source("25")

        self.assertIn("within 25 miles of Austin, TX", snapshot)
        self.assertIn("Local concert", snapshot)
        self.assertIn("Moody Center, Austin", snapshot)
        query = parse_qs(urlsplit(provider_request.call_args.args[0].full_url).query)
        self.assertEqual(query["latlong"], ["30.2672,-97.7431"])
        self.assertEqual(query["radius"], ["25"])
        self.assertEqual(query["apikey"], ["events-key"])

    def test_gmail_fetch_requests_only_inbox_metadata_and_ignores_body(self) -> None:
        with (
            patch("homebrain.agent._gmail_access_token", return_value="access-token"),
            patch(
                "homebrain.agent._read_provider_json",
                side_effect=[
                    {"messages": [{"id": "message/1"}]},
                    {
                        "snippet": "private body snippet",
                        "labelIds": ["INBOX", "UNREAD"],
                        "payload": {
                            "headers": [
                                {"name": "From", "value": "sender@example.com"},
                                {"name": "Subject", "value": "Home update"},
                                {"name": "Date", "value": "Thu, 12 Nov 2026 10:00:00 -0600"},
                            ],
                            "body": {"data": "private body"},
                        },
                    },
                ],
            ) as provider_request,
        ):
            snapshot = _fetch_gmail_source()

        self.assertIn("sender@example.com", snapshot)
        self.assertIn("Home update", snapshot)
        self.assertIn("UNREAD", snapshot)
        self.assertNotIn("private body", snapshot)
        listing_request = provider_request.call_args_list[0].args[0]
        self.assertEqual(
            parse_qs(urlsplit(listing_request.full_url).query),
            {"labelIds": ["INBOX"], "maxResults": ["20"]},
        )
        metadata_request = provider_request.call_args_list[1].args[0]
        query = parse_qs(urlsplit(metadata_request.full_url).query)
        self.assertEqual(query["format"], ["metadata"])
        self.assertEqual(
            query["metadataHeaders"], ["From", "Subject", "Date"]
        )
        self.assertEqual(metadata_request.get_header("Authorization"), "Bearer access-token")

    def test_github_fetch_returns_activity_not_repository_contents(self) -> None:
        with patch(
            "homebrain.agent._github_request",
            side_effect=[
                [
                    {
                        "number": 1,
                        "title": "Fix sensor alert",
                        "state": "open",
                        "updated_at": "2026-11-12T10:00:00Z",
                        "labels": [{"name": "bug"}],
                    }
                ],
                [
                    {
                        "number": 2,
                        "title": "Improve dashboard",
                        "state": "open",
                        "updated_at": "2026-11-12T11:00:00Z",
                    }
                ],
                [
                    {
                        "name": "v1.2",
                        "tag_name": "v1.2",
                        "published_at": "2026-11-12T12:00:00Z",
                    }
                ],
            ],
        ) as github_request:
            snapshot = _fetch_github_source("octo/homebrain")

        self.assertIn("Fix sensor alert", snapshot)
        self.assertIn("Improve dashboard", snapshot)
        self.assertIn("v1.2", snapshot)
        self.assertNotIn("source code", snapshot.lower())
        self.assertEqual(github_request.call_count, 3)

    def test_github_token_is_sent_only_as_a_bearer_header(self) -> None:
        with (
            patch.dict(os.environ, {"HOMEBRAIN_GITHUB_TOKEN": "ghp_private"}),
            patch("homebrain.agent._read_provider_json", return_value=[]) as provider_request,
        ):
            _github_request("https://api.github.com/repos/octo/homebrain/issues")

        request = provider_request.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Authorization"), "Bearer ghp_private")
        self.assertNotIn("ghp_private", request.full_url)

    def test_dashboard_output_is_validated_and_bounded(self) -> None:
        result = _validate_dashboard(
            json.dumps(
                {
                    "headline": "Home is calm",
                    "metrics": [
                        {"label": str(index), "value": "ok"} for index in range(12)
                    ],
                    "insights": [
                        {
                            "title": f"Finding {index}",
                            "body": "Evidence",
                            "priority": "high",
                        }
                        for index in range(15)
                    ],
                }
            )
        )
        self.assertEqual(len(result["metrics"]), 8)
        self.assertEqual(len(result["insights"]), 12)

    def test_source_count_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store = DashboardStore(str(Path(tempdir) / "sources.sqlite3"))
            for index in range(MAX_SOURCES):
                store.add_source(f"Note {index}", "text", "A note.")
            with self.assertRaisesRegex(ValueError, f"maximum of {MAX_SOURCES}"):
                store.add_source("Extra note", "text", "Another note.")

    def test_weather_defaults_to_austin_in_central_time_and_fahrenheit(self) -> None:
        with patch.dict(
            os.environ,
            {
                "HOMEBRAIN_WEATHER_LOCATION": "Austin, TX",
                "HOMEBRAIN_WEATHER_LATITUDE": "30.2672",
                "HOMEBRAIN_WEATHER_LONGITUDE": "-97.7431",
                "HOMEBRAIN_WEATHER_TIMEZONE": "America/Chicago",
            },
        ):
            location, url = load_weather_config()
        self.assertEqual(location, "Austin, TX")
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query["latitude"], ["30.2672"])
        self.assertEqual(query["longitude"], ["-97.7431"])
        self.assertEqual(query["timezone"], ["America/Chicago"])
        self.assertEqual(query["temperature_unit"], ["fahrenheit"])

    def test_analysis_interval_defaults_to_fifteen_minutes(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            _, _, interval, _ = load_agent_config()
        self.assertEqual(interval, 900)

    def test_weather_formatter_includes_current_and_forecast_context(self) -> None:
        snapshot = _format_weather_response(
            {
                "timezone": "America/Chicago",
                "current": {
                    "time": "2026-11-12T10:00",
                    "temperature_2m": 72,
                    "apparent_temperature": 70,
                    "relative_humidity_2m": 45,
                    "weather_code": 61,
                    "wind_speed_10m": 4,
                    "wind_gusts_10m": 8,
                    "precipitation": 0.1,
                },
                "hourly": {
                    "time": ["2026-11-12T10:00", "2026-11-12T11:00"],
                    "temperature_2m": [72, 68],
                    "precipitation_probability": [30, 80],
                    "weather_code": [61, 63],
                    "wind_speed_10m": [4, 6],
                },
                "daily": {
                    "time": ["2026-11-12"],
                    "weather_code": [63],
                    "temperature_2m_max": [74],
                    "temperature_2m_min": [58],
                    "precipitation_probability_max": [80],
                    "precipitation_sum": [0.2],
                    "sunrise": ["2026-11-12T06:30"],
                    "sunset": ["2026-11-12T17:30"],
                },
            },
            "Austin, TX",
        )
        self.assertIn("Austin, TX", snapshot)
        self.assertIn("light rain", snapshot)
        self.assertIn("precipitation chance 80%", snapshot)
        self.assertIn("sunset 2026-11-12T17:30", snapshot)

    def test_chat_uses_dashboard_as_reference_context(self) -> None:
        dashboard = {"headline": "Temperature is 21 C"}
        messages = [{"role": "user", "content": "What is the temperature?"}]
        with patch(
            "homebrain.agent._model_request", return_value="21 C"
        ) as model_request:
            response = chat_with_model(messages, dashboard=dashboard)
        self.assertEqual(response["content"], "21 C")
        model_messages = model_request.call_args.args[0]
        self.assertEqual(model_messages[0]["role"], "system")
        self.assertIn("21 C", model_messages[1]["content"])
        self.assertIn("untrusted", model_messages[0]["content"])


class AnalysisAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = DashboardStore(str(Path(self.tempdir.name) / "homebrain.sqlite3"))

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_empty_source_set_updates_dashboard_without_calling_model(self) -> None:
        agent = AnalysisAgent(self.store)
        with patch("homebrain.agent._model_request") as model_request:
            agent.run_once()
        model_request.assert_not_called()
        dashboard = self.store.dashboard()
        self.assertEqual(dashboard["latest_run"]["status"], "empty")
        self.assertIn("Add a data source", dashboard["dashboard"]["headline"])

    def test_weather_source_is_seeded_once_and_respects_user_changes(self) -> None:
        self.store.ensure_weather_source("Austin Weather", "https://example.test/first")
        self.store.set_source_enabled(WEATHER_SOURCE_ID, False)
        self.store.ensure_weather_source("Austin, TX Weather", "https://example.test/updated")
        source = self.store.list_sources()[0]
        self.assertEqual(source["name"], "Austin, TX Weather")
        self.assertEqual(source["value"], "https://example.test/updated")
        self.assertFalse(source["enabled"])
        self.store.delete_source(WEATHER_SOURCE_ID)
        self.store.ensure_weather_source("Austin Weather", "https://example.test/again")
        self.assertEqual(self.store.list_sources(), [])

    def test_live_sources_are_seeded_once_with_default_watchlist(self) -> None:
        configs = load_builtin_source_configs("Austin, TX")
        for source_id, name, source_type, value, seed_key in configs:
            self.store.ensure_builtin_source(source_id, source_type, name, value, seed_key)

        sources = {source["id"]: source for source in self.store.list_sources()}
        self.assertEqual(
            set(sources),
            {TRAFFIC_SOURCE_ID, STOCKS_SOURCE_ID, NEWS_SOURCE_ID, EVENTS_SOURCE_ID},
        )
        self.assertEqual(sources[STOCKS_SOURCE_ID]["value"], "SPY, QQQ, DIA")
        self.assertEqual(sources[EVENTS_SOURCE_ID]["value"], "25")
        self.store.set_source_enabled(TRAFFIC_SOURCE_ID, False)
        for source_id, name, source_type, value, seed_key in configs:
            self.store.ensure_builtin_source(source_id, source_type, name, value, seed_key)
        self.assertFalse(
            next(source for source in self.store.list_sources() if source["id"] == TRAFFIC_SOURCE_ID)["enabled"]
        )
        self.store.delete_source(NEWS_SOURCE_ID)
        for source_id, name, source_type, value, seed_key in configs:
            self.store.ensure_builtin_source(source_id, source_type, name, value, seed_key)
        self.assertNotIn(NEWS_SOURCE_ID, {source["id"] for source in self.store.list_sources()})

    def test_run_analyzes_sources_and_persists_dashboard(self) -> None:
        self.store.add_source("Kitchen sensor", "text", "Temperature is 21 C.")
        expected = {
            "headline": "Everything is steady.",
            "metrics": [{"label": "Temperature", "value": "21 C"}],
            "insights": [],
        }
        with patch("homebrain.agent._model_request", return_value=json.dumps(expected)) as request:
            AnalysisAgent(self.store).run_once()

        request.assert_called_once()
        args = request.call_args.args
        self.assertIn("Kitchen sensor", args[0][1]["content"])
        dashboard = self.store.dashboard()
        self.assertEqual(dashboard["latest_run"]["status"], "completed")
        self.assertEqual(dashboard["dashboard"]["metrics"][0]["value"], "21 C")
        self.assertEqual(request.call_args.kwargs["max_tokens"], 800)
        self.assertEqual(request.call_args.kwargs["timeout"], 300)

    def test_analysis_sends_live_feed_snapshots_to_local_model(self) -> None:
        source_types = ("traffic", "stocks", "news", "events")
        for source_type in source_types:
            self.store.add_source(source_type.title(), source_type, "sample")
        with (
            patch(
                "homebrain.agent._fetch_source",
                side_effect=lambda source: f"{source['type']} provider snapshot",
            ),
            patch(
                "homebrain.agent._model_request",
                return_value='{"headline":"Signals updated","metrics":[],"insights":[]}',
            ) as model_request,
        ):
            AnalysisAgent(self.store).run_once()

        prompt = model_request.call_args.args[0][1]["content"]
        for source_type in source_types:
            self.assertIn(f"{source_type} provider snapshot", prompt)
        self.assertEqual(self.store.dashboard()["latest_run"]["status"], "completed")

    def test_failed_sources_do_not_reduce_successful_source_context_budget(self) -> None:
        self.store.add_source("Good source", "text", "content")
        self.store.add_source("Offline source one", "text", "content")
        self.store.add_source("Offline source two", "text", "content")

        def fetch(source: dict[str, str]) -> str:
            if source["name"].startswith("Offline"):
                raise ValueError("provider unavailable")
            return f"{'x' * 5990}TAIL"

        with (
            patch("homebrain.agent._fetch_source", side_effect=fetch),
            patch(
                "homebrain.agent._model_request",
                return_value='{"headline":"Signals updated","metrics":[],"insights":[]}',
            ) as model_request,
        ):
            AnalysisAgent(self.store).run_once()

        self.assertIn("TAIL", model_request.call_args.args[0][1]["content"])
        latest_run = self.store.dashboard()["latest_run"]
        self.assertEqual(latest_run["status"], "partial")
        self.assertEqual(
            {error["source"] for error in latest_run["errors"]},
            {"Offline source one", "Offline source two"},
        )

    def test_partial_source_failure_is_visible_with_successful_analysis(self) -> None:
        self.store.add_source("Good source", "text", "All is well.")
        self.store.add_source("Offline source", "url", "https://example.com/feed")

        def fetch(source: dict[str, str]) -> str:
            if source["name"] == "Offline source":
                raise OSError("connection refused")
            return "All is well."

        with (
            patch(
                "homebrain.agent._fetch_source",
                side_effect=fetch,
            ),
            patch(
                "homebrain.agent._model_request",
                return_value='{"headline":"All is well","metrics":[],"insights":[]}',
            ),
        ):
            AnalysisAgent(self.store).run_once()

        dashboard = self.store.dashboard()
        self.assertEqual(dashboard["latest_run"]["status"], "partial")
        self.assertEqual(dashboard["latest_run"]["errors"][0]["source"], "Offline source")

    def test_invalid_model_output_does_not_replace_dashboard(self) -> None:
        self.store.add_source("Notes", "text", "A note.")
        with patch(
            "homebrain.agent._model_request",
            side_effect=[
                '{"headline":"Last good dashboard","metrics":[],"insights":[]}',
                "not json",
            ],
        ):
            agent = AnalysisAgent(self.store)
            agent.run_once()
            agent.run_once()
        dashboard = self.store.dashboard()
        self.assertEqual(dashboard["latest_run"]["status"], "error")
        self.assertEqual(dashboard["dashboard"]["headline"], "Last good dashboard")
        self.assertIn("valid dashboard JSON", dashboard["latest_run"]["errors"][0]["error"])


if __name__ == "__main__":
    unittest.main()
