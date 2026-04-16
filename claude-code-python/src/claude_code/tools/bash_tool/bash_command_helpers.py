"""Bash command permission helpers. Ported from BashTool/bashCommandHelpers.ts"""
from __future__ import annotations
import re
from typing import Any, Dict, List, Optional, Tuple


def split_command(command: str) -> List[str]:
    """Split compound bash commands by shell operators (; && || |)."""
    parts = re.split(r'(?:;|&&|\|\||(?<!\|)\|(?!\|))', command)
    return [p.strip() for p in parts if p.strip()]


def is_cd_command(command: str) -> bool:
    stripped = command.strip()
    return stripped == 'cd' or stripped.startswith('cd ') or stripped.startswith('cd\t')


def normalize_cd_command(command: str) -> Optional[str]:
    """Extract the target path from a cd command."""
    m = re.match(r'^cd\s+(.+)$', command.strip())
    return m.group(1).strip().strip('"\'') if m else None


def create_permission_request_message(command: str, reason: str = "") -> str:
    return f"Permission required to run: {command}" + (f"\nReason: {reason}" if reason else "")


def build_allow_command(command: str) -> Dict[str, Any]:
    return {"behavior": "allow", "updatedInput": {"command": command}}


def build_ask_command(command: str, message: str = "") -> Dict[str, Any]:
    return {"behavior": "ask", "message": message or f"Allow running: {command}?"}
