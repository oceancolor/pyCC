# 原始 TS: commands/version.ts
"""Version command - print the current Claude Code version."""
from __future__ import annotations

import importlib.metadata
from typing import Any


def get_version() -> str:
    """Return the installed package version, or a fallback string."""
    try:
        return importlib.metadata.version("claude-code")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0-dev"


async def run(args: str = "", context: Any = None) -> dict[str, Any]:
    """Entry point called by the command dispatcher."""
    return {"type": "text", "value": get_version()}
