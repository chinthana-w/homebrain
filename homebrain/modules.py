"""Module registry for the Homebrain gateway."""

from __future__ import annotations

import json
import os
from typing import Any

DEFAULT_MODULES: list[dict[str, Any]] = [
    {
        "id": "llm",
        "name": "Local LLM",
        "kind": "ai",
        "endpoint": "http://llama-cpp:8080/v1",
        "description": "Local GGUF inference server with an OpenAI-compatible API.",
        "public_port": 8080,
        "public_path": "/v1/models",
    },
    {
        "id": "jellyfin",
        "name": "Jellyfin",
        "kind": "media",
        "endpoint": "http://jellyfin:8096",
        "description": "Media server for local content streaming.",
        "public_port": 8096,
        "public_path": "/web/",
    },
    {
        "id": "pihole",
        "name": "Pi-hole",
        "kind": "network",
        "endpoint": "http://pihole/admin",
        "description": "LAN DNS filtering and network controls.",
        "public_port": 8081,
        "public_path": "/admin/",
    },
]


def load_modules() -> list[dict[str, Any]]:
    """Return configured modules, optionally overridden by env JSON."""
    raw = os.getenv("HOMEBRAIN_MODULES_JSON", "").strip()
    if not raw:
        return list(DEFAULT_MODULES)

    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError("HOMEBRAIN_MODULES_JSON must be a JSON list")

    normalized: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            raise ValueError("Each module must be a JSON object")
        module_id = str(item.get("id", "")).strip()
        endpoint = str(item.get("endpoint", "")).strip()
        if not module_id or not endpoint:
            raise ValueError("Each module requires non-empty 'id' and 'endpoint'")
        public_port = item.get("public_port")
        if public_port is not None:
            if isinstance(public_port, bool):
                raise ValueError("Module 'public_port' must be an integer from 1 to 65535")
            try:
                public_port = int(public_port)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "Module 'public_port' must be an integer from 1 to 65535"
                ) from exc
            if not 1 <= public_port <= 65535:
                raise ValueError("Module 'public_port' must be an integer from 1 to 65535")
        public_path = str(item.get("public_path") or "/").strip()
        if not public_path.startswith("/") or public_path.startswith("//"):
            raise ValueError("Module 'public_path' must be an absolute path")
        normalized.append(
            {
                "id": module_id,
                "name": str(item.get("name") or module_id),
                "kind": str(item.get("kind") or "custom"),
                "endpoint": endpoint,
                "description": str(item.get("description") or "Custom module"),
                "public_port": public_port,
                "public_path": public_path,
            }
        )

    return normalized
