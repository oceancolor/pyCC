"""Command descriptor for /install-github-app. Ported from commands/install_github_app/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "install-github-app"
DESCRIPTION = "Set up Claude GitHub Actions for a repository"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
AVAILABILITY: List[str] = ['claude-ai', 'console']


@dataclass
class InstallGithubAppCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    availability: List[str] = field(default_factory=lambda: ['claude-ai', 'console'])

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /install-github-app command.

        Install Claude GitHub Actions for a repository.
        """
        return {"type": "local-command", "name": "install-github-app", "args": args}


default = InstallGithubAppCommand()
