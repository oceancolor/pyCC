"""Clear command implementation. Ported from commands/clear/clear.ts"""
from __future__ import annotations
from typing import Any

async def call(args: str, context: Any = None) -> dict:
    from claude_code.commands.clear.conversation import clear_conversation
    await clear_conversation(context)
    return {"type": "text", "value": ""}
