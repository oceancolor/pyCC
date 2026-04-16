"""MCP OAuth port helper. Ported from services/mcp/oauthPort.ts"""
import os

DEFAULT_MCP_OAUTH_PORT = 8484

def get_mcp_oauth_port() -> int:
    val = os.environ.get("CLAUDE_CODE_MCP_OAUTH_PORT")
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return DEFAULT_MCP_OAUTH_PORT
