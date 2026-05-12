"""
Fetch telemetry - tracks plugin installation/usage telemetry.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def record_plugin_install_event(
    plugin_id: str,
    version: Optional[str] = None,
    source: str = "marketplace",
) -> None:
    """Record a plugin installation event for telemetry."""
    # Telemetry is a no-op in the Python port.
    pass


def record_plugin_uninstall_event(plugin_id: str) -> None:
    """Record a plugin uninstall event for telemetry."""
    pass


def record_plugin_usage_event(
    plugin_id: str,
    event_type: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Record a plugin usage event."""
    pass
