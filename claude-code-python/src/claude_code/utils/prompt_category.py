"""
Query source / prompt category helpers. Ported from promptCategory.ts
"""
from __future__ import annotations
from typing import Optional


def get_query_source_for_agent(agent_type: Optional[str], is_built_in: bool) -> str:
    if is_built_in:
        return f"agent:builtin:{agent_type}" if agent_type else "agent:default"
    return "agent:custom"


def get_query_source_for_repl(output_style: Optional[str] = None) -> str:
    default_style = "default"
    style = output_style or default_style
    if style == default_style:
        return "repl_main_thread"
    return f"repl_main_thread:outputStyle:{style}"
