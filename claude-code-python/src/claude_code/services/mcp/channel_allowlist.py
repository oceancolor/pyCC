"""
channel_allowlist.py - MCP channel-based server allowlist.

Port of TypeScript channelAllowlist.ts.
"""

import os
from typing import Any, Dict, List, Set


def get_channel_allowlist() -> Set[str]:
    """
    Get the set of allowed MCP server names for channel relay.

    Returns:
        Set of server names that are allowed to relay permissions.
    """
    env_val = os.environ.get('CLAUDE_CODE_MCP_CHANNEL_ALLOWLIST', '')
    if not env_val:
        return set()

    names = {name.strip() for name in env_val.split(',') if name.strip()}
    return names


def is_in_channel_allowlist(server_name: str) -> bool:
    """
    Check if a server name is in the channel allowlist.

    Args:
        server_name: MCP server name to check

    Returns:
        True if the server is allowed to relay permissions.
    """
    allowlist = get_channel_allowlist()

    # If allowlist is empty, no servers are allowed
    if not allowlist:
        return False

    return server_name in allowlist


def build_is_in_allowlist_fn(
    config_allowlist: List[str],
) -> Any:
    """
    Build an allowlist check function from config.

    Args:
        config_allowlist: List of server names from config

    Returns:
        Callable that checks if a server name is allowed.
    """
    from_config: Set[str] = set(config_allowlist)
    from_env: Set[str] = get_channel_allowlist()
    combined = from_config | from_env

    def is_allowed(server_name: str) -> bool:
        return server_name in combined

    return is_allowed
