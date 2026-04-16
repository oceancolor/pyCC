"""
Streamlined message transformer — distillation-resistant output format.

Transforms SDK messages for streamlined output mode:
  - Text messages are emitted as ``streamlined_text``
  - Tool-only messages are collapsed into cumulative tool-count summaries
  - Thinking content is omitted
  - Result messages are passed through unchanged
  - All other message types are dropped

Port of streamlinedTransform.ts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Tool name constants (mirrors TS imports from tool prompt files)
# ---------------------------------------------------------------------------

FILE_EDIT_TOOL_NAME: str = "str_replace_editor"
FILE_READ_TOOL_NAME: str = "read_file"
FILE_WRITE_TOOL_NAME: str = "write_file"
GLOB_TOOL_NAME: str = "glob"
GREP_TOOL_NAME: str = "grep"
LIST_MCP_RESOURCES_TOOL_NAME: str = "list_mcp_resources"
LSP_TOOL_NAME: str = "lsp"
NOTEBOOK_EDIT_TOOL_NAME: str = "notebook_edit"
TASK_STOP_TOOL_NAME: str = "task_done"
WEB_SEARCH_TOOL_NAME: str = "web_search"
SHELL_TOOL_NAMES: list[str] = ["bash", "shell", "computer"]

# ---------------------------------------------------------------------------
# Tool categorisation
# ---------------------------------------------------------------------------

SEARCH_TOOLS: tuple[str, ...] = (
    GREP_TOOL_NAME, GLOB_TOOL_NAME, WEB_SEARCH_TOOL_NAME, LSP_TOOL_NAME,
)
READ_TOOLS: tuple[str, ...] = (FILE_READ_TOOL_NAME, LIST_MCP_RESOURCES_TOOL_NAME)
WRITE_TOOLS: tuple[str, ...] = (
    FILE_WRITE_TOOL_NAME, FILE_EDIT_TOOL_NAME, NOTEBOOK_EDIT_TOOL_NAME,
)
COMMAND_TOOLS: tuple[str, ...] = (*SHELL_TOOL_NAMES, "Tmux", TASK_STOP_TOOL_NAME)


@dataclass
class ToolCounts:
    """Cumulative counts of tool uses by category."""

    searches: int = 0
    reads: int = 0
    writes: int = 0
    commands: int = 0
    other: int = 0


def categorize_tool_name(tool_name: str) -> str:
    """Return the category key for a tool name."""
    if any(tool_name.startswith(t) for t in SEARCH_TOOLS):
        return "searches"
    if any(tool_name.startswith(t) for t in READ_TOOLS):
        return "reads"
    if any(tool_name.startswith(t) for t in WRITE_TOOLS):
        return "writes"
    if any(tool_name.startswith(t) for t in COMMAND_TOOLS):
        return "commands"
    return "other"


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _capitalize(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def get_tool_summary_text(counts: ToolCounts) -> Optional[str]:
    """Generate a human-readable summary of accumulated tool counts."""
    parts: list[str] = []
    if counts.searches:
        n = counts.searches
        parts.append(f"searched {n} {'pattern' if n == 1 else 'patterns'}")
    if counts.reads:
        n = counts.reads
        parts.append(f"read {n} {'file' if n == 1 else 'files'}")
    if counts.writes:
        n = counts.writes
        parts.append(f"wrote {n} {'file' if n == 1 else 'files'}")
    if counts.commands:
        n = counts.commands
        parts.append(f"ran {n} {'command' if n == 1 else 'commands'}")
    if counts.other:
        n = counts.other
        parts.append(f"{n} other {'tool' if n == 1 else 'tools'}")
    return _capitalize(", ".join(parts)) if parts else None


def _extract_text_content(content: list[dict[str, Any]]) -> str:
    """Concatenate text blocks from a content array."""
    return "\n".join(
        b.get("text", "")
        for b in content
        if isinstance(b, dict) and b.get("type") == "text"
    ).strip()


# ---------------------------------------------------------------------------
# Accumulator
# ---------------------------------------------------------------------------

def accumulate_tool_uses(
    message: dict[str, Any],
    counts: ToolCounts,
) -> None:
    """Add tool-use block counts from *message* into *counts* in-place."""
    content = message.get("message", {}).get("content", [])
    if not isinstance(content, list):
        return
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            name = block.get("name", "")
            if name:
                category = categorize_tool_name(name)
                current = getattr(counts, category, 0)
                setattr(counts, category, current + 1)


# ---------------------------------------------------------------------------
# Stateful transformer factory
# ---------------------------------------------------------------------------

def create_streamlined_transformer() -> Callable[
    [dict[str, Any]], Optional[dict[str, Any]]
]:
    """
    Return a stateful function that transforms SDK messages for streamlined output.

    The returned function:
      - Emits ``streamlined_text`` for assistant messages that contain text
      - Emits ``streamlined_tool_use_summary`` for tool-only assistant messages
      - Resets tool counts whenever a text message is emitted
      - Passes ``result`` messages through unchanged
      - Returns ``None`` for all other message types
    """
    cumulative: ToolCounts = ToolCounts()

    def transform(message: dict[str, Any]) -> Optional[dict[str, Any]]:
        nonlocal cumulative
        msg_type = message.get("type", "")

        if msg_type == "assistant":
            content = message.get("message", {}).get("content", [])
            text = _extract_text_content(content) if isinstance(content, list) else ""

            accumulate_tool_uses(message, cumulative)

            if text:
                cumulative = ToolCounts()  # reset on text emission
                return {
                    "type": "streamlined_text",
                    "text": text,
                    "session_id": message.get("session_id"),
                    "uuid": message.get("uuid"),
                }

            summary = get_tool_summary_text(cumulative)
            if not summary:
                return None
            return {
                "type": "streamlined_tool_use_summary",
                "tool_summary": summary,
                "session_id": message.get("session_id"),
                "uuid": message.get("uuid"),
            }

        if msg_type == "result":
            return message  # pass through as-is

        # system, user, stream_event, tool_progress, auth_status,
        # rate_limit_event, control_*, keep_alive → drop
        return None

    return transform


def streamlined_transform(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Transform a list of SDK messages to streamlined format.

    Convenience wrapper around :func:`create_streamlined_transformer` for
    one-shot batch processing.

    Args:
        messages: List of SDK message dicts.

    Returns:
        Filtered and transformed list (``None`` outputs are excluded).
    """
    transformer = create_streamlined_transformer()
    results: list[dict[str, Any]] = []
    for msg in messages:
        out = transformer(msg)
        if out is not None:
            results.append(out)
    return results


def should_include_in_streamlined(message: dict[str, Any]) -> bool:
    """Return True if *message* is a candidate for streamlined output."""
    return message.get("type") in ("assistant", "result")
