"""
MCP Instructions Delta

Computes the diff between currently-connected MCP servers (that carry
instructions) and what has already been announced in the conversation.

Python port of mcpInstructionsDelta.ts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, List, Optional

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class McpInstructionsDelta:
    """Represents incremental changes to MCP server instructions."""

    # Server names added since last announcement
    added_names: List[str] = field(default_factory=list)
    # Rendered "## {name}\n{instructions}" blocks for added_names
    added_blocks: List[str] = field(default_factory=list)
    # Server names removed since last announcement
    removed_names: List[str] = field(default_factory=list)


@dataclass
class ClientSideInstruction:
    """Client-authored instruction block for a specific MCP server."""

    server_name: str
    block: str


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------


def _is_env_truthy(val: Optional[str]) -> bool:
    return val is not None and val.lower() in {"1", "true", "yes", "on"}


def _is_env_defined_falsy(val: Optional[str]) -> bool:
    return val is not None and val.lower() in {"0", "false", "no", "off", ""}


def _get_feature_value(key: str, default: bool) -> bool:  # noqa: ARG001
    """Stub for GrowthBook feature-flag lookup."""
    return default


def _log_event(event: str, payload: dict) -> None:  # noqa: ARG001
    """Stub for analytics event logging."""


def is_mcp_instructions_delta_enabled() -> bool:
    """Return True when MCP instructions should be delivered via delta attachments.

    Priority:
      1. CLAUDE_CODE_MCP_INSTR_DELTA env var (true/false)
      2. USER_TYPE == 'ant' → always on
      3. GrowthBook gate 'tengu_basalt_3kr'
    """
    env = os.environ.get("CLAUDE_CODE_MCP_INSTR_DELTA")
    if _is_env_truthy(env):
        return True
    if _is_env_defined_falsy(env):
        return False
    return os.environ.get("USER_TYPE") == "ant" or _get_feature_value(
        "tengu_basalt_3kr", False
    )


# ---------------------------------------------------------------------------
# Delta computation
# ---------------------------------------------------------------------------


def get_mcp_instructions_delta(
    mcp_clients: List[Any],
    messages: List[Any],
    client_side_instructions: List[ClientSideInstruction],
) -> Optional[McpInstructionsDelta]:
    """Diff connected MCP servers against what's announced in *messages*.

    Args:
        mcp_clients: List of MCPServerConnection objects.  A "connected"
            server is one whose ``type`` attribute equals ``"connected"``.
        messages: Conversation message list.  Attachment messages of type
            ``"attachment"`` with ``attachment.type == "mcp_instructions_delta"``
            are scanned to reconstruct the currently-announced set.
        client_side_instructions: Extra client-authored blocks to attach.

    Returns:
        McpInstructionsDelta if anything changed, None otherwise.
    """
    # Reconstruct the announced set from the message history
    announced: set[str] = set()
    attachment_count = 0
    mid_count = 0

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get("type") != "attachment":
            continue
        attachment_count += 1
        attachment = msg.get("attachment", {})
        if attachment.get("type") != "mcp_instructions_delta":
            continue
        mid_count += 1
        for name in attachment.get("addedNames", []):
            announced.add(name)
        for name in attachment.get("removedNames", []):
            announced.discard(name)

    # Collect connected servers
    connected = [c for c in mcp_clients if getattr(c, "type", None) == "connected"]
    connected_names: set[str] = {getattr(c, "name", "") for c in connected}

    # Build instruction blocks (server-authored + client-side)
    blocks: dict[str, str] = {}
    for c in connected:
        name = getattr(c, "name", "")
        instructions = getattr(c, "instructions", None)
        if instructions:
            blocks[name] = f"## {name}\n{instructions}"

    for ci in client_side_instructions:
        if ci.server_name not in connected_names:
            continue
        existing = blocks.get(ci.server_name)
        if existing:
            blocks[ci.server_name] = f"{existing}\n\n{ci.block}"
        else:
            blocks[ci.server_name] = f"## {ci.server_name}\n{ci.block}"

    # Compute added (has instructions but not yet announced)
    added: list[tuple[str, str]] = [
        (name, block) for name, block in blocks.items() if name not in announced
    ]

    # Compute removed (announced but no longer connected)
    removed: list[str] = [n for n in announced if n not in connected_names]

    if not added and not removed:
        return None

    _log_event(
        "tengu_mcp_instructions_pool_change",
        {
            "addedCount": len(added),
            "removedCount": len(removed),
            "priorAnnouncedCount": len(announced),
            "clientSideCount": len(client_side_instructions),
            "messagesLength": len(messages),
            "attachmentCount": attachment_count,
            "midCount": mid_count,
        },
    )

    added.sort(key=lambda x: x[0])
    return McpInstructionsDelta(
        added_names=[a[0] for a in added],
        added_blocks=[a[1] for a in added],
        removed_names=sorted(removed),
    )


# ---------------------------------------------------------------------------
# Apply-delta helper (for reconstructing full instruction set from history)
# ---------------------------------------------------------------------------


def apply_delta(base: set[str], delta: McpInstructionsDelta) -> set[str]:
    """Return a new set of announced server names after applying *delta*.

    Args:
        base: Currently-announced server names.
        delta: Delta to apply.

    Returns:
        Updated set of announced names.
    """
    result = set(base)
    result.update(delta.added_names)
    result -= set(delta.removed_names)
    return result
