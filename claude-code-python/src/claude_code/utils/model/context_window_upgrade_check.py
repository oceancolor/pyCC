"""Context window upgrade check utilities. Ported from utils/model/contextWindowUpgradeCheck.ts"""

from __future__ import annotations

from typing import Optional

from .check1m_access import check_opus_1m_access, check_sonnet_1m_access


def _get_available_upgrade() -> Optional[dict]:
    """Get available model upgrade for more context, or None if unavailable.

    Returns a dict with keys: alias, name, multiplier.
    """
    from .model import get_user_specified_model_setting

    current = get_user_specified_model_setting()
    if current == "opus" and check_opus_1m_access():
        return {"alias": "opus[1m]", "name": "Opus 1M", "multiplier": 5}
    if current == "sonnet" and check_sonnet_1m_access():
        return {"alias": "sonnet[1m]", "name": "Sonnet 1M", "multiplier": 5}
    return None


def get_upgrade_message(context: str) -> Optional[str]:
    """Get upgrade message for different contexts.

    Args:
        context: Either 'warning' or 'tip'.

    Returns:
        A human-readable string, or None if no upgrade is available.
    """
    upgrade = _get_available_upgrade()
    if not upgrade:
        return None

    if context == "warning":
        return f"/model {upgrade['alias']}"
    if context == "tip":
        return f"Tip: You have access to {upgrade['name']} with {upgrade['multiplier']}x more context"
    return None
