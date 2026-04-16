"""Factory for plugin-redirect commands. Ported from commands/createMovedToPluginCommand.ts"""
from __future__ import annotations
import os
from claude_code.commands import Command


def create_moved_to_plugin_command(name: str, description: str, progress_message: str,
                                    plugin_name: str, plugin_command: str,
                                    get_prompt_while_marketplace_private=None) -> Command:
    class _MovedCommand(Command):
        pass

    _MovedCommand.type = "prompt"
    _MovedCommand.name = name
    _MovedCommand.description = description
    _MovedCommand.progress_message = progress_message
    _MovedCommand.source = "builtin"

    async def get_prompt(self_inner, args: str, context=None) -> list:
        if os.environ.get("USER_TYPE") == "ant":
            return [{"type": "text", "text":
                     f"This command has been moved to a plugin.\n"
                     f"Install: claude plugin install {plugin_name}@claude-code-marketplace\n"
                     f"Then use: /{plugin_name}:{plugin_command}"}]
        if get_prompt_while_marketplace_private:
            return await get_prompt_while_marketplace_private(args, context)
        return [{"type": "text", "text": f"/{name} is not available yet."}]

    _MovedCommand.get_prompt_for_command = get_prompt  # type: ignore
    return _MovedCommand()
