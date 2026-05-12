"""
/version command.
Ported from commands/version.ts

Prints the Claude Code version this session is running.
"""
from __future__ import annotations

import importlib.metadata
import os
from typing import Any, Dict

COMMAND_NAME = "version"


def _get_version() -> str:
    try:
        return importlib.metadata.version("claude-code")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


async def call(_args: str = "", **_kwargs: Any) -> Dict[str, Any]:
    return {
        "type": "text",
        "value": _get_version(),
    }


COMMAND: Dict[str, Any] = {
    "type": "local",
    "name": COMMAND_NAME,
    "description": "Print the version this session is running (not what autoupdate downloaded)",
    "is_enabled": lambda: os.environ.get("USER_TYPE") == "ant",
    "supports_non_interactive": True,
    "load": lambda: {"call": call},
}
