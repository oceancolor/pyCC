"""
official_registry.py - Official MCP server registry.

Port of TypeScript officialRegistry.ts.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

OFFICIAL_REGISTRY_URL = 'https://registry.smithery.ai'
OFFICIAL_REGISTRY_TIMEOUT = 5.0

# Well-known official MCP servers
OFFICIAL_SERVERS: Dict[str, Dict[str, Any]] = {
    'filesystem': {
        'name': 'filesystem',
        'description': 'MCP server for file system operations',
        'qualifiedName': '@modelcontextprotocol/server-filesystem',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-filesystem'],
    },
    'github': {
        'name': 'github',
        'description': 'MCP server for GitHub operations',
        'qualifiedName': '@modelcontextprotocol/server-github',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-github'],
    },
    'memory': {
        'name': 'memory',
        'description': 'MCP server for persistent memory',
        'qualifiedName': '@modelcontextprotocol/server-memory',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-memory'],
    },
    'fetch': {
        'name': 'fetch',
        'description': 'MCP server for HTTP requests',
        'qualifiedName': '@modelcontextprotocol/server-fetch',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-fetch'],
    },
    'brave-search': {
        'name': 'brave-search',
        'description': 'MCP server for Brave Search',
        'qualifiedName': '@modelcontextprotocol/server-brave-search',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-brave-search'],
    },
}


def get_official_server(name: str) -> Optional[Dict[str, Any]]:
    """
    Get official server info by name.

    Args:
        name: Server name or qualified name

    Returns:
        Server info dict or None if not found.
    """
    # Check by short name
    if name in OFFICIAL_SERVERS:
        return OFFICIAL_SERVERS[name]

    # Check by qualified name
    for server in OFFICIAL_SERVERS.values():
        if server.get('qualifiedName') == name:
            return server

    return None


def get_all_official_servers() -> List[Dict[str, Any]]:
    """Get all official server definitions."""
    return list(OFFICIAL_SERVERS.values())


async def search_registry(
    query: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Search the Smithery MCP registry.

    Args:
        query: Search query
        limit: Maximum number of results

    Returns:
        List of matching server info dicts.
    """
    try:
        import httpx

        async with httpx.AsyncClient(timeout=OFFICIAL_REGISTRY_TIMEOUT) as client:
            response = await client.get(
                f"{OFFICIAL_REGISTRY_URL}/servers",
                params={'q': query, 'pageSize': limit},
                headers={'Accept': 'application/json'},
            )
            response.raise_for_status()
            data = response.json()
            return data.get('servers', [])
    except Exception as e:
        logger.debug(f'Registry search failed: {e}')
        return []


def is_official_server(qualified_name: str) -> bool:
    """
    Check if a server is an official MCP server.

    Args:
        qualified_name: Server qualified name like '@modelcontextprotocol/server-xxx'

    Returns:
        True if the server is from the official MCP org.
    """
    return qualified_name.startswith('@modelcontextprotocol/')
