"""
gates.py - Feature gates for computer use (Chicago MCP).

Port of TypeScript gates.ts.
"""

import os
import sys
from typing import Optional

# Default configuration
_DEFAULTS = {
    'enabled': False,
    'pixelValidation': False,
    'clipboardPasteMultiline': True,
    'mouseAnimation': True,
    'hideBeforeAction': True,
    'autoTargetDisplay': True,
    'clipboardGuard': True,
    'coordinateMode': 'pixels',
}

# Frozen coordinate mode (set once on first read)
_frozen_coordinate_mode: Optional[str] = None


def _read_config() -> dict:
    """Read Chicago configuration from dynamic config."""
    try:
        from ...services.analytics.growthbook import get_dynamic_config_cached_may_be_stale
        partial = get_dynamic_config_cached_may_be_stale('tengu_malort_pedway', _DEFAULTS)
        return {**_DEFAULTS, **partial}
    except ImportError:
        return dict(_DEFAULTS)


def _has_required_subscription() -> bool:
    """Check if user has required subscription (Max/Pro or ant)."""
    if os.environ.get('USER_TYPE') == 'ant':
        return True

    try:
        from ...utils.auth import get_subscription_type
        tier = get_subscription_type()
        return tier in ('max', 'pro')
    except Exception:
        return False


def get_chicago_enabled() -> bool:
    """Check if Chicago (computer use) MCP is enabled."""
    if sys.platform != 'darwin':
        return False

    # Disable for ants with monorepo access unless overridden
    if (os.environ.get('USER_TYPE') == 'ant'
            and os.environ.get('MONOREPO_ROOT_DIR')
            and not _is_env_truthy(os.environ.get('ALLOW_ANT_COMPUTER_USE_MCP', ''))):
        return False

    return _has_required_subscription() and _read_config().get('enabled', False)


def get_chicago_sub_gates() -> dict:
    """Get sub-feature gates for Chicago."""
    config = _read_config()
    return {k: v for k, v in config.items() if k not in ('enabled', 'coordinateMode')}


def get_chicago_coordinate_mode() -> str:
    """
    Get the coordinate mode (frozen at first read).
    Returns 'pixels' or 'normalized'.
    """
    global _frozen_coordinate_mode
    if _frozen_coordinate_mode is None:
        _frozen_coordinate_mode = _read_config().get('coordinateMode', 'pixels')
    return _frozen_coordinate_mode


def _is_env_truthy(value: str) -> bool:
    """Check if an environment variable value is truthy."""
    return value.lower() in ('1', 'true', 'yes', 'on') if value else False
