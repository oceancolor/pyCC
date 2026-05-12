"""
prefix.py - Command prefix utilities for bash commands.

Port of TypeScript prefix.ts.
"""

import re
from typing import List, Optional, Dict, Any


NUMERIC = re.compile(r'^\d+$')
ENV_VAR = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')

# Wrapper commands with complex option handling
WRAPPER_COMMANDS = {'nice'}


def _to_array(val):
    """Convert single value or list to list."""
    if isinstance(val, list):
        return val
    return [val]


def _is_known_subcommand(arg: str, spec: Optional[Dict]) -> bool:
    """Check if args[0] matches a known subcommand."""
    if not spec or not spec.get('subcommands'):
        return False
    for sub in spec['subcommands']:
        name = sub.get('name', '')
        if isinstance(name, list):
            if arg in name:
                return True
        else:
            if name == arg:
                return True
    return False


async def get_command_prefix_static(
    command: str,
    recursion_depth: int = 0,
    wrapper_count: int = 0,
) -> Optional[Dict[str, Optional[str]]]:
    """
    Get the static command prefix for a given command.
    Returns dict with 'commandPrefix' key, or None.
    """
    if wrapper_count > 2 or recursion_depth > 10:
        return None

    from .parser import parse_command, extract_command_arguments, find_command_node
    from .registry import get_command_spec
    from ..shell.spec_prefix import build_prefix

    parsed = await parse_command(command)
    if not parsed:
        return None

    if not parsed.get('command_node'):
        return {'commandPrefix': None}

    env_vars = parsed.get('env_vars', [])
    command_node = parsed['command_node']
    cmd_args = extract_command_arguments(command_node)

    if not cmd_args:
        return {'commandPrefix': None}

    cmd = cmd_args[0]
    args = cmd_args[1:]

    spec = await get_command_spec(cmd)

    is_wrapper = (
        cmd in WRAPPER_COMMANDS
        or (spec and spec.get('args') and any(
            arg.get('isCommand') for arg in _to_array(spec.get('args', []))
            if arg
        ))
    )

    if is_wrapper and args and _is_known_subcommand(args[0], spec):
        is_wrapper = False

    if is_wrapper:
        prefix = await _handle_wrapper(cmd, args, recursion_depth, wrapper_count)
    else:
        prefix = await build_prefix(cmd, args, spec)

    if prefix is None and recursion_depth == 0 and is_wrapper:
        return None

    env_prefix = f"{' '.join(env_vars)} " if env_vars else ''
    return {'commandPrefix': env_prefix + prefix if prefix else None}


async def _handle_wrapper(
    command: str,
    args: List[str],
    recursion_depth: int,
    wrapper_count: int,
) -> Optional[str]:
    """Handle wrapper commands like sudo, timeout, nice."""
    from .registry import get_command_spec

    spec = await get_command_spec(command)

    if spec and spec.get('args'):
        spec_args = _to_array(spec['args'])
        command_arg_index = next(
            (i for i, a in enumerate(spec_args) if a and a.get('isCommand')),
            -1
        )

        if command_arg_index != -1:
            parts = [command]

            for i, arg in enumerate(args):
                if i > command_arg_index:
                    break
                if i == command_arg_index:
                    result = await get_command_prefix_static(
                        ' '.join(args[i:]),
                        recursion_depth + 1,
                        wrapper_count + 1,
                    )
                    if result and result.get('commandPrefix'):
                        parts.extend(result['commandPrefix'].split(' '))
                        return ' '.join(parts)
                    break
                elif arg and not arg.startswith('-') and not ENV_VAR.match(arg):
                    parts.append(arg)

    wrapped = next(
        (a for a in args if not a.startswith('-') and not NUMERIC.match(a) and not ENV_VAR.match(a)),
        None
    )
    if not wrapped:
        return command

    result = await get_command_prefix_static(
        ' '.join(args[args.index(wrapped):]),
        recursion_depth + 1,
        wrapper_count + 1,
    )

    if not result or not result.get('commandPrefix'):
        return None
    return f"{command} {result['commandPrefix']}"


async def get_compound_command_prefixes_static(
    command: str,
    exclude_subcommand=None,
) -> List[str]:
    """
    Computes prefixes for a compound command (with && / || / ;).
    """
    from .parser import split_command_with_operators

    subcommands = _split_command_deprecated(command)
    if len(subcommands) <= 1:
        result = await get_command_prefix_static(command)
        if result and result.get('commandPrefix'):
            return [result['commandPrefix']]
        return []

    prefixes: List[str] = []
    for subcmd in subcommands:
        trimmed = subcmd.strip()
        if exclude_subcommand and exclude_subcommand(trimmed):
            continue
        result = await get_command_prefix_static(trimmed)
        if result and result.get('commandPrefix'):
            prefixes.append(result['commandPrefix'])

    if not prefixes:
        return []

    # Group by root command
    groups: Dict[str, List[str]] = {}
    for prefix in prefixes:
        root = prefix.split(' ')[0]
        if root not in groups:
            groups[root] = []
        groups[root].append(prefix)

    collapsed = []
    for group in groups.values():
        collapsed.append(_longest_common_prefix(group))
    return collapsed


def _split_command_deprecated(command: str) -> List[str]:
    """Split command by && / || / ; operators."""
    # Simple split on compound operators
    parts = re.split(r'(?:&&|\|\||;)', command)
    return [p for p in parts if p.strip()]


def _longest_common_prefix(strings: List[str]) -> str:
    """Compute the longest common prefix aligned to word boundaries."""
    if not strings:
        return ''
    if len(strings) == 1:
        return strings[0]

    first = strings[0]
    words = first.split(' ')
    common_words = len(words)

    for s in strings[1:]:
        other_words = s.split(' ')
        shared = 0
        while shared < common_words and shared < len(other_words) and words[shared] == other_words[shared]:
            shared += 1
        common_words = shared

    return ' '.join(words[:max(1, common_words)])
