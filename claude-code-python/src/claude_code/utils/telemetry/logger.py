"""
logger.py - Telemetry logger for Claude Code.

Port of TypeScript logger.ts.
"""

import logging
import os
from typing import Any, Dict, Optional

# Telemetry logger
_logger = logging.getLogger('claude-code.telemetry')

# Log levels
LOG_LEVEL_DEBUG = 'debug'
LOG_LEVEL_INFO = 'info'
LOG_LEVEL_WARN = 'warn'
LOG_LEVEL_ERROR = 'error'


def _is_telemetry_logging_enabled() -> bool:
    """Check if telemetry logging is enabled."""
    return os.environ.get('CLAUDE_CODE_TELEMETRY_LOG', '').lower() in ('1', 'true', 'verbose')


def log_telemetry_event(
    level: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Log a telemetry event.

    Args:
        level: Log level ('debug', 'info', 'warn', 'error')
        message: Log message
        data: Optional additional data
    """
    if not _is_telemetry_logging_enabled() and level not in (LOG_LEVEL_ERROR,):
        return

    if data:
        formatted = f"[telemetry] {message}: {data}"
    else:
        formatted = f"[telemetry] {message}"

    if level == LOG_LEVEL_DEBUG:
        _logger.debug(formatted)
    elif level == LOG_LEVEL_INFO:
        _logger.info(formatted)
    elif level == LOG_LEVEL_WARN:
        _logger.warning(formatted)
    elif level == LOG_LEVEL_ERROR:
        _logger.error(formatted)
    else:
        _logger.debug(formatted)


def log_span_started(span_name: str, attributes: Optional[Dict] = None) -> None:
    """Log when a span is started."""
    log_telemetry_event(LOG_LEVEL_DEBUG, f"Span started: {span_name}", attributes)


def log_span_ended(
    span_name: str,
    duration_ms: Optional[float] = None,
    status: Optional[str] = None,
) -> None:
    """Log when a span ends."""
    data: Dict[str, Any] = {}
    if duration_ms is not None:
        data['duration_ms'] = duration_ms
    if status is not None:
        data['status'] = status
    log_telemetry_event(LOG_LEVEL_DEBUG, f"Span ended: {span_name}", data or None)


def log_metric_recorded(
    metric_name: str,
    value: Any,
    attributes: Optional[Dict] = None,
) -> None:
    """Log when a metric is recorded."""
    data: Dict[str, Any] = {'value': value}
    if attributes:
        data['attributes'] = attributes
    log_telemetry_event(LOG_LEVEL_DEBUG, f"Metric: {metric_name}", data)


def log_export_error(exporter_name: str, error: Exception) -> None:
    """Log telemetry export errors."""
    log_telemetry_event(
        LOG_LEVEL_ERROR,
        f"Export failed for {exporter_name}",
        {'error': str(error)},
    )
