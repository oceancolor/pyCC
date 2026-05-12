"""
session_tracing.py - Session-level OpenTelemetry tracing utilities.

Port of TypeScript sessionTracing.ts.
"""

import contextlib
import logging
import os
import time
from typing import Any, Callable, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

# Span name constants
SESSION_SPAN = 'claude_code.session'
INTERACTION_SPAN = 'claude_code.interaction'
LLM_REQUEST_SPAN = 'claude_code.llm_request'
TOOL_SPAN = 'claude_code.tool'
BASH_EXEC_SPAN = 'claude_code.bash_exec'


class SpanContext:
    """Context for a tracing span."""

    def __init__(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.attributes: Dict[str, Any] = attributes or {}
        self.start_time = time.monotonic()
        self._span: Optional[Any] = None
        self._status: str = 'ok'
        self._error: Optional[Exception] = None

    def set_attribute(self, key: str, value: Any) -> None:
        """Set a span attribute."""
        self.attributes[key] = value
        if self._span and hasattr(self._span, 'set_attribute'):
            self._span.set_attribute(key, value)

    def set_attributes(self, attrs: Dict[str, Any]) -> None:
        """Set multiple span attributes."""
        for k, v in attrs.items():
            self.set_attribute(k, v)

    def record_error(self, error: Exception) -> None:
        """Record an error on the span."""
        self._status = 'error'
        self._error = error
        if self._span and hasattr(self._span, 'record_exception'):
            self._span.record_exception(error)

    def get_duration_ms(self) -> float:
        """Get elapsed time in milliseconds."""
        return (time.monotonic() - self.start_time) * 1000


class SessionTracer:
    """Session-level tracer for Claude Code."""

    def __init__(self):
        self._session_span: Optional[SpanContext] = None
        self._current_interaction_span: Optional[SpanContext] = None
        self._current_llm_span: Optional[SpanContext] = None
        self._current_tool_span: Optional[SpanContext] = None
        self._tracer: Optional[Any] = None

    def _get_tracer(self) -> Any:
        if self._tracer is None:
            from .instrumentation import get_tracer
            self._tracer = get_tracer('claude-code.session')
        return self._tracer

    def start_session_span(
        self,
        session_id: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> SpanContext:
        """Start the session-level span."""
        ctx = SpanContext(SESSION_SPAN, {'session.id': session_id, **(attributes or {})})
        self._session_span = ctx
        return ctx

    def end_session_span(self) -> None:
        """End the session-level span."""
        self._session_span = None

    def start_interaction_span(
        self,
        session_id: str,
        model: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> SpanContext:
        """Start an interaction-level span."""
        ctx = SpanContext(INTERACTION_SPAN, {
            'session.id': session_id,
            'model': model,
            **(attributes or {}),
        })
        self._current_interaction_span = ctx
        return ctx

    def end_interaction_span(self, end_attributes: Optional[Dict] = None) -> None:
        """End the current interaction span."""
        if self._current_interaction_span and end_attributes:
            self._current_interaction_span.set_attributes(end_attributes)
        self._current_interaction_span = None

    def start_llm_request_span(
        self,
        model: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> SpanContext:
        """Start an LLM request span."""
        ctx = SpanContext(LLM_REQUEST_SPAN, {'model': model, **(attributes or {})})
        self._current_llm_span = ctx
        return ctx

    def end_llm_request_span(self, end_attributes: Optional[Dict] = None) -> None:
        """End the current LLM request span."""
        if self._current_llm_span and end_attributes:
            self._current_llm_span.set_attributes(end_attributes)
        self._current_llm_span = None

    def start_tool_span(
        self,
        tool_name: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> SpanContext:
        """Start a tool use span."""
        ctx = SpanContext(TOOL_SPAN, {'tool.name': tool_name, **(attributes or {})})
        self._current_tool_span = ctx
        return ctx

    def end_tool_span(self, end_attributes: Optional[Dict] = None) -> None:
        """End the current tool span."""
        if self._current_tool_span and end_attributes:
            self._current_tool_span.set_attributes(end_attributes)
        self._current_tool_span = None


# Global session tracer
_session_tracer: Optional[SessionTracer] = None


def get_session_tracer() -> SessionTracer:
    """Get the global session tracer."""
    global _session_tracer
    if _session_tracer is None:
        _session_tracer = SessionTracer()
    return _session_tracer


def start_session_span(
    session_id: str,
    attributes: Optional[Dict[str, Any]] = None,
) -> SpanContext:
    """Start the session-level span."""
    return get_session_tracer().start_session_span(session_id, attributes)


def end_session_span() -> None:
    """End the session-level span."""
    get_session_tracer().end_session_span()


def start_interaction_span(
    session_id: str,
    model: str,
    attributes: Optional[Dict[str, Any]] = None,
) -> SpanContext:
    """Start an interaction span."""
    return get_session_tracer().start_interaction_span(session_id, model, attributes)


def end_interaction_span(end_attributes: Optional[Dict] = None) -> None:
    """End the current interaction span."""
    get_session_tracer().end_interaction_span(end_attributes)


def start_llm_request_span(
    model: str,
    attributes: Optional[Dict[str, Any]] = None,
) -> SpanContext:
    """Start an LLM request span."""
    return get_session_tracer().start_llm_request_span(model, attributes)


def end_llm_request_span(end_attributes: Optional[Dict] = None) -> None:
    """End the current LLM request span."""
    get_session_tracer().end_llm_request_span(end_attributes)


def start_tool_span(
    tool_name: str,
    attributes: Optional[Dict[str, Any]] = None,
) -> SpanContext:
    """Start a tool span."""
    return get_session_tracer().start_tool_span(tool_name, attributes)


def end_tool_span(end_attributes: Optional[Dict] = None) -> None:
    """End the current tool span."""
    get_session_tracer().end_tool_span(end_attributes)
