"""1M context window access check utilities. Ported from utils/model/check1mAccess.ts"""

from __future__ import annotations

import os
from typing import Optional

# Disabled reasons that still count as "provisioned" (credits depleted, but not disabled)
_PROVISIONED_DISABLED_REASONS = frozenset(["out_of_credits"])

# Disabled reasons that mean "not provisioned or actively disabled"
_NOT_PROVISIONED_REASONS = frozenset([
    "overage_not_provisioned",
    "org_level_disabled",
    "org_level_disabled_until",
    "seat_tier_level_disabled",
    "member_level_disabled",
    "seat_tier_zero_credit_limit",
    "group_zero_credit_limit",
    "member_zero_credit_limit",
    "org_service_level_disabled",
    "org_service_zero_credit_limit",
    "no_limits_configured",
    "unknown",
])


def _is_1m_context_disabled() -> bool:
    """Check if 1M context is disabled via the CLAUDE_CODE_DISABLE_1M_CONTEXT env var."""
    val = os.environ.get("CLAUDE_CODE_DISABLE_1M_CONTEXT", "").lower()
    return val in ("1", "true", "yes")


def _is_claude_ai_subscriber() -> bool:
    """Check if the current user is a claude.ai subscriber (not API/PAYG)."""
    try:
        from claude_code.utils.auth import auth as auth_module
        return auth_module.is_claude_ai_subscriber()
    except Exception:
        return False


def _is_extra_usage_enabled() -> bool:
    """Check if extra usage (1M context) is enabled based on the cached disabled reason.

    - undefined/missing: treat as not enabled (conservative)
    - null/empty: no disabled reason → enabled
    - 'out_of_credits': provisioned but depleted → still counts as enabled
    - anything else → not enabled
    """
    try:
        from claude_code.utils.config import get_global_config
        config = get_global_config()
        reason = getattr(config, "cached_extra_usage_disabled_reason", None)
    except Exception:
        return False

    # Sentinel: key not present at all → conservative "not enabled"
    if reason is None:
        return False
    # Explicit null equivalent (empty string) → no disabled reason → enabled
    if reason == "":
        return True
    if reason in _PROVISIONED_DISABLED_REASONS:
        return True
    return False


def check_opus_1m_access() -> bool:
    """Return True if the current user can access Opus with 1M context."""
    if _is_1m_context_disabled():
        return False
    if _is_claude_ai_subscriber():
        return _is_extra_usage_enabled()
    # Non-subscribers (API/PAYG) have access
    return True


def check_sonnet_1m_access() -> bool:
    """Return True if the current user can access Sonnet with 1M context."""
    if _is_1m_context_disabled():
        return False
    if _is_claude_ai_subscriber():
        return _is_extra_usage_enabled()
    # Non-subscribers (API/PAYG) have access
    return True
