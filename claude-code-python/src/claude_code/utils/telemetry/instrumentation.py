"""
instrumentation.py - OpenTelemetry instrumentation setup.

Port of TypeScript instrumentation.ts.
"""

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Global tracer provider
_tracer_provider: Optional[Any] = None
_meter_provider: Optional[Any] = None
_is_initialized = False


def is_telemetry_enabled() -> bool:
    """Check if telemetry is enabled."""
    disabled = os.environ.get('DISABLE_TELEMETRY', '').lower() in ('1', 'true', 'yes')
    return not disabled


def get_tracer(name: str = 'claude-code') -> Any:
    """Get an OpenTelemetry tracer."""
    if not is_telemetry_enabled():
        return _NoopTracer()

    try:
        from opentelemetry import trace
        _ensure_initialized()
        return trace.get_tracer(name)
    except ImportError:
        return _NoopTracer()


def get_meter(name: str = 'claude-code') -> Any:
    """Get an OpenTelemetry meter."""
    if not is_telemetry_enabled():
        return _NoopMeter()

    try:
        from opentelemetry import metrics
        _ensure_initialized()
        return metrics.get_meter(name)
    except ImportError:
        return _NoopMeter()


def _ensure_initialized() -> None:
    """Initialize OpenTelemetry if not already done."""
    global _is_initialized, _tracer_provider, _meter_provider

    if _is_initialized:
        return

    _is_initialized = True

    try:
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.metrics import MeterProvider

        # Check for OTLP endpoint (optional)
        otlp_endpoint = os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT')

        if otlp_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                from opentelemetry.sdk.trace.export import BatchSpanProcessor

                _tracer_provider = TracerProvider()
                exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
                _tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
                trace.set_tracer_provider(_tracer_provider)
            except ImportError:
                _tracer_provider = TracerProvider()
                trace.set_tracer_provider(_tracer_provider)
        else:
            _tracer_provider = TracerProvider()
            trace.set_tracer_provider(_tracer_provider)

        _meter_provider = MeterProvider()
        metrics.set_meter_provider(_meter_provider)

        logger.debug('OpenTelemetry initialized')
    except ImportError:
        logger.debug('OpenTelemetry not available, using noop providers')


def shutdown_instrumentation() -> None:
    """Shutdown OpenTelemetry instrumentation."""
    global _tracer_provider, _meter_provider

    if _tracer_provider and hasattr(_tracer_provider, 'shutdown'):
        try:
            _tracer_provider.shutdown()
        except Exception:
            pass
        _tracer_provider = None

    if _meter_provider and hasattr(_meter_provider, 'shutdown'):
        try:
            _meter_provider.shutdown()
        except Exception:
            pass
        _meter_provider = None


class _NoopSpan:
    """No-op span for when telemetry is disabled."""

    def __enter__(self) -> '_NoopSpan':
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_attributes(self, attributes: dict) -> None:
        pass

    def set_status(self, status: Any) -> None:
        pass

    def record_exception(self, exception: Exception) -> None:
        pass

    def end(self) -> None:
        pass

    def is_recording(self) -> bool:
        return False


class _NoopTracer:
    """No-op tracer for when telemetry is disabled."""

    def start_span(self, name: str, *args: Any, **kwargs: Any) -> _NoopSpan:
        return _NoopSpan()

    def start_as_current_span(self, name: str, *args: Any, **kwargs: Any) -> _NoopSpan:
        return _NoopSpan()


class _NoopCounter:
    """No-op counter for when telemetry is disabled."""

    def add(self, value: Any, *args: Any, **kwargs: Any) -> None:
        pass


class _NoopHistogram:
    """No-op histogram for when telemetry is disabled."""

    def record(self, value: Any, *args: Any, **kwargs: Any) -> None:
        pass


class _NoopMeter:
    """No-op meter for when telemetry is disabled."""

    def create_counter(self, name: str, *args: Any, **kwargs: Any) -> _NoopCounter:
        return _NoopCounter()

    def create_histogram(self, name: str, *args: Any, **kwargs: Any) -> _NoopHistogram:
        return _NoopHistogram()

    def create_up_down_counter(self, name: str, *args: Any, **kwargs: Any) -> _NoopCounter:
        return _NoopCounter()
