"""
plugin_telemetry.py - Plugin telemetry utilities.

Port of TypeScript pluginTelemetry.ts.
"""

import os
import time
from typing import Any, Dict, List, Optional


class PluginTelemetryCollector:
    """Collects telemetry data from plugins."""

    def __init__(self):
        self._plugin_events: List[Dict[str, Any]] = []
        self._plugin_errors: List[Dict[str, Any]] = []
        self._plugin_durations: Dict[str, List[float]] = {}

    def record_plugin_event(
        self,
        plugin_name: str,
        event_type: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a plugin telemetry event."""
        event = {
            'pluginName': plugin_name,
            'eventType': event_type,
            'timestamp': time.time(),
            'attributes': attributes or {},
        }
        self._plugin_events.append(event)

    def record_plugin_error(
        self,
        plugin_name: str,
        error: Exception,
        context: Optional[str] = None,
    ) -> None:
        """Record a plugin error."""
        error_entry = {
            'pluginName': plugin_name,
            'error': str(error),
            'errorType': type(error).__name__,
            'timestamp': time.time(),
        }
        if context:
            error_entry['context'] = context
        self._plugin_errors.append(error_entry)

    def record_plugin_duration(
        self,
        plugin_name: str,
        operation: str,
        duration_ms: float,
    ) -> None:
        """Record how long a plugin operation took."""
        key = f"{plugin_name}.{operation}"
        if key not in self._plugin_durations:
            self._plugin_durations[key] = []
        self._plugin_durations[key].append(duration_ms)

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of collected plugin telemetry."""
        return {
            'totalEvents': len(self._plugin_events),
            'totalErrors': len(self._plugin_errors),
            'plugins': list({e['pluginName'] for e in self._plugin_events}),
            'averageDurations': {
                key: sum(durations) / len(durations)
                for key, durations in self._plugin_durations.items()
                if durations
            },
        }

    def clear(self) -> None:
        """Clear all collected telemetry."""
        self._plugin_events.clear()
        self._plugin_errors.clear()
        self._plugin_durations.clear()


# Global instance
_collector: Optional[PluginTelemetryCollector] = None


def get_plugin_telemetry_collector() -> PluginTelemetryCollector:
    """Get the global plugin telemetry collector."""
    global _collector
    if _collector is None:
        _collector = PluginTelemetryCollector()
    return _collector


def record_plugin_load(
    plugin_name: str,
    version: Optional[str] = None,
    duration_ms: Optional[float] = None,
) -> None:
    """
    Record a plugin being loaded.

    Args:
        plugin_name: Name of the plugin
        version: Plugin version if available
        duration_ms: How long loading took
    """
    collector = get_plugin_telemetry_collector()

    attrs: Dict[str, Any] = {}
    if version:
        attrs['version'] = version

    collector.record_plugin_event(plugin_name, 'load', attrs)

    if duration_ms is not None:
        collector.record_plugin_duration(plugin_name, 'load', duration_ms)


def record_plugin_tool_call(
    plugin_name: str,
    tool_name: str,
    duration_ms: Optional[float] = None,
    error: Optional[Exception] = None,
) -> None:
    """
    Record a plugin tool call.

    Args:
        plugin_name: Name of the plugin
        tool_name: Name of the tool called
        duration_ms: How long the call took
        error: Any error that occurred
    """
    collector = get_plugin_telemetry_collector()

    if error:
        collector.record_plugin_error(plugin_name, error, context=tool_name)
    else:
        attrs: Dict[str, Any] = {'toolName': tool_name}
        collector.record_plugin_event(plugin_name, 'tool_call', attrs)

    if duration_ms is not None:
        collector.record_plugin_duration(plugin_name, f"tool.{tool_name}", duration_ms)
