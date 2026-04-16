"""Command exit-code semantics. Ported from BashTool/commandSemantics.ts"""
from __future__ import annotations
from typing import Callable, Dict, Optional, Tuple


CommandSemantic = Callable[[int, str, str], Tuple[bool, Optional[str]]]


def _default(exit_code: int, _out: str, _err: str) -> Tuple[bool, Optional[str]]:
    if exit_code != 0:
        return True, f"Command failed with exit code {exit_code}"
    return False, None


def _grep_semantic(exit_code: int, _out: str, _err: str) -> Tuple[bool, Optional[str]]:
    if exit_code >= 2:
        return True, None
    if exit_code == 1:
        return False, "No matches found"
    return False, None


def _find_semantic(exit_code: int, _out: str, _err: str) -> Tuple[bool, Optional[str]]:
    if exit_code >= 2:
        return True, None
    if exit_code == 1:
        return False, "Some directories were inaccessible"
    return False, None


COMMAND_SEMANTICS: Dict[str, CommandSemantic] = {
    "grep": _grep_semantic,
    "rg": _grep_semantic,
    "find": _find_semantic,
    "diff": lambda c, o, e: (c >= 2, "diff error" if c >= 2 else None),
    "test": lambda c, o, e: (False, None),
    "[": lambda c, o, e: (False, None),
}


def get_command_semantic(base_cmd: str) -> CommandSemantic:
    return COMMAND_SEMANTICS.get(base_cmd, _default)


def interpret_exit_code(command: str, exit_code: int, stdout: str, stderr: str) -> Tuple[bool, Optional[str]]:
    """Return (is_error, message) using command-specific semantics."""
    base = command.strip().split()[0] if command.strip() else ""
    semantic = get_command_semantic(base)
    return semantic(exit_code, stdout, stderr)
