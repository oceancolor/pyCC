"""LSP server config. Ported from services/lsp/config.ts"""
from __future__ import annotations
from typing import Any, Dict

# Type alias for scoped LSP server config dicts
ScopedLspServerConfig = Dict[str, Any]


async def get_all_lsp_servers() -> Dict[str, Any]:
    """Get all configured LSP servers from installed plugins.

    LSP servers are only supported via plugins, not user/project settings.

    Returns:
        Dict with key 'servers': a record of scoped server name -> config.
    """
    all_servers: Dict[str, ScopedLspServerConfig] = {}

    try:
        from claude_code.utils.plugins.plugin_loader import load_all_plugins_cache_only
        result = await load_all_plugins_cache_only()
        plugins = result.get("enabled", [])

        for plugin in plugins:
            try:
                from claude_code.utils.plugins.lsp_plugin_integration import get_plugin_lsp_servers
                scoped_servers = await get_plugin_lsp_servers(plugin)
                if scoped_servers:
                    all_servers.update(scoped_servers)
            except Exception:
                continue

    except Exception as e:
        try:
            from claude_code.utils.log import log_error
            log_error(e)
        except Exception:
            pass

    return {"servers": all_servers}
