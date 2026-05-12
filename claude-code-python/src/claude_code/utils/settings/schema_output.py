"""
Schema output - generates JSON schema output for settings validation.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional


SETTINGS_JSON_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Claude Code Settings",
    "type": "object",
    "properties": {
        "apiKeyHelper": {"type": "string"},
        "cleanupPeriodDays": {"type": "number"},
        "disableAllHooks": {"type": "boolean"},
        "allowManagedHooksOnly": {"type": "boolean"},
        "hooks": {"type": "object"},
        "includeCoAuthoredBy": {"type": "boolean"},
        "permissions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "toolName": {"type": "string"},
                    "behavior": {"type": "string", "enum": ["allow", "deny", "ask"]},
                    "ruleContent": {"type": "string"},
                },
                "required": ["toolName", "behavior"],
            },
        },
        "model": {"type": "string"},
        "smallFastModel": {"type": "string"},
        "env": {"type": "object"},
        "preferredNotifChannel": {"type": "string"},
        "theme": {"type": "string"},
        "verbose": {"type": "boolean"},
        "maxTokens": {"type": "number"},
    },
    "additionalProperties": True,
}


def get_settings_schema() -> Dict[str, Any]:
    """Get the JSON schema for settings validation."""
    return SETTINGS_JSON_SCHEMA


def render_settings_schema_output(
    indent: int = 2,
) -> str:
    """Render the settings JSON schema as a string."""
    return json.dumps(SETTINGS_JSON_SCHEMA, indent=indent)
