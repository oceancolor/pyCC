"""
registry.py - Command spec registry for bash completion.

Port of TypeScript registry.ts.
"""

from typing import Any, Dict, List, Optional, Union
from functools import lru_cache


CommandSpec = Dict[str, Any]
Argument = Dict[str, Any]
Option = Dict[str, Any]


async def load_fig_spec(command: str) -> Optional[CommandSpec]:
    """Attempt to load a fig spec for the given command."""
    if not command or '/' in command or '\\' in command:
        return None
    if '..' in command:
        return None
    if command.startswith('-') and command != '-':
        return None
    # Python: no @withfig/autocomplete equivalent; return None
    return None


# Simple in-memory cache for command specs
_spec_cache: Dict[str, Optional[CommandSpec]] = {}

# Built-in specs (minimal set)
_BUILTIN_SPECS: List[CommandSpec] = [
    {
        'name': 'git',
        'description': 'Git version control',
        'subcommands': [
            {'name': 'add'},
            {'name': 'commit'},
            {'name': 'push'},
            {'name': 'pull'},
            {'name': 'fetch'},
            {'name': 'checkout'},
            {'name': 'branch'},
            {'name': 'status'},
            {'name': 'log'},
            {'name': 'diff'},
            {'name': 'merge'},
            {'name': 'rebase'},
            {'name': 'clone'},
            {'name': 'init'},
            {'name': 'remote'},
            {'name': 'worktree'},
        ],
    },
    {
        'name': 'npm',
        'description': 'Node package manager',
        'subcommands': [
            {'name': 'install'},
            {'name': 'run'},
            {'name': 'test'},
            {'name': 'build'},
        ],
    },
    {
        'name': 'sudo',
        'description': 'Execute as superuser',
        'args': [{'name': 'command', 'isCommand': True}],
    },
    {
        'name': 'timeout',
        'description': 'Run with time limit',
        'args': [{'name': 'duration'}, {'name': 'command', 'isCommand': True}],
    },
    {
        'name': 'nice',
        'description': 'Run with modified scheduling priority',
        'args': [{'name': 'command', 'isCommand': True}],
    },
    {
        'name': 'env',
        'description': 'Set environment and execute command',
        'args': [{'name': 'command', 'isCommand': True}],
    },
]


async def get_command_spec(command: str) -> Optional[CommandSpec]:
    """Get the command spec for a given command."""
    if command in _spec_cache:
        return _spec_cache[command]

    # Check builtin specs
    spec = next((s for s in _BUILTIN_SPECS if s.get('name') == command), None)

    if spec is None:
        spec = await load_fig_spec(command)

    _spec_cache[command] = spec
    return spec
