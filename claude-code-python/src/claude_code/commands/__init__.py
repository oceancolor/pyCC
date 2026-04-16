"""
Commands package
原始 TS: src/commands/

Slash commands available in the REPL.
Each command is lazy-loaded in TS; here we eagerly register them
since Python startup overhead is acceptable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from claude_code.types.command import CommandBase, LocalCommand, LocalCommandResult


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

_COMMAND_REGISTRY: dict[str, CommandBase] = {}


def register(cmd: CommandBase) -> None:
    _COMMAND_REGISTRY[cmd.name] = cmd


def get_all_commands() -> list[CommandBase]:
    return list(_COMMAND_REGISTRY.values())


def get_command(name: str) -> Optional[CommandBase]:
    return _COMMAND_REGISTRY.get(name)


# ---------------------------------------------------------------------------
# Built-in commands (stubs)
# ---------------------------------------------------------------------------

@dataclass
class StubCommand(CommandBase):
    """Stub command for unimplemented commands."""
    action: Optional[Callable[..., Any]] = None

    async def execute(self, args: str = "", context: Any = None) -> str:
        if self.action:
            return await self.action(args, context)
        return f"Command /{self.name} not yet implemented in Python port"


def _make_stub(name: str, description: str, aliases: Optional[list[str]] = None) -> StubCommand:
    cmd = StubCommand()
    cmd.name = name
    cmd.description = description
    cmd.aliases = aliases or []
    return cmd


# Register all built-in slash commands
_BUILTIN_COMMANDS = [
    _make_stub("clear", "Clear conversation history and free up context", ["reset", "new"]),
    _make_stub("compact", "Clear conversation history but keep a summary in context"),
    _make_stub("help", "Show help and available commands", ["?"]),
    _make_stub("model", "Switch the AI model"),
    _make_stub("exit", "Exit Claude Code", ["quit", "q"]),
    _make_stub("version", "Show version information"),
    _make_stub("status", "Show current session status"),
    _make_stub("cost", "Show token usage and cost"),
    _make_stub("config", "Open or modify configuration"),
    _make_stub("doctor", "Check system health"),
    _make_stub("bug", "File a bug report"),
    _make_stub("review", "Request a code review"),
    _make_stub("commit", "Create a git commit"),
    _make_stub("diff", "Show git diff"),
    _make_stub("plan", "Enter planning mode"),
    _make_stub("permissions", "View and modify tool permissions"),
    _make_stub("memory", "Show or edit memory"),
    _make_stub("resume", "Resume a previous session"),
    _make_stub("share", "Share the current session"),
    _make_stub("stats", "Show usage statistics"),
    _make_stub("vim", "Enter vim mode"),
    _make_stub("voice", "Start voice mode"),
    _make_stub("theme", "Change color theme"),
    _make_stub("upgrade", "Upgrade Claude Code"),
]

for _cmd in _BUILTIN_COMMANDS:
    register(_cmd)
