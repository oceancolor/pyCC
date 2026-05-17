"""
CLI package — headless / non-interactive output.

Original TypeScript: src/cli/

The TypeScript source uses React/Ink for the interactive REPL UI and a
separate headless path (cli/print.ts) for `-p`/`--print` mode.

This Python package re-exports the headless print utilities and provides
stub entry-points for the interactive REPL (which will be implemented with
prompt_toolkit or textual in a later milestone).
"""
from __future__ import annotations

from .print import (
    run_headless,
    DynamicMcpState,
    SdkMcpState,
    McpSetServersResult,
)

__all__ = [
    "run_headless",
    "DynamicMcpState",
    "SdkMcpState",
    "McpSetServersResult",
]
