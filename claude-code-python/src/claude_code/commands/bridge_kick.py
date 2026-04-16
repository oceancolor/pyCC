"""
/bridge-kick command (ANT-only debug). Ported from commands/bridge-kick.ts
"""
from __future__ import annotations
import os
from claude_code.commands import Command


class BridgeKickCommand(Command):
    type = "local"
    name = "bridge-kick"
    description = "ANT-only: inject bridge failure states for testing"
    source = "builtin"

    def is_enabled(self) -> bool:
        return os.environ.get("USER_TYPE") == "ant"

    async def call(self, args: str, context=None) -> dict:
        parts = args.strip().split()
        if not parts:
            return {"type": "text", "value": "Usage: /bridge-kick <subcommand>"}
        return {"type": "text", "value": f"bridge-kick: {' '.join(parts)} (stub — bridge not implemented)"}


bridge_kick = BridgeKickCommand()
