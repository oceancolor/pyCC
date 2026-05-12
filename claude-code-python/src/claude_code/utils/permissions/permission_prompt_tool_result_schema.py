"""
Permission prompt tool result schema.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


PERMISSION_PROMPT_TOOL_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "behavior": {
            "type": "string",
            "enum": ["allow", "deny", "ask"],
            "description": "The permission decision",
        },
        "updatedInput": {
            "type": "object",
            "description": "Optional updated tool input (for allow decisions)",
        },
        "message": {
            "type": "string",
            "description": "Optional message to include with the decision",
        },
    },
    "required": ["behavior"],
}


def validate_permission_prompt_tool_result(data: Any) -> Optional[Dict[str, Any]]:
    """Validate a permission prompt tool result."""
    if not isinstance(data, dict):
        return None
    behavior = data.get("behavior")
    if behavior not in ("allow", "deny", "ask"):
        return None
    return {
        "behavior": behavior,
        "updatedInput": data.get("updatedInput"),
        "message": data.get("message"),
    }


def create_allow_result(updated_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create an allow permission result."""
    result: Dict[str, Any] = {"behavior": "allow"}
    if updated_input is not None:
        result["updatedInput"] = updated_input
    return result


def create_deny_result(message: Optional[str] = None) -> Dict[str, Any]:
    """Create a deny permission result."""
    result: Dict[str, Any] = {"behavior": "deny"}
    if message:
        result["message"] = message
    return result
