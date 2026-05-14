"""Command descriptor for /perf-issue. Ported from commands/perf_issue/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "perf-issue"
DESCRIPTION = "Report a performance issue (ANT-only)"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = True  # ANT-internal or advanced command


@dataclass
class PerfIssueCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    is_hidden: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /perf-issue command."""
        return {"type": "local-command", "name": "perf-issue", "args": args}


default = PerfIssueCommand()
