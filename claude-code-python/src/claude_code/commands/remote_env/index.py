"""Command descriptor for /remote-env. Ported from commands/remote_env/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "remote-env"
DESCRIPTION = "Configure the default remote environment for teleport sessions"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False


@dataclass
class RemoteEnvCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /remote-env command.

        Manage remote environment settings.
        """
        return {"type": "local-command", "name": "remote-env", "args": args}


default = RemoteEnvCommand()
