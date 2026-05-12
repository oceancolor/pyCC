"""
spec_prefix.py - Build command prefix from fig spec.

Port of TypeScript specPrefix.ts.
"""

from typing import Any, Dict, List, Optional


async def build_prefix(
    command: str,
    args: List[str],
    spec: Optional[Dict[str, Any]],
) -> Optional[str]:
    """
    Build a command prefix string from a fig spec.

    Args:
        command: The base command name
        args: Command arguments
        spec: The fig-format command spec

    Returns:
        The command prefix string, or None if we can't determine it.
    """
    if not command:
        return None

    if not spec:
        return command

    # No subcommands in spec
    if not spec.get('subcommands'):
        return command

    if not args:
        return command

    first_arg = args[0]

    # Try to match the first argument as a subcommand
    subcommand = _find_subcommand(spec, first_arg)
    if subcommand:
        if subcommand.get('subcommands') and len(args) > 1:
            nested = _find_subcommand(subcommand, args[1])
            if nested:
                return f"{command} {first_arg} {args[1]}"

        return f"{command} {first_arg}"

    return command


def _find_subcommand(
    spec: Dict[str, Any],
    name: str,
) -> Optional[Dict[str, Any]]:
    """Find a subcommand by name (including aliases)."""
    subcommands = spec.get('subcommands', []) or []
    for sub in subcommands:
        sub_name = sub.get('name', '')
        if isinstance(sub_name, list):
            if name in sub_name:
                return sub
        else:
            if sub_name == name:
                return sub
    return None
