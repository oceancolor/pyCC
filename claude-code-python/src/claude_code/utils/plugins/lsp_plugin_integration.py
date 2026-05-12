"""
LSP plugin integration - integrates Language Server Protocol plugins.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def get_lsp_plugins() -> List[Dict[str, Any]]:
    """Get list of installed LSP-type plugins."""
    return []


def start_lsp_plugin(plugin_id: str, workspace_root: str) -> Optional[Dict[str, Any]]:
    """Start an LSP plugin server. Returns connection info or None."""
    return None


def stop_lsp_plugin(plugin_id: str) -> None:
    """Stop a running LSP plugin server."""
    pass


def get_lsp_plugin_capabilities(plugin_id: str) -> Dict[str, Any]:
    """Get capabilities of an LSP plugin."""
    return {}
