"""Prompt / query source category helpers. Ported from utils/promptCategory.ts"""
from __future__ import annotations
from typing import Optional

# QuerySource is a string literal type in TS — we alias it to str here.
QuerySource = str


def get_query_source_for_agent(
    agent_type: Optional[str],
    is_built_in_agent: bool,
) -> QuerySource:
    """Return the analytics query-source string for an agent invocation.

    Args:
        agent_type: The type/name of the agent, or None for the default agent.
        is_built_in_agent: True if the agent is a built-in rather than custom.

    Returns:
        A ``QuerySource`` string such as ``"agent:builtin:code-reviewer"`` or
        ``"agent:custom"``.
    """
    if is_built_in_agent:
        return f"agent:builtin:{agent_type}" if agent_type else "agent:default"
    return "agent:custom"


def get_query_source_for_repl() -> QuerySource:
    """Return the analytics query-source string for a REPL main-thread query.

    Inspects the output-style setting (when available) and returns a
    ``repl_main_thread[:outputStyle:<style>]`` string.
    """
    try:
        from claude_code.utils.settings.settings import get_settings_deprecated  # type: ignore[import]
        settings = get_settings_deprecated()
        style: Optional[str] = (settings or {}).get("outputStyle")
    except Exception:
        style = None

    default_style = "default"
    if not style or style == default_style:
        return "repl_main_thread"

    # Determine whether this is a known built-in style.
    try:
        from claude_code.constants.output_styles import OUTPUT_STYLE_CONFIG  # type: ignore[import]
        is_built_in = style in OUTPUT_STYLE_CONFIG
    except ImportError:
        is_built_in = False

    if is_built_in:
        return f"repl_main_thread:outputStyle:{style}"
    return "repl_main_thread:outputStyle:custom"
