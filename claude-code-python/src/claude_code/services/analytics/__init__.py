"""Analytics module exports."""
from claude_code.services.analytics.index import log_event, attach_analytics_sink, strip_proto_fields
from claude_code.services.analytics.config import is_analytics_disabled, is_feedback_survey_disabled
from claude_code.services.analytics.sink import initialize_analytics_sink, initialize_analytics_gates
from claude_code.services.analytics.sink_killswitch import is_sink_killed

__all__ = [
    "log_event",
    "attach_analytics_sink",
    "strip_proto_fields",
    "is_analytics_disabled",
    "is_feedback_survey_disabled",
    "initialize_analytics_sink",
    "initialize_analytics_gates",
    "is_sink_killed",
]
