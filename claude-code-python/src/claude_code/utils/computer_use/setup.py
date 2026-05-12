"""
setup.py - Setup utilities for computer use MCP.

Port of TypeScript setup.ts.
"""

import sys
from typing import Any, Dict, List, Optional


def build_mcp_tool_name(server_name: str, tool_name: str) -> str:
    """Build an MCP tool name from server and tool names."""
    return f"mcp__{server_name}__{tool_name}"


def setup_computer_use_mcp() -> Dict[str, Any]:
    """
    Setup computer use MCP configuration.

    Returns:
        Dict with 'mcpConfig' and 'allowedTools' keys.
    """
    from .common import COMPUTER_USE_MCP_SERVER_NAME, CLI_CU_CAPABILITIES
    from .gates import get_chicago_coordinate_mode

    # Get all computer use tool names
    allowed_tools = _build_computer_use_tools(
        CLI_CU_CAPABILITIES,
        get_chicago_coordinate_mode(),
    )
    allowed_tool_names = [
        build_mcp_tool_name(COMPUTER_USE_MCP_SERVER_NAME, tool['name'])
        for tool in allowed_tools
    ]

    mcp_config = {
        COMPUTER_USE_MCP_SERVER_NAME: {
            'type': 'stdio',
            'command': sys.executable,
            'args': ['-m', 'claude_code.utils.computer_use.mcp_server'],
            'scope': 'dynamic',
        }
    }

    return {
        'mcpConfig': mcp_config,
        'allowedTools': allowed_tool_names,
    }


def _build_computer_use_tools(
    capabilities: Dict[str, Any],
    coordinate_mode: str,
) -> List[Dict[str, str]]:
    """Build the list of computer use tool definitions."""
    # Standard computer use tools
    tools = [
        {'name': 'screenshot'},
        {'name': 'click'},
        {'name': 'type_text'},
        {'name': 'key'},
        {'name': 'scroll'},
        {'name': 'move_mouse'},
        {'name': 'drag'},
        {'name': 'request_access'},
        {'name': 'get_screen_info'},
        {'name': 'list_granted_applications'},
    ]
    return tools
