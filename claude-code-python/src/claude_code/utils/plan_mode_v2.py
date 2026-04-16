"""
Plan Mode V2 - configuration and feature flags.

Mirrors planModeV2.ts: agent-count helpers, experiment variants, and
feature-flag checks for the plan-mode workflow.

Environment variable overrides (all honoured at import time via lazy
helpers so tests can patch os.environ freely):
  CLAUDE_CODE_PLAN_V2_AGENT_COUNT         int 1-10
  CLAUDE_CODE_PLAN_V2_EXPLORE_AGENT_COUNT int 1-10
  CLAUDE_CODE_PLAN_MODE_INTERVIEW_PHASE   truthy/falsy
  CLAUDE_CODE_MCP_INSTR_DELTA             truthy/falsy
  USER_TYPE                               'ant' → always-on paths
"""

from __future__ import annotations

import os
from typing import Literal, Optional

# ---------------------------------------------------------------------------
# Env helpers (thin local stubs — real ones live in env_utils.py)
# ---------------------------------------------------------------------------


def _is_env_truthy(val: Optional[str]) -> bool:
    return val is not None and val.lower() in {"1", "true", "yes", "on"}


def _is_env_defined_falsy(val: Optional[str]) -> bool:
    return val is not None and val.lower() in {"0", "false", "no", "off", ""}


def _get_feature_value(key: str, default: bool) -> bool:  # noqa: ARG001
    """Stub for GrowthBook feature-flag lookup."""
    return default


def _get_subscription_type() -> str:
    """Stub for subscription-type lookup."""
    return os.environ.get("CLAUDE_SUBSCRIPTION_TYPE", "free")


def _get_rate_limit_tier() -> str:
    """Stub for rate-limit-tier lookup."""
    return os.environ.get("CLAUDE_RATE_LIMIT_TIER", "default")


# ---------------------------------------------------------------------------
# Agent-count helpers
# ---------------------------------------------------------------------------


def get_plan_mode_v2_agent_count() -> int:
    """Return the number of agents to spawn in Plan Mode V2.

    Priority:
      1. CLAUDE_CODE_PLAN_V2_AGENT_COUNT env var (1-10)
      2. Subscription/tier rules
      3. Default: 1
    """
    raw = os.environ.get("CLAUDE_CODE_PLAN_V2_AGENT_COUNT")
    if raw:
        try:
            count = int(raw)
            if 1 <= count <= 10:
                return count
        except ValueError:
            pass

    subscription = _get_subscription_type()
    tier = _get_rate_limit_tier()

    if subscription == "max" and tier == "default_claude_max_20x":
        return 3
    if subscription in {"enterprise", "team"}:
        return 3
    return 1


def get_plan_mode_v2_explore_agent_count() -> int:
    """Return the number of explore agents for Plan Mode V2.

    Priority:
      1. CLAUDE_CODE_PLAN_V2_EXPLORE_AGENT_COUNT env var (1-10)
      2. Default: 3
    """
    raw = os.environ.get("CLAUDE_CODE_PLAN_V2_EXPLORE_AGENT_COUNT")
    if raw:
        try:
            count = int(raw)
            if 1 <= count <= 10:
                return count
        except ValueError:
            pass
    return 3


# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------


def is_plan_mode_interview_phase_enabled() -> bool:
    """Return True if the plan-mode interview phase is active.

    Config: ant=always_on, envVar override, GrowthBook gate.
    """
    if os.environ.get("USER_TYPE") == "ant":
        return True
    env = os.environ.get("CLAUDE_CODE_PLAN_MODE_INTERVIEW_PHASE")
    if _is_env_truthy(env):
        return True
    if _is_env_defined_falsy(env):
        return False
    return _get_feature_value("tengu_plan_mode_interview_phase", False)


# ---------------------------------------------------------------------------
# Pewter-ledger experiment variant
# ---------------------------------------------------------------------------

PewterLedgerVariant = Optional[Literal["trim", "cut", "cap"]]


def get_pewter_ledger_variant() -> PewterLedgerVariant:
    """Return the active pewter-ledger experiment arm, or None (control).

    Arms: None (control), 'trim', 'cut', 'cap' — progressively stricter
    guidance on plan file size.
    """
    raw = _get_feature_value("tengu_pewter_ledger", None)  # type: ignore[arg-type]
    if raw in {"trim", "cut", "cap"}:
        return raw  # type: ignore[return-value]
    return None
