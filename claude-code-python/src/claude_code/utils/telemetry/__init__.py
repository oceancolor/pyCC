"""Telemetry utilities.

Provides OpenTelemetry tracing, BigQuery event export, and session-level
telemetry helpers used to record usage metrics and performance data.

Ported from: src/utils/telemetry/ (TypeScript)

Usage::

    from claude_code.utils.telemetry import TelemetryEvent, log_telemetry_event
"""
from __future__ import annotations

from claude_code.utils.telemetry.events import TelemetryEvent
from claude_code.utils.telemetry.logger import (
    log_telemetry_event,
)

__all__ = [
    "TelemetryEvent",
    "log_telemetry_event",
]
