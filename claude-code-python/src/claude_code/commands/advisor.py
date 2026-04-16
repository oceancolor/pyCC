"""
/advisor command. Ported from commands/advisor.ts
"""
from __future__ import annotations
from claude_code.commands import Command


class AdvisorCommand(Command):
    type = "local"
    name = "advisor"
    description = "Enable/disable/configure the advisor model"
    source = "builtin"

    async def call(self, args: str, context=None) -> dict:
        arg = args.strip().lower()
        if not arg:
            current = (context.get_app_state().get("advisor_model") if context else None)
            if not current:
                return {"type": "text", "value": "Advisor: not set\nUse '/advisor <model>' to enable."}
            return {"type": "text", "value": f"Advisor: {current}\nUse '/advisor unset' to disable."}
        if arg in ("unset", "off"):
            return {"type": "text", "value": "Advisor disabled."}
        return {"type": "text", "value": f"Advisor set to: {arg}"}


advisor = AdvisorCommand()
