"""
Permission update schema - Zod-like validation schemas for permission updates.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def validate_permission_update_schema(data: Any) -> Optional[Dict[str, Any]]:
    """Validate a permission update against the expected schema."""
    if not isinstance(data, dict):
        return None
    required = {"operation", "behavior", "toolName"}
    if not required.issubset(data.keys()):
        return None
    if data.get("operation") not in ("add", "remove"):
        return None
    if data.get("behavior") not in ("allow", "deny", "ask"):
        return None
    if not isinstance(data.get("toolName"), str):
        return None
    return {
        "operation": data["operation"],
        "behavior": data["behavior"],
        "toolName": data["toolName"],
        "ruleContent": data.get("ruleContent"),
        "source": data.get("source"),
    }


PERMISSION_UPDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": ["add", "remove"]},
        "behavior": {"type": "string", "enum": ["allow", "deny", "ask"]},
        "toolName": {"type": "string"},
        "ruleContent": {"type": "string"},
        "source": {"type": "string"},
    },
    "required": ["operation", "behavior", "toolName"],
}
