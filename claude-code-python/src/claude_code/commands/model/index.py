"""Model command index. Ported from commands/model/index.ts"""
from __future__ import annotations
from claude_code.commands import Command

class ModelCommand(Command):
    type = "local"
    name = "model"
    argument_hint = "[model]"
    source = "builtin"

    @property
    def description(self):
        try:
            from claude_code.utils.model.model import get_main_loop_model
            return f"Set the AI model (currently {get_main_loop_model()})"
        except Exception:
            return "Set the AI model"

    async def call(self, args: str, context=None) -> dict:
        arg = args.strip()
        if not arg:
            from claude_code.utils.model.model import get_main_loop_model
            return {"type": "text", "value": f"Current model: {get_main_loop_model()}"}
        from claude_code.utils.model.validate_model import validate_model
        result = await validate_model(arg)
        if not result.get("valid"):
            return {"type": "text", "value": f"Invalid model: {result.get('error')}"}
        return {"type": "text", "value": f"Model set to: {arg}"}

model_cmd = ModelCommand()
