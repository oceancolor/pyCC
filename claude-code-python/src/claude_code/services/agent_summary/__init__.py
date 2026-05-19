"""Agent summary service.

Generates a compact, human-readable summary of an agent sub-session
conversation.  The summary is injected into the parent session as a
tool result when the sub-agent finishes, replacing the full transcript
to save context-window tokens.

This is especially important in deep sub-agent trees where replaying the
full conversation history of every sub-agent would exceed the context limit
of the parent.

Ported from: src/services/agentSummary/ (TypeScript)

Usage::

    from claude_code.services.agent_summary import generate_agent_summary

    summary = await generate_agent_summary(messages, model)
"""
from __future__ import annotations

from claude_code.services.agent_summary.agent_summary import generate_agent_summary

__all__ = ["generate_agent_summary"]
