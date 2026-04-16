"""
Side query utility — lightweight API wrapper for queries outside the main
conversation loop. These calls don't affect the main conversation history.

Port of sideQuery.ts.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional, Union


# ---------------------------------------------------------------------------
# Types (mirrors TypeScript interfaces with Python equivalents)
# ---------------------------------------------------------------------------

MessageParam = dict[str, Any]
TextBlockParam = dict[str, Any]
Tool = dict[str, Any]
ToolChoice = dict[str, Any]


@dataclass
class SideQueryOptions:
    """Options for a side query call."""

    model: str
    messages: list[MessageParam]
    query_source: str  # querySource — for analytics attribution
    system: Optional[Union[str, list[TextBlockParam]]] = None
    tools: Optional[list[Tool]] = None
    tool_choice: Optional[ToolChoice] = None
    output_format: Optional[dict[str, Any]] = None
    max_tokens: int = 1024
    max_retries: int = 2
    skip_system_prompt_prefix: bool = False
    temperature: Optional[float] = None
    thinking: Optional[Union[int, bool]] = None  # budget_tokens or False
    stop_sequences: Optional[list[str]] = None


@dataclass
class SideQueryResponse:
    """Stub response from a side query."""

    content: list[dict[str, Any]]
    model: str
    stop_reason: Optional[str] = None
    usage: dict[str, int] = field(default_factory=lambda: {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    })
    request_id: Optional[str] = None

    def get_text(self) -> str:
        """Extract concatenated text from content blocks."""
        parts: list[str] = []
        for block in self.content:
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_first_user_message_text(messages: list[MessageParam]) -> str:
    """Extract text from the first user message (for fingerprint computation)."""
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        return block.get("text", "")
    return ""


def _build_thinking_config(
    thinking: Optional[Union[int, bool]],
    max_tokens: int,
) -> Optional[dict[str, Any]]:
    """Build thinking configuration dict from options."""
    if thinking is False:
        return {"type": "disabled"}
    if isinstance(thinking, int):
        return {
            "type": "enabled",
            "budget_tokens": min(thinking, max_tokens - 1),
        }
    return None


def _build_system_blocks(
    system: Optional[Union[str, list[TextBlockParam]]],
    attribution_header: Optional[str],
    skip_prefix: bool,
    cli_prefix: str = "",
) -> list[TextBlockParam]:
    """Assemble system prompt into a list of text blocks."""
    blocks: list[TextBlockParam] = []

    if attribution_header:
        blocks.append({"type": "text", "text": attribution_header})

    if not skip_prefix and cli_prefix:
        blocks.append({"type": "text", "text": cli_prefix})

    if isinstance(system, str):
        if system:
            blocks.append({"type": "text", "text": system})
    elif isinstance(system, list):
        blocks.extend(system)

    return blocks


# ---------------------------------------------------------------------------
# Main API
# ---------------------------------------------------------------------------

async def run_side_query(
    prompt: str,
    system: Optional[str] = None,
    model: str = "claude-3-5-haiku-20241022",
    max_tokens: int = 1024,
    query_source: str = "side_query",
) -> str:
    """
    Execute a side query — an independent API call that does not affect the
    main conversation history.

    This is a stub implementation that returns placeholder text.  The full
    implementation wires up to the Anthropic client (getAnthropicClient),
    injects OAuth attribution headers, and logs analytics events.

    Args:
        prompt: User-facing prompt text.
        system: Optional system prompt string.
        model: Model identifier.
        max_tokens: Maximum output tokens (default 1024).
        query_source: Analytics attribution label.

    Returns:
        Text response from the model (stub returns empty string).
    """
    opts = SideQueryOptions(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        query_source=query_source,
        system=system,
        max_tokens=max_tokens,
    )
    response = await _side_query(opts)
    return response.get_text()


async def _side_query(opts: SideQueryOptions) -> SideQueryResponse:
    """
    Full side query implementation (stub — wire up Anthropic client here).

    Steps in the real implementation:
      1. Obtain Anthropic client via getAnthropicClient(maxRetries, model)
      2. Compute model betas (getModelBetas) + structured-outputs beta if needed
      3. Compute fingerprint from first user message text
      4. Build attribution header (getAttributionHeader)
      5. Assemble system blocks (attribution + CLI prefix + caller system)
      6. Build thinking config if requested
      7. Normalise model string (strip [1m] suffix)
      8. Call client.beta.messages.create(...)
      9. Log analytics event (tengu_api_success)
      10. Update last API completion timestamp
    """
    first_text = _extract_first_user_message_text(opts.messages)
    _ = first_text  # would be used for fingerprint in real impl

    thinking_config = _build_thinking_config(opts.thinking, opts.max_tokens)
    _ = thinking_config  # used in real API call

    system_blocks = _build_system_blocks(
        opts.system,
        attribution_header=None,  # computed from fingerprint in real impl
        skip_prefix=opts.skip_system_prompt_prefix,
    )
    _ = system_blocks

    # Stub: return empty response
    return SideQueryResponse(
        content=[],
        model=opts.model,
        stop_reason="end_turn",
    )
