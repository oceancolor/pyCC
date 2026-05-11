"""REPL tool constants. Ported from REPLTool/constants.ts"""
from __future__ import annotations
import os

REPL_TOOL_NAME = "REPL"

# Tools hidden from direct model use when REPL mode is enabled.
# The model must use REPL to batch-invoke these instead.
REPL_ONLY_TOOLS: frozenset = frozenset([
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
    "NotebookEdit",
    "Agent",
])


def is_repl_mode_enabled() -> bool:
    """Return True when REPL mode should be active.

    Rules (matching constants.ts exactly):
    - CLAUDE_CODE_REPL=0/false/no  → always off
    - CLAUDE_REPL_MODE=1/true      → always on
    - USER_TYPE=ant + ENTRYPOINT=cli → on by default
    - SDK entry-points              → off by default
    """
    repl_env = os.environ.get("CLAUDE_CODE_REPL", "")
    if repl_env.lower() in ("0", "false", "no"):
        return False
    if os.environ.get("CLAUDE_REPL_MODE", "").lower() in ("1", "true", "yes"):
        return True
    return (
        os.environ.get("USER_TYPE") == "ant"
        and os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "cli"
    )
