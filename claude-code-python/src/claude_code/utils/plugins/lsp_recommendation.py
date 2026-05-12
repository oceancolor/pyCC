"""
LSP recommendation - recommends LSP-related plugins.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def get_lsp_plugin_recommendations(
    file_extensions: Optional[List[str]] = None,
    installed_plugins: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Get LSP plugin recommendations based on file types in the project."""
    return []


def should_recommend_lsp_plugin(
    plugin_id: str,
    file_extensions: List[str],
) -> bool:
    """Check if an LSP plugin should be recommended for the given file types."""
    return False
