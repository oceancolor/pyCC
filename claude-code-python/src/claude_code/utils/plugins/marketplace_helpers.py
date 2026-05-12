"""
Marketplace helpers - helper functions for marketplace operations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def format_marketplace_url(base_url: str, plugin_id: str) -> str:
    """Format a URL to fetch plugin info from the marketplace."""
    base = base_url.rstrip("/")
    return f"{base}/plugins/{plugin_id}"


def parse_marketplace_search_results(data: Any) -> List[Dict[str, Any]]:
    """Parse marketplace search results into a normalized list."""
    if not isinstance(data, (list, dict)):
        return []
    if isinstance(data, list):
        return [p for p in data if isinstance(p, dict)]
    results = data.get("results") or data.get("plugins") or []
    return [p for p in results if isinstance(p, dict)]


def sort_plugins_by_relevance(
    plugins: List[Dict[str, Any]],
    query: str,
) -> List[Dict[str, Any]]:
    """Sort plugins by relevance to a search query."""
    query_lower = query.lower()

    def score(plugin: Dict[str, Any]) -> int:
        name = (plugin.get("name") or "").lower()
        desc = (plugin.get("description") or "").lower()
        s = 0
        if query_lower in name:
            s += 10
        if query_lower in desc:
            s += 5
        return s

    return sorted(plugins, key=score, reverse=True)


def get_plugin_display_name(plugin: Dict[str, Any]) -> str:
    """Get a display name for a plugin."""
    return (
        plugin.get("displayName")
        or plugin.get("title")
        or plugin.get("name")
        or plugin.get("id")
        or "Unknown Plugin"
    )
