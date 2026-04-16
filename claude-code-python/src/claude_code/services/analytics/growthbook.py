"""
GrowthBook feature flags client.

Ported from services/analytics/growthbook.ts (1155 lines).

GrowthBook is used for feature flag management (A/B tests, kill switches,
dynamic configuration). This Python port provides:

- Local environment-variable overrides (CLAUDE_INTERNAL_FC_OVERRIDES)
- Disk-cache fallback (cachedGrowthBookFeatures in global config)
- Remote eval stub (no live GrowthBook SDK — returns cached/default values)

All "blocks on init" / "async" functions are implemented as sync stubs because
the Python port does not run a full GrowthBook SDK client.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable, Dict, Optional, Set, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Module-level state (mirrors TS module-level let variables)
# ---------------------------------------------------------------------------

# Cache for remote-eval feature values populated from disk on first access
_remote_eval_feature_values: Dict[str, Any] = {}

# Track features accessed before init that need exposure logging (stub)
_pending_exposures: Set[str] = set()

# Track features that have already had their exposure logged (dedup)
_logged_exposures: Set[str] = set()

# Experiment data by feature (stub — no live SDK)
_experiment_data_by_feature: Dict[str, Dict[str, Any]] = {}

# Whether GrowthBook env-override parsing has happened
_env_overrides_parsed: bool = False
_env_overrides: Optional[Dict[str, Any]] = None

# Refresh signal listeners (lightweight pub/sub, no threading)
_refresh_listeners: list = []

# Re-initializing promise placeholder (no-op in Python sync context)
_reinitializing: bool = False


# ---------------------------------------------------------------------------
# Env-var overrides
# ---------------------------------------------------------------------------

def _get_env_overrides() -> Optional[Dict[str, Any]]:
    """
    Parse env var overrides for GrowthBook features.

    Set CLAUDE_INTERNAL_FC_OVERRIDES to a JSON object mapping feature keys to
    values to bypass remote eval and disk cache. Only active when USER_TYPE is
    'ant'.

    Example:
        CLAUDE_INTERNAL_FC_OVERRIDES='{"my_feature": true, "my_config": {"key": "val"}}'
    """
    global _env_overrides_parsed, _env_overrides

    if not _env_overrides_parsed:
        _env_overrides_parsed = True
        if os.environ.get("USER_TYPE") == "ant":
            raw = os.environ.get("CLAUDE_INTERNAL_FC_OVERRIDES")
            if raw:
                try:
                    _env_overrides = json.loads(raw)
                    logger.debug(
                        "GrowthBook: Using env var overrides for %d features: %s",
                        len(_env_overrides),
                        ", ".join(_env_overrides.keys()),
                    )
                except json.JSONDecodeError as e:
                    logger.error(
                        "GrowthBook: Failed to parse CLAUDE_INTERNAL_FC_OVERRIDES: %s — %s",
                        raw,
                        e,
                    )
    return _env_overrides


def has_growth_book_env_override(feature: str) -> bool:
    """
    Check if a feature has an env-var override (CLAUDE_INTERNAL_FC_OVERRIDES).
    When True, _CACHED_MAY_BE_STALE will return the override without touching
    disk or network.
    """
    overrides = _get_env_overrides()
    return overrides is not None and feature in overrides


# ---------------------------------------------------------------------------
# Config / config overrides
# ---------------------------------------------------------------------------

def _get_global_config() -> Dict[str, Any]:
    """Retrieve the global config dict, returning {} on any failure."""
    try:
        from ...utils.config import get_global_config
        result = get_global_config()
        return result if isinstance(result, dict) else {}
    except (ImportError, AttributeError, Exception):
        return {}


def _get_config_overrides() -> Optional[Dict[str, Any]]:
    """
    Local config overrides set via /config Gates tab (ant-only).
    Checked after env-var overrides — env wins for eval harnesses.
    """
    if os.environ.get("USER_TYPE") != "ant":
        return None
    try:
        config = _get_global_config()
        return config.get("growthBookOverrides")
    except Exception:
        return None


def _save_global_config_patch(patch: Dict[str, Any]) -> None:
    """Merge a patch into the global config, silently ignoring errors."""
    try:
        from ...utils.config import save_global_config
        save_global_config(lambda c: {**c, **patch})
    except (ImportError, AttributeError, Exception):
        pass


def get_all_growth_book_features() -> Dict[str, Any]:
    """
    Enumerate all known GrowthBook features and their current resolved values.
    In-memory payload first, disk cache fallback.
    Used by the /config Gates tab.
    """
    if _remote_eval_feature_values:
        return dict(_remote_eval_feature_values)
    config = _get_global_config()
    return dict(config.get("cachedGrowthBookFeatures") or {})


def get_growth_book_config_overrides() -> Dict[str, Any]:
    """Return the current config overrides dict (ant-only)."""
    return _get_config_overrides() or {}


def set_growth_book_config_override(feature: str, value: Any) -> None:
    """
    Set or clear a single config override. Pass None to clear.
    Fires onGrowthBookRefresh listeners so systems that bake gate values into
    long-lived objects rebuild.
    """
    if os.environ.get("USER_TYPE") != "ant":
        return
    try:
        from ...utils.config import save_global_config

        def _update(c: Dict[str, Any]) -> Dict[str, Any]:
            current = dict(c.get("growthBookOverrides") or {})
            if value is None:
                if feature not in current:
                    return c
                current.pop(feature, None)
                if not current:
                    result = dict(c)
                    result.pop("growthBookOverrides", None)
                    return result
                return {**c, "growthBookOverrides": current}
            if current.get(feature) == value:
                return c
            return {**c, "growthBookOverrides": {**current, feature: value}}

        save_global_config(_update)
        _emit_refresh()
    except (ImportError, AttributeError, Exception) as e:
        logger.error("GrowthBook: Failed to set config override: %s", e)


def clear_growth_book_config_overrides() -> None:
    """Clear all config overrides (ant-only)."""
    if os.environ.get("USER_TYPE") != "ant":
        return
    try:
        from ...utils.config import save_global_config

        def _update(c: Dict[str, Any]) -> Dict[str, Any]:
            overrides = c.get("growthBookOverrides")
            if not overrides:
                return c
            result = dict(c)
            result.pop("growthBookOverrides", None)
            return result

        save_global_config(_update)
        _emit_refresh()
    except (ImportError, AttributeError, Exception) as e:
        logger.error("GrowthBook: Failed to clear config overrides: %s", e)


def get_api_base_url_host() -> Optional[str]:
    """
    Hostname of ANTHROPIC_BASE_URL when it points at a non-Anthropic proxy.

    Returns None for unset/default (api.anthropic.com) so the attribute
    is absent for direct-API users.
    """
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    if not base_url:
        return None
    try:
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        host = parsed.netloc or parsed.hostname
        if host == "api.anthropic.com":
            return None
        return host or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Refresh signal (lightweight pub/sub, no threading)
# ---------------------------------------------------------------------------

def on_growth_book_refresh(listener: Callable[[], None]) -> Callable[[], None]:
    """
    Register a callback to fire when GrowthBook feature values refresh.
    Returns an unsubscribe function.

    If init has already completed with features, the listener fires once on
    the next iteration (catch-up for late subscribers).
    """
    _refresh_listeners.append(listener)

    def unsubscribe() -> None:
        try:
            _refresh_listeners.remove(listener)
        except ValueError:
            pass

    # Catch-up: if we already have remote eval values, notify immediately
    if _remote_eval_feature_values:
        try:
            listener()
        except Exception as e:
            logger.error("GrowthBook refresh listener error: %s", e)

    return unsubscribe


def _emit_refresh() -> None:
    """Notify all registered refresh listeners."""
    for listener in list(_refresh_listeners):
        try:
            listener()
        except Exception as e:
            logger.error("GrowthBook refresh listener error: %s", e)


# ---------------------------------------------------------------------------
# Feature value resolution (core logic)
# ---------------------------------------------------------------------------

def _resolve_feature_value(feature: str, default_value: T) -> T:
    """
    Internal resolution priority:
    1. Env-var overrides (CLAUDE_INTERNAL_FC_OVERRIDES, ant-only)
    2. Config overrides (growthBookOverrides, ant-only)
    3. In-memory remote eval values (populated at init / refresh)
    4. Disk cache (cachedGrowthBookFeatures in global config)
    5. default_value
    """
    # 1. Env overrides
    overrides = _get_env_overrides()
    if overrides is not None and feature in overrides:
        return overrides[feature]  # type: ignore[return-value]

    # 2. Config overrides (ant-only)
    config_overrides = _get_config_overrides()
    if config_overrides is not None and feature in config_overrides:
        return config_overrides[feature]  # type: ignore[return-value]

    # 3. In-memory remote eval values
    if feature in _remote_eval_feature_values:
        return _remote_eval_feature_values[feature]  # type: ignore[return-value]

    # 4. Disk cache
    try:
        config = _get_global_config()
        cached = (config.get("cachedGrowthBookFeatures") or {}).get(feature)
        if cached is not None:
            return cached  # type: ignore[return-value]
    except Exception:
        pass

    # 5. Default
    return default_value


def _is_growth_book_enabled() -> bool:
    """
    Check if GrowthBook operations should be enabled.
    GrowthBook depends on 1P event logging being enabled.
    """
    try:
        from .first_party_event_logger import is_1p_event_logging_enabled
        return is_1p_event_logging_enabled()
    except (ImportError, AttributeError, Exception):
        # Fall back to checking if there's any cached data or env key
        config = _get_global_config()
        return bool(
            config.get("cachedGrowthBookFeatures")
            or os.environ.get("CLAUDE_INTERNAL_FC_OVERRIDES")
        )


# ---------------------------------------------------------------------------
# Public API — feature value getters
# ---------------------------------------------------------------------------

def get_feature_value_cached_may_be_stale(feature: str, default_value: T) -> T:
    """
    Get a feature value from disk cache immediately. Pure read.

    This is the preferred method for startup-critical paths and sync contexts.
    The value may be stale if the cache was written by a previous process.

    In-memory payload is authoritative once processRemoteEvalPayload has run.
    Falls back to disk cache (survives across process restarts).
    """
    result = _resolve_feature_value(feature, default_value)

    # Track for deferred exposure logging (no-op when SDK is absent)
    if feature not in _experiment_data_by_feature:
        _pending_exposures.add(feature)

    if os.environ.get("USER_TYPE") == "ant":
        logger.debug('GrowthBook: getFeatureValue("%s") = %r', feature, result)

    return result


# Alias used in some callers
def get_feature_value_cached_with_refresh(
    feature: str,
    default_value: T,
    _refresh_interval_ms: int,
) -> T:
    """
    Deprecated: disk cache is now synced on every successful payload load.
    Use get_feature_value_cached_may_be_stale directly.
    """
    return get_feature_value_cached_may_be_stale(feature, default_value)


async def get_feature_value_deprecated(feature: str, default_value: T) -> T:
    """
    Deprecated async getter. Blocks on GrowthBook initialization which can
    slow down startup. Use get_feature_value_cached_may_be_stale instead.

    In the Python port, this is a thin async wrapper that resolves immediately
    from cache/default.
    """
    return get_feature_value_cached_may_be_stale(feature, default_value)


def check_statsig_feature_gate_cached_may_be_stale(gate: str) -> bool:
    """
    Check a Statsig feature gate value via GrowthBook, with fallback to Statsig
    cache.

    MIGRATION ONLY: For migrating existing Statsig gates to GrowthBook.
    For new features, use get_feature_value_cached_may_be_stale() instead.
    """
    overrides = _get_env_overrides()
    if overrides is not None and gate in overrides:
        return bool(overrides[gate])

    config_overrides = _get_config_overrides()
    if config_overrides is not None and gate in config_overrides:
        return bool(config_overrides[gate])

    if not _is_growth_book_enabled():
        return False

    # Track for deferred exposure logging
    _pending_exposures.add(gate)

    config = _get_global_config()

    # GrowthBook cache first
    gb_cached = (config.get("cachedGrowthBookFeatures") or {}).get(gate)
    if gb_cached is not None:
        return bool(gb_cached)

    # Statsig fallback for migration period
    return bool((config.get("cachedStatsigGates") or {}).get(gate, False))


async def check_security_restriction_gate(gate: str) -> bool:
    """
    Check a security restriction gate, waiting for re-init if in progress.

    Use this for security-critical gates where we need fresh values after auth changes.
    Statsig cache is checked first as a safety measure.
    """
    overrides = _get_env_overrides()
    if overrides is not None and gate in overrides:
        return bool(overrides[gate])

    config_overrides = _get_config_overrides()
    if config_overrides is not None and gate in config_overrides:
        return bool(config_overrides[gate])

    if not _is_growth_book_enabled():
        return False

    # (No async re-init wait in Python port — synchronous stub)

    config = _get_global_config()

    # Statsig cache first (safety measure for security checks)
    statsig_cached = (config.get("cachedStatsigGates") or {}).get(gate)
    if statsig_cached is not None:
        return bool(statsig_cached)

    # GrowthBook cache
    gb_cached = (config.get("cachedGrowthBookFeatures") or {}).get(gate)
    if gb_cached is not None:
        return bool(gb_cached)

    return False


async def check_gate_cached_or_blocking(gate: str) -> bool:
    """
    Check a boolean entitlement gate with fallback-to-blocking semantics.

    Fast path: if the disk cache already says True, return it immediately.
    Slow path: if disk says False/missing, awaits GrowthBook init and fetches
    fresh server value (max ~5s). In the Python port, this is a disk-cache
    lookup with a default of False.
    """
    overrides = _get_env_overrides()
    if overrides is not None and gate in overrides:
        return bool(overrides[gate])

    config_overrides = _get_config_overrides()
    if config_overrides is not None and gate in config_overrides:
        return bool(config_overrides[gate])

    if not _is_growth_book_enabled():
        return False

    # Fast path: disk cache says True
    config = _get_global_config()
    cached = (config.get("cachedGrowthBookFeatures") or {}).get(gate)
    if cached is True:
        _pending_exposures.add(gate)
        return True

    # Slow path: return default False (no live SDK in Python port)
    return False


# ---------------------------------------------------------------------------
# Dynamic config wrappers (Statsig API parity)
# ---------------------------------------------------------------------------

async def get_dynamic_config_blocks_on_init(config_name: str, default_value: T) -> T:
    """
    Get a dynamic config value — blocks until GrowthBook is initialized.
    Prefer get_dynamic_config_cached_may_be_stale for startup-critical paths.

    In GrowthBook, dynamic configs are just features with object values.
    """
    return await get_feature_value_deprecated(config_name, default_value)


def get_dynamic_config_cached_may_be_stale(config_name: str, default_value: T) -> T:
    """
    Get a dynamic config value from disk cache immediately.

    This is the preferred method for startup-critical paths and sync contexts.
    In GrowthBook, dynamic configs are just features with object values.
    """
    return get_feature_value_cached_may_be_stale(config_name, default_value)


# ---------------------------------------------------------------------------
# Initialisation / reset
# ---------------------------------------------------------------------------

def _sync_remote_eval_to_disk() -> None:
    """
    Write the complete _remote_eval_feature_values map to disk.

    Wholesale replace (not merge): features deleted server-side are dropped
    from disk on the next successful payload.
    """
    if not _remote_eval_feature_values:
        return
    try:
        fresh = dict(_remote_eval_feature_values)
        config = _get_global_config()
        if config.get("cachedGrowthBookFeatures") == fresh:
            return
        _save_global_config_patch({"cachedGrowthBookFeatures": fresh})
    except Exception as e:
        logger.error("GrowthBook: Failed to sync remote eval to disk: %s", e)


async def initialize_growth_book() -> None:
    """
    Initialize GrowthBook client (blocks until ready).

    In the Python port, this loads the disk-cached feature values into
    _remote_eval_feature_values so that subsequent calls to
    get_feature_value_cached_may_be_stale() use the in-memory map (faster)
    instead of re-parsing the config JSON every call.
    """
    global _remote_eval_feature_values

    config = _get_global_config()
    cached: Dict[str, Any] = config.get("cachedGrowthBookFeatures") or {}

    if cached:
        _remote_eval_feature_values.update(cached)
        logger.debug("GrowthBook: Loaded %d features from disk cache", len(cached))
        _emit_refresh()
    else:
        logger.debug("GrowthBook: No cached features found — using defaults")


async def refresh_growth_book_features() -> None:
    """
    Light refresh — re-fetch features from server without recreating client.

    In the Python port, this is a no-op (no live SDK). Feature values are
    refreshed from disk cache via initialize_growth_book().
    """
    logger.debug("GrowthBook: Light refresh (no-op in Python port)")


def refresh_growth_book_after_auth_change() -> None:
    """
    Refresh GrowthBook after auth changes (login/logout).

    In the Python port, this clears the in-memory cache so the next call
    re-reads from disk.
    """
    global _remote_eval_feature_values
    _remote_eval_feature_values = {}
    _emit_refresh()
    logger.debug("GrowthBook: Cleared in-memory feature values after auth change")


def reset_growth_book() -> None:
    """Reset GrowthBook client state (primarily for testing)."""
    global _remote_eval_feature_values
    global _pending_exposures
    global _logged_exposures
    global _experiment_data_by_feature
    global _env_overrides
    global _env_overrides_parsed
    global _reinitializing
    _remote_eval_feature_values = {}
    _pending_exposures = set()
    _logged_exposures = set()
    _experiment_data_by_feature = {}
    _env_overrides = None
    _env_overrides_parsed = False
    _reinitializing = False
    _refresh_listeners.clear()
    logger.debug("GrowthBook: Reset complete")


def setup_periodic_growth_book_refresh() -> None:
    """
    Set up periodic refresh of GrowthBook features.

    In the Python port, this is a no-op. Long-running processes should call
    refresh_growth_book_features() on their own schedule.
    """
    pass


def stop_periodic_growth_book_refresh() -> None:
    """Stop periodic refresh (for testing or cleanup)."""
    pass


# ---------------------------------------------------------------------------
# Backwards compatibility aliases (match TS export names via snake_case)
# ---------------------------------------------------------------------------

#: Primary cached getter — non-blocking, may return stale values
get_feature_value_CACHED_MAY_BE_STALE = get_feature_value_cached_may_be_stale  # noqa: N816

#: Deprecated async getter
get_feature_value_DEPRECATED = get_feature_value_deprecated  # noqa: N816

#: Statsig migration helper
checkStatsigFeatureGate_CACHED_MAY_BE_STALE = check_statsig_feature_gate_cached_may_be_stale  # noqa: N816

#: Dynamic config cached getter
getDynamicConfig_CACHED_MAY_BE_STALE = get_dynamic_config_cached_may_be_stale  # noqa: N816

#: Dynamic config blocking getter (async)
getDynamicConfig_BLOCKS_ON_INIT = get_dynamic_config_blocks_on_init  # noqa: N816

#: Security gate checker (async)
checkSecurityRestrictionGate = check_security_restriction_gate  # noqa: N816

#: Entitlement gate checker (async, fast-path if cached True)
checkGate_CACHED_OR_BLOCKING = check_gate_cached_or_blocking  # noqa: N816
