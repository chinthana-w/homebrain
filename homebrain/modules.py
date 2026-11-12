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
        "endpoint": "http://ollama:11434",
        "description": "Small on-device LLM runtime (model configurable).",
    },
    {
        "id": "jellyfin",
        "name": "Jellyfin",
        "kind": "media",
        "endpoint": "http://jellyfin:8096",
        "description": "Media server for local content streaming.",
    },
    {
        "id": "pihole",
        "name": "Pi-hole",
        "kind": "network",
        "endpoint": "http://pihole/admin",
        "description": "LAN DNS filtering and network controls.",
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
        normalized.append(
            {
                "id": module_id,
                "name": str(item.get("name") or module_id),
                "kind": str(item.get("kind") or "custom"),
                "endpoint": endpoint,
                "description": str(item.get("description") or "Custom module"),
            }
        )

    return normalized
