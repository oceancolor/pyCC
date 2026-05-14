"""Telemetry utilities sub-package. Ported from utils/telemetry/.

Provides OpenTelemetry tracing, BigQuery export, and session telemetry
helpers used across the Claude Code codebase.
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
