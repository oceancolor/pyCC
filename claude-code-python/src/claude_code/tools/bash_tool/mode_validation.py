"""Permission mode validation for bash commands. Ported from BashTool/modeValidation.ts"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

ACCEPT_EDITS_ALLOWED_COMMANDS = frozenset(["mkdir", "touch", "rm", "rmdir", "mv", "cp", "sed"])


def _get_base_cmd(cmd: str) -> str:
    return cmd.strip().split()[0] if cmd.strip() else ""


def check_permission_mode(command: str, mode: str) -> Dict[str, Any]:
    """
    Returns a PermissionResult dict:
      { behavior: 'allow' | 'ask' | 'passthrough', message: str, ... }
    """
    if mode in ("bypassPermissions", "dontAsk"):
        return {"behavior": "passthrough", "message": f"{mode} handled elsewhere"}

    base = _get_base_cmd(command)
    if mode == "acceptEdits" and base in ACCEPT_EDITS_ALLOWED_COMMANDS:
        return {"behavior": "allow", "updatedInput": {"command": command},
                "decisionReason": {"type": "mode", "mode": "acceptEdits"}}

    return {"behavior": "passthrough", "message": f"No mode-specific handling for '{base}' in {mode} mode"}


def get_auto_allowed_commands(mode: str) -> List[str]:
    return list(ACCEPT_EDITS_ALLOWED_COMMANDS) if mode == "acceptEdits" else []
