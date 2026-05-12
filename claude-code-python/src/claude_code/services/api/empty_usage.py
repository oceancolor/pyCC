"""
Zero-initialized usage object.
Ported from services/api/emptyUsage.ts

Extracted from logging.ts so that bridge/replBridge can import it without
transitively pulling in api/errors.ts → utils/messages.ts → the world.
"""
from __future__ import annotations

from typing import Any, Dict

EMPTY_USAGE: Dict[str, Any] = {
    "input_tokens": 0,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0,
    "output_tokens": 0,
    "server_tool_use": {
        "web_search_requests": 0,
        "web_fetch_requests": 0,
    },
    "service_tier": "standard",
    "cache_creation": {
        "ephemeral_1h_input_tokens": 0,
        "ephemeral_5m_input_tokens": 0,
    },
    "inference_geo": "",
    "iterations": [],
    "speed": "standard",
}
