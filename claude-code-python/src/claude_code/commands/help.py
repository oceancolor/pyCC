# 原始 TS: commands/help/index.ts + help.tsx
"""Help command - show available slash commands."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CommandInfo:
    name: str
    description: str
    aliases: list[str] = field(default_factory=list)
    argument_hint: str = ""


def get_help_text(commands: list[CommandInfo] | None = None) -> str:
    """Format a human-readable list of available commands."""
    if not commands:
        # Default built-in list
        commands = _default_commands()

    lines = ["Available commands:", ""]
    for cmd in sorted(commands, key=lambda c: c.name):
        aliases = f"  (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
        hint = f" {cmd.argument_hint}" if cmd.argument_hint else ""
        lines.append(f"  /{cmd.name}{hint} — {cmd.description}{aliases}")

    lines.append("")
    lines.append("Type /help <command> for details on a specific command.")
    return "\n".join(lines)


def _default_commands() -> list[CommandInfo]:
    return [
        CommandInfo("help", "Show this help message"),
        CommandInfo("clear", "Clear conversation history"),
        CommandInfo("compact", "Compress conversation to save context", argument_hint="[instructions]"),
        CommandInfo("config", "View or edit configuration"),
        CommandInfo("cost", "Show session token usage and cost"),
        CommandInfo("doctor", "Run diagnostics"),
        CommandInfo("login", "Sign in to your Anthropic account"),
        CommandInfo("logout", "Sign out from your Anthropic account"),
        CommandInfo("resume", "Resume a previous conversation", aliases=["continue"], argument_hint="[id]"),
        CommandInfo("status", "Show current session status"),
        CommandInfo("version", "Print version information"),
        CommandInfo("bug", "Report a bug"),
    ]


async def run(args: str = "", context: Any = None) -> dict[str, Any]:
    """Entry point called by the command dispatcher."""
    text = get_help_text()
    return {"type": "text", "value": text}
