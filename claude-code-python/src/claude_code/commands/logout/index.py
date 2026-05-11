"""
Ported from: commands/logout/logout.tsx

/logout command — remove stored credentials, clear all auth-related caches,
and exit the REPL.

The React JSX rendering from the TS source is replaced with a plain print
message.  A best-effort graceful shutdown is attempted after 200 ms.
"""
from __future__ import annotations

import asyncio
from typing import Dict


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

async def _remove_api_key() -> None:
    try:
        from claude_code.utils.auth import remove_api_key  # type: ignore[import]
        await remove_api_key()
    except (ImportError, Exception):  # noqa: BLE001
        pass


def _delete_secure_storage() -> None:
    try:
        from claude_code.utils.secure_storage.index import get_secure_storage  # type: ignore[import]
        storage = get_secure_storage()
        storage.delete()
    except (ImportError, Exception):  # noqa: BLE001
        pass


async def _flush_telemetry() -> None:
    try:
        from claude_code.utils.telemetry.instrumentation import flush_telemetry  # type: ignore[import]
        await flush_telemetry()
    except (ImportError, Exception):  # noqa: BLE001
        pass


async def _clear_auth_related_caches() -> None:
    """Clear all in-memory caches that are invalidated by an auth change."""
    try:
        from claude_code.utils.auth import get_claude_ai_oauth_tokens  # type: ignore[import]
        cache = getattr(get_claude_ai_oauth_tokens, "cache", None)
        if cache and hasattr(cache, "clear"):
            cache.clear()
    except (ImportError, Exception):
        pass

    for fn_path in [
        "claude_code.bridge.trusted_device:clear_trusted_device_token_cache",
        "claude_code.utils.betas:clear_betas_caches",
        "claude_code.utils.tool_schema_cache:clear_tool_schema_cache",
        "claude_code.utils.user:reset_user_cache",
        "claude_code.services.analytics.growthbook:refresh_growth_book_after_auth_change",
    ]:
        try:
            module_path, _, fn_name = fn_path.partition(":")
            import importlib
            mod = importlib.import_module(module_path)
            fn = getattr(mod, fn_name)
            result = fn()
            if asyncio.iscoroutine(result):
                await result
        except (ImportError, AttributeError, Exception):
            pass

    # Async caches
    for fn_path in [
        "claude_code.services.remote_managed_settings.index:clear_remote_managed_settings_cache",
        "claude_code.services.policy_limits.index:clear_policy_limits_cache",
    ]:
        try:
            module_path, _, fn_name = fn_path.partition(":")
            import importlib
            mod = importlib.import_module(module_path)
            fn = getattr(mod, fn_name)
            await fn()
        except (ImportError, AttributeError, Exception):
            pass


def _save_global_config_on_logout(clear_onboarding: bool) -> None:
    try:
        from claude_code.utils.config import save_global_config  # type: ignore[import]

        def _updater(current: dict) -> dict:
            updated = dict(current)
            if clear_onboarding:
                updated["hasCompletedOnboarding"] = False
                updated["subscriptionNoticeCount"] = 0
                updated["hasAvailableSubscription"] = False
                if (
                    isinstance(updated.get("customApiKeyResponses"), dict)
                    and updated["customApiKeyResponses"].get("approved")
                ):
                    updated["customApiKeyResponses"] = {
                        **updated["customApiKeyResponses"],
                        "approved": [],
                    }
            updated["oauthAccount"] = None
            return updated

        save_global_config(_updater)
    except (ImportError, Exception):  # noqa: BLE001
        pass


def _graceful_shutdown_sync(code: int, reason: str) -> None:
    try:
        from claude_code.utils.graceful_shutdown import graceful_shutdown_sync  # type: ignore[import]
        graceful_shutdown_sync(code, reason)
    except (ImportError, Exception):
        import sys
        sys.exit(code)


# ---------------------------------------------------------------------------
# Core logout logic (reusable)
# ---------------------------------------------------------------------------

async def perform_logout(*, clear_onboarding: bool = False) -> None:
    """
    Flush telemetry, clear credentials, wipe secure storage, and reset caches.

    Parameters
    ----------
    clear_onboarding:
        When True, reset onboarding flags in the global config (used by /logout).
    """
    # Flush telemetry BEFORE clearing credentials to avoid org data leakage
    await _flush_telemetry()
    await _remove_api_key()
    _delete_secure_storage()
    await _clear_auth_related_caches()
    _save_global_config_on_logout(clear_onboarding)


# ---------------------------------------------------------------------------
# Command entry point
# ---------------------------------------------------------------------------

async def call() -> Dict[str, str]:
    """
    Handle the /logout command.

    Performs logout, prints a confirmation message, and schedules a
    graceful shutdown after 200 ms.

    Returns
    -------
    dict
        ``{"type": "text", "value": <message>}``
    """
    await perform_logout(clear_onboarding=True)

    message = "Successfully logged out from your Anthropic account."
    print(message)

    async def _shutdown_soon() -> None:
        await asyncio.sleep(0.2)
        _graceful_shutdown_sync(0, "logout")

    asyncio.ensure_future(_shutdown_soon())

    return {"type": "text", "value": message}
