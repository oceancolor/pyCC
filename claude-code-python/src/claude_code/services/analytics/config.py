"""Analytics config. Ported from services/analytics/config.ts"""
from __future__ import annotations
import os


def _is_env_truthy(val: str | None) -> bool:
    return val is not None and val.lower() in ("1", "true", "yes")


def is_analytics_disabled() -> bool:
    """Check if analytics operations should be disabled.

    Disabled when:
    - NODE_ENV == 'test'
    - Third-party cloud providers (Bedrock/Vertex/Foundry)
    - Telemetry opted out
    """
    from claude_code.utils.privacy_level import is_telemetry_disabled
    return (
        os.environ.get("NODE_ENV") == "test"
        or _is_env_truthy(os.environ.get("CLAUDE_CODE_USE_BEDROCK"))
        or _is_env_truthy(os.environ.get("CLAUDE_CODE_USE_VERTEX"))
        or _is_env_truthy(os.environ.get("CLAUDE_CODE_USE_FOUNDRY"))
        or is_telemetry_disabled()
    )


def is_feedback_survey_disabled() -> bool:
    """Check if feedback survey should be suppressed.

    Unlike is_analytics_disabled(), does NOT block on 3P providers.
    """
    from claude_code.utils.privacy_level import is_telemetry_disabled
    return os.environ.get("NODE_ENV") == "test" or is_telemetry_disabled()
