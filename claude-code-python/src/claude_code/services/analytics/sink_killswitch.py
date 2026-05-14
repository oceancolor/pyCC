"""Analytics sink killswitch. Ported from services/analytics/sinkKillswitch.ts"""
from __future__ import annotations
from typing import Literal

SinkName = Literal["datadog", "firstParty"]

# Mangled name: per-sink analytics killswitch
_SINK_KILLSWITCH_CONFIG_NAME = "tengu_frond_boric"


def is_sink_killed(sink: SinkName) -> bool:
    """Check if an analytics sink has been killed via dynamic config.

    GrowthBook JSON config shape: { datadog?: boolean, firstParty?: boolean }
    A value of True stops all dispatch to that sink.
    Fail-open: missing/malformed config leaves sink on.
    """
    try:
        from claude_code.services.analytics.growthbook import get_dynamic_config_cached_may_be_stale
        config: dict = get_dynamic_config_cached_may_be_stale(_SINK_KILLSWITCH_CONFIG_NAME, {})
        if config is None:
            return False
        return config.get(sink) is True
    except Exception:
        return False
