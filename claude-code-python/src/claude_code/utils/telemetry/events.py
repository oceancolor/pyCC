"""
events.py - Telemetry event definitions and processing.

Port of TypeScript events.ts.
"""

import hashlib
import json
import os
import platform
import sys
import time
from typing import Any, Dict, List, Optional

# Event type constants
INTERACTION_EVENT = 'tengu_session_interaction'
LLM_REQUEST_EVENT = 'tengu_llm_request'
TOOL_EVENT = 'tengu_tool_use'
BASH_EXEC_EVENT = 'tengu_bash_exec'

# Status values
STATUS_SUCCESS = 'success'
STATUS_ERROR = 'error'
STATUS_ABORTED = 'aborted'


class TelemetryEvent:
    """Represents a telemetry event."""

    def __init__(
        self,
        event_type: str,
        attributes: Optional[Dict[str, Any]] = None,
        timestamp: Optional[float] = None,
    ):
        self.event_type = event_type
        self.attributes: Dict[str, Any] = attributes or {}
        self.timestamp = timestamp or time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'eventType': self.event_type,
            'attributes': self.attributes,
            'timestamp': self.timestamp,
        }


def build_resource_attributes() -> Dict[str, str]:
    """Build standard resource attributes for telemetry."""
    import importlib.metadata

    try:
        version = importlib.metadata.version('claude-code')
    except Exception:
        version = 'unknown'

    uname = platform.uname()
    os_type = {
        'linux': 'linux',
        'darwin': 'darwin',
        'windows': 'windows',
    }.get(sys.platform, 'unknown')

    return {
        'service.name': 'claude-code',
        'service.version': version,
        'os.type': os_type,
        'os.version': uname.release,
        'host.arch': uname.machine,
    }


def get_session_id_for_telemetry() -> str:
    """Get the session ID for telemetry."""
    try:
        from ...bootstrap.state import get_session_id
        return get_session_id()
    except ImportError:
        return 'unknown'


def hash_message_for_telemetry(message: Any) -> str:
    """Hash a message for telemetry (privacy-preserving)."""
    try:
        content = json.dumps(message, ensure_ascii=False, default=str)
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
    except Exception:
        return 'unknown'


def build_interaction_event(
    session_id: str,
    user_prompt: str,
    model: str,
    tool_names: List[str],
    status: str = STATUS_SUCCESS,
    error: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> TelemetryEvent:
    """Build a session interaction telemetry event."""
    attrs: Dict[str, Any] = {
        'session.id': session_id,
        'model': model,
        'tool_names': ','.join(tool_names),
        'status': status,
    }

    if error:
        attrs['error'] = error[:500]

    if duration_ms is not None:
        attrs['duration_ms'] = duration_ms

    return TelemetryEvent(INTERACTION_EVENT, attrs)


def build_llm_request_event(
    session_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    status: str = STATUS_SUCCESS,
    error: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> TelemetryEvent:
    """Build an LLM request telemetry event."""
    attrs: Dict[str, Any] = {
        'session.id': session_id,
        'model': model,
        'tokens.input': input_tokens,
        'tokens.output': output_tokens,
        'tokens.cache_read': cache_read_tokens,
        'tokens.cache_creation': cache_creation_tokens,
        'status': status,
    }

    if error:
        attrs['error'] = error[:500]

    if duration_ms is not None:
        attrs['duration_ms'] = duration_ms

    return TelemetryEvent(LLM_REQUEST_EVENT, attrs)


def build_tool_event(
    session_id: str,
    tool_name: str,
    status: str = STATUS_SUCCESS,
    error: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> TelemetryEvent:
    """Build a tool use telemetry event."""
    attrs: Dict[str, Any] = {
        'session.id': session_id,
        'tool.name': tool_name,
        'status': status,
    }

    if error:
        attrs['error'] = error[:500]

    if duration_ms is not None:
        attrs['duration_ms'] = duration_ms

    return TelemetryEvent(TOOL_EVENT, attrs)
