"""Analytics module exports."""
from claude_code.services.analytics.index import log_event, attach_analytics_sink, log_event_async
from claude_code.services.analytics.config import is_analytics_disabled, is_feedback_survey_disabled
from claude_code.services.analytics.sink import initialize_analytics_sink, initialize_analytics_gates
from claude_code.services.analytics.sink_killswitch import is_sink_killed


def strip_proto_fields(data: dict) -> dict:
    """Remove _PROTO_* keys from a metadata dict.

    These keys are PII-tagged values meant only for privileged BQ columns.
    Strip them before sending to general-access backends like Datadog.
    """
    return {k: v for k, v in data.items() if not k.startswith("_PROTO_")}


__all__ = [
    "log_event",
    "log_event_async",
    "attach_analytics_sink",
    "is_analytics_disabled",
    "is_feedback_survey_disabled",
    "initialize_analytics_sink",
    "initialize_analytics_gates",
    "is_sink_killed",
    "strip_proto_fields",
]
