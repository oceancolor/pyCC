"""
Official marketplace GCS - fetches plugin data from GCS-backed marketplace.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

OFFICIAL_MARKETPLACE_GCS_BASE = (
    "https://storage.googleapis.com/claude-code-plugins"
)


async def fetch_plugin_manifest_from_gcs(
    plugin_id: str,
    version: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch a plugin manifest from GCS storage."""
    return None


async def fetch_plugin_zip_url_from_gcs(
    plugin_id: str,
    version: str,
) -> Optional[str]:
    """Fetch the download URL for a plugin zip from GCS."""
    return None
