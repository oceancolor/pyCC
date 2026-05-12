"""
env_expansion.py - Environment variable expansion for MCP server configurations.

Port of TypeScript envExpansion.ts.
"""

import os
import re
from typing import Any, Dict, List, Optional, Union


# Pattern for ${VAR} or $VAR style environment variables
_ENV_VAR_PATTERN = re.compile(r'\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)')


def expand_env_vars(value: str) -> str:
    """
    Expand environment variables in a string.

    Supports ${VAR_NAME} and $VAR_NAME syntax.
    Unset variables are replaced with empty string.

    Args:
        value: String potentially containing env var references

    Returns:
        String with env vars expanded.
    """
    def replace_match(m: re.Match) -> str:
        var_name = m.group(1) or m.group(2)
        return os.environ.get(var_name, '')

    return _ENV_VAR_PATTERN.sub(replace_match, value)


def expand_env_vars_in_config(
    config: Dict[str, Any],
    keys_to_expand: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Expand environment variables in an MCP server config dict.

    Args:
        config: Server config dict
        keys_to_expand: Keys to expand (defaults to 'command', 'args', 'env')

    Returns:
        New config dict with env vars expanded.
    """
    if keys_to_expand is None:
        keys_to_expand = ['command', 'args', 'env']

    result = dict(config)

    if 'command' in keys_to_expand and isinstance(result.get('command'), str):
        result['command'] = expand_env_vars(result['command'])

    if 'args' in keys_to_expand and isinstance(result.get('args'), list):
        result['args'] = [
            expand_env_vars(arg) if isinstance(arg, str) else arg
            for arg in result['args']
        ]

    if 'env' in keys_to_expand and isinstance(result.get('env'), dict):
        result['env'] = {
            k: expand_env_vars(v) if isinstance(v, str) else v
            for k, v in result['env'].items()
        }

    return result


def expand_mcp_server_configs(
    servers: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    Expand environment variables in all MCP server configurations.

    Args:
        servers: Dict mapping server names to server config dicts

    Returns:
        New dict with env vars expanded in all configs.
    """
    return {
        name: expand_env_vars_in_config(config)
        for name, config in servers.items()
    }
