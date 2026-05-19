"""Services package.

Top-level re-exports for the most commonly used service functions.

Ported from: src/services/ (TypeScript)

Sub-packages
------------
agent_summary
    Generates compressed summaries of agent conversations.
compact
    Context-window compaction and auto-compact threshold management.
extract_memories
    Extracts long-term memories from conversation transcripts.
lsp
    Language Server Protocol (LSP) client and passive diagnostics.
magic_docs
    Fetches and processes MCP magic documentation pages.
remote_managed_settings
    Loads operator-controlled settings from a remote URL.
settings_sync
    Synchronises local settings with a remote settings store.
tips
    Tip-of-the-day registry and scheduler.
tool_use_summary
    Generates concise summaries of tool-use activity.
tools_service
    Core tool orchestration, streaming executor, and hooks.
"""
from __future__ import annotations

from claude_code.services.api import get_anthropic_client, get_api_provider
from claude_code.services.token_estimation import (
    estimate_tokens_from_string,
    estimate_tokens_from_content,
    estimate_messages_tokens,
)

__all__ = [
    "get_anthropic_client",
    "get_api_provider",
    "estimate_tokens_from_string",
    "estimate_tokens_from_content",
    "estimate_messages_tokens",
]
