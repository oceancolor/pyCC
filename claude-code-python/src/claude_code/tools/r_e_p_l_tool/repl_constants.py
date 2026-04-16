"""REPL tool constants. Ported from REPLTool/constants.ts"""
from __future__ import annotations
import os

REPL_TOOL_NAME = "REPL"

REPL_ONLY_TOOL_NAMES = frozenset([
    "Read", "Write", "Edit", "Glob", "Grep", "Bash", "NotebookEdit", "Agent"
])


def is_repl_mode_enabled() -> bool:
    val = os.environ.get("CLAUDE_CODE_REPL", "")
    if val.lower() in ("0", "false", "no"):
        return False
    if os.environ.get("CLAUDE_REPL_MODE", "").lower() in ("1", "true"):
        return True
    return (os.environ.get("USER_TYPE") == "ant" and
            os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "cli")
