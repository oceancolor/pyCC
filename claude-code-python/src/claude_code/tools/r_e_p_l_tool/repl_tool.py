"""REPL tool primitive tools list. Ported from REPLTool/primitiveTools.ts"""
from __future__ import annotations
from typing import Any, List, Optional

# Lazy-initialised list of primitive tool instances.
# In the TypeScript original these are singleton tool objects; here we store
# the tool *names* and resolve actual instances at call-time to avoid circular
# import issues (same reason TS uses a lazy getter).
_primitive_tool_names = [
    "FileRead",
    "FileWrite",
    "FileEdit",
    "Glob",
    "Grep",
    "Bash",
    "NotebookEdit",
    "Agent",
]

_primitive_tools: Optional[List[Any]] = None


def get_repl_primitive_tools() -> List[Any]:
    """Return the list of primitive tools available inside the REPL VM context.

    These tools are hidden from direct model use when REPL mode is enabled
    (they appear in REPL_ONLY_TOOLS) but are still accessible inside the REPL
    sandbox. Lazy to avoid circular init (same pattern as the TS original).
    """
    global _primitive_tools
    if _primitive_tools is not None:
        return _primitive_tools

    # Deferred import to break potential circular dependency chains.
    try:
        from claude_code.tools import get_tool_by_name, get_all_tools  # type: ignore[import]

        all_tools = get_all_tools()
        _primitive_tools = [
            t for t in all_tools if getattr(t, "name", None) in _primitive_tool_names
        ]
    except Exception:
        # Fallback: return an empty list rather than crash during import.
        _primitive_tools = []

    return _primitive_tools


def get_repl_primitive_tool_names() -> List[str]:
    """Return the names of primitive tools (no circular-import risk)."""
    return list(_primitive_tool_names)
