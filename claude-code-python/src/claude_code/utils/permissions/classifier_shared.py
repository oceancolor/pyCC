"""
Classifier shared - shared infrastructure for classifier-based permission systems.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def extract_tool_use_block(
    content: List[Dict[str, Any]],
    tool_name: str,
) -> Optional[Dict[str, Any]]:
    """Extract tool use block from message content by tool name."""
    for block in content:
        if block.get("type") == "tool_use" and block.get("name") == tool_name:
            return block
    return None


def parse_classifier_response(
    tool_use_block: Dict[str, Any],
    schema: Any,
) -> Optional[Any]:
    """Parse and validate classifier response from tool use block."""
    try:
        input_data = tool_use_block.get("input", {})
        if hasattr(schema, "parse"):
            return schema.parse(input_data)
        elif hasattr(schema, "validate"):
            return schema.validate(input_data)
        # If schema is a simple callable, call it
        if callable(schema):
            return schema(input_data)
        return input_data
    except Exception:
        return None
