"""Command descriptor for /install-slack-app. Ported from commands/install_slack_app/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "install-slack-app"
DESCRIPTION = "Install the Claude Slack app"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
SUPPORTS_NON_INTERACTIVE: bool = False
AVAILABILITY: List[str] = ['claude-ai']


@dataclass
class InstallSlackAppCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    availability: List[str] = field(default_factory=lambda: ['claude-ai'])

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /install-slack-app command."""
        return {"type": "text", "value": f"/install-slack-app not yet implemented"}


default = InstallSlackAppCommand()
