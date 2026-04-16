"""
MCP tool output truncation utilities.  Port of mcpValidation.ts.

Despite the filename, the TS source handles MCP output truncation rather than
JSON-schema validation.  A thin validate_mcp_tool_input() shim is included for
API compatibility.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional, Union

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MCP_TOKEN_COUNT_THRESHOLD_FACTOR: float = 0.5
IMAGE_TOKEN_ESTIMATE: int = 1600
DEFAULT_MAX_MCP_OUTPUT_TOKENS: int = 25_000

MCPToolResult = Optional[Union[str, list[dict[str, Any]]]]


@dataclass
class McpValidationError:
    """Represents a validation/truncation error for MCP tool output."""
    message: str
    field: Optional[str] = None
    code: Optional[str] = None

    def __str__(self) -> str:
        return f"[{self.field}] {self.message}" if self.field else self.message


# ---------------------------------------------------------------------------
# Token cap helpers
# ---------------------------------------------------------------------------

def get_max_mcp_output_tokens() -> int:
    """Resolve MCP output token cap: env var → GrowthBook flag → default."""
    env_value = os.environ.get("MAX_MCP_OUTPUT_TOKENS", "")
    if env_value:
        try:
            parsed = int(env_value)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return DEFAULT_MAX_MCP_OUTPUT_TOKENS


def _get_max_mcp_output_chars() -> int:
    return get_max_mcp_output_tokens() * 4


def _get_truncation_message() -> str:
    limit = get_max_mcp_output_tokens()
    return (
        f"\n\n[OUTPUT TRUNCATED - exceeded {limit} token limit]\n\n"
        "The tool output was truncated. If this MCP server provides pagination "
        "or filtering tools, use them to retrieve specific portions of the data. "
        "If pagination is not available, inform the user that you are working "
        "with truncated output and results may be incomplete."
    )


# ---------------------------------------------------------------------------
# Size estimation
# ---------------------------------------------------------------------------

def _rough_token_count(text: str) -> int:
    return max(1, len(text) // 4)


def get_content_size_estimate(content: MCPToolResult) -> int:
    """Rough token-count estimate for MCP tool result content."""
    if not content:
        return 0
    if isinstance(content, str):
        return _rough_token_count(content)
    total = 0
    for block in content:
        if block.get("type") == "text":
            total += _rough_token_count(block.get("text", ""))
        elif block.get("type") == "image":
            total += IMAGE_TOKEN_ESTIMATE
    return total


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------

def _truncate_content_blocks(
    blocks: list[dict[str, Any]],
    max_chars: int,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    current_chars = 0
    for block in blocks:
        if block.get("type") == "text":
            remaining = max_chars - current_chars
            if remaining <= 0:
                break
            text: str = block.get("text", "")
            if len(text) <= remaining:
                result.append(block)
                current_chars += len(text)
            else:
                result.append({"type": "text", "text": text[:remaining]})
                break
        elif block.get("type") == "image":
            image_chars = IMAGE_TOKEN_ESTIMATE * 4
            if current_chars + image_chars <= max_chars:
                result.append(block)
                current_chars += image_chars
            # skip images that exceed budget (compression not implemented)
        else:
            result.append(block)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def mcp_content_needs_truncation(content: MCPToolResult) -> bool:
    """Return True if *content* likely exceeds the configured token cap."""
    if not content:
        return False
    estimate = get_content_size_estimate(content)
    cap = get_max_mcp_output_tokens()
    if estimate <= cap * MCP_TOKEN_COUNT_THRESHOLD_FACTOR:
        return False
    return estimate > cap  # stub: uses estimate as proxy for real token count


def truncate_mcp_content(content: MCPToolResult) -> MCPToolResult:
    """Truncate MCP tool result content to the configured token limit."""
    if not content:
        return content
    max_chars = _get_max_mcp_output_chars()
    truncation_msg = _get_truncation_message()
    if isinstance(content, str):
        return content[:max_chars] + truncation_msg
    truncated = _truncate_content_blocks(list(content), max_chars)
    truncated.append({"type": "text", "text": truncation_msg})
    return truncated


def truncate_mcp_content_if_needed(content: MCPToolResult) -> MCPToolResult:
    """Truncate *content* only if it exceeds the configured token limit."""
    if not mcp_content_needs_truncation(content):
        return content
    return truncate_mcp_content(content)


def validate_mcp_tool_input(
    schema: dict[str, Any],
    input_data: Any,
) -> tuple[bool, list[McpValidationError]]:
    """
    Validate MCP tool input against *schema* (stub — always returns valid).

    The TS source delegates validation to the MCP SDK upstream; this shim
    exists for API compatibility only.
    """
    _ = schema, input_data
    return True, []
