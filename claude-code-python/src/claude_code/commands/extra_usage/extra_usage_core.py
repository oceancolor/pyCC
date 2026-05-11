"""
Extra usage core logic.

Ported from: commands/extra-usage/extra-usage-core.ts

Handles the business logic for the /extra-usage command:
  - Checks whether the user is a team/enterprise subscriber without
    billing access and, if so, attempts to submit an admin request.
  - Otherwise opens the billing URL in the system browser.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Typed result (mirrors the TS union type ExtraUsageResult)
# ---------------------------------------------------------------------------

# { "type": "message", "value": <str> }
# { "type": "browser-opened", "url": <str>, "opened": <bool> }


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

def _get_global_config() -> dict:
    try:
        from claude_code.utils.config import get_global_config  # type: ignore[import]
        return get_global_config()
    except ImportError:
        return {}


def _save_global_config(updater) -> None:
    try:
        from claude_code.utils.config import save_global_config  # type: ignore[import]
        save_global_config(updater)
    except ImportError:
        pass


def _get_subscription_type() -> Optional[str]:
    try:
        from claude_code.utils.auth import get_subscription_type  # type: ignore[import]
        return get_subscription_type()
    except ImportError:
        return None


def _has_claude_ai_billing_access() -> bool:
    try:
        from claude_code.utils.billing import has_claude_ai_billing_access  # type: ignore[import]
        return has_claude_ai_billing_access()
    except ImportError:
        return True  # Safe default: don't block


def _invalidate_overage_credit_grant_cache() -> None:
    try:
        from claude_code.services.api.overage_credit_grant import (  # type: ignore[import]
            invalidate_overage_credit_grant_cache,
        )
        invalidate_overage_credit_grant_cache()
    except ImportError:
        pass


async def _fetch_utilization() -> Optional[Dict[str, Any]]:
    try:
        from claude_code.services.api.usage import fetch_utilization  # type: ignore[import]
        return await fetch_utilization()
    except ImportError:
        return None


async def _check_admin_request_eligibility(request_type: str) -> Optional[Dict[str, Any]]:
    try:
        from claude_code.services.api.admin_requests import (  # type: ignore[import]
            check_admin_request_eligibility,
        )
        return await check_admin_request_eligibility(request_type)
    except ImportError:
        return None


async def _get_my_admin_requests(
    request_type: str,
    statuses: list,
) -> Optional[list]:
    try:
        from claude_code.services.api.admin_requests import get_my_admin_requests  # type: ignore[import]
        return await get_my_admin_requests(request_type, statuses)
    except ImportError:
        return None


async def _create_admin_request(payload: dict) -> None:
    try:
        from claude_code.services.api.admin_requests import create_admin_request  # type: ignore[import]
        await create_admin_request(payload)
    except ImportError:
        pass


async def _open_browser(url: str) -> bool:
    try:
        from claude_code.utils.browser import open_browser  # type: ignore[import]
        return await open_browser(url)
    except ImportError:
        import webbrowser
        try:
            return webbrowser.open(url)
        except Exception:  # noqa: BLE001
            return False


def _log_error(error: Exception) -> None:
    try:
        from claude_code.utils.log import log_error  # type: ignore[import]
        log_error(error)
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

async def run_extra_usage() -> Dict[str, Any]:
    """
    Determine what to do for /extra-usage and return a result dict.

    Returns
    -------
    dict
        Either ``{"type": "message", "value": <str>}``
        or ``{"type": "browser-opened", "url": <str>, "opened": <bool>}``.
    """
    # Track that the user has visited
    if not _get_global_config().get("hasVisitedExtraUsage"):
        _save_global_config(lambda prev: {**prev, "hasVisitedExtraUsage": True})

    _invalidate_overage_credit_grant_cache()

    subscription_type = _get_subscription_type()
    is_team_or_enterprise = subscription_type in ("team", "enterprise")
    has_billing_access = _has_claude_ai_billing_access()

    if not has_billing_access and is_team_or_enterprise:
        # Check if overage is already unlimited
        extra_usage: Optional[Dict[str, Any]] = None
        try:
            utilization = await _fetch_utilization()
            if utilization:
                extra_usage = utilization.get("extra_usage")
        except Exception as e:  # noqa: BLE001
            _log_error(e)

        if (
            extra_usage is not None
            and extra_usage.get("is_enabled")
            and extra_usage.get("monthly_limit") is None
        ):
            return {
                "type": "message",
                "value": "Your organization already has unlimited extra usage. No request needed.",
            }

        # Check eligibility
        try:
            eligibility = await _check_admin_request_eligibility("limit_increase")
            if eligibility and eligibility.get("is_allowed") is False:
                return {
                    "type": "message",
                    "value": "Please contact your admin to manage extra usage settings.",
                }
        except Exception as e:  # noqa: BLE001
            _log_error(e)

        # Check for existing pending/dismissed requests
        try:
            existing = await _get_my_admin_requests(
                "limit_increase", ["pending", "dismissed"]
            )
            if existing:
                return {
                    "type": "message",
                    "value": "You have already submitted a request for extra usage to your admin.",
                }
        except Exception as e:  # noqa: BLE001
            _log_error(e)

        # Create the request
        try:
            await _create_admin_request(
                {"request_type": "limit_increase", "details": None}
            )
            if extra_usage and extra_usage.get("is_enabled"):
                value = "Request sent to your admin to increase extra usage."
            else:
                value = "Request sent to your admin to enable extra usage."
            return {"type": "message", "value": value}
        except Exception as e:  # noqa: BLE001
            _log_error(e)

        return {
            "type": "message",
            "value": "Please contact your admin to manage extra usage settings.",
        }

    # User has billing access — open the browser
    url = (
        "https://claude.ai/admin-settings/usage"
        if is_team_or_enterprise
        else "https://claude.ai/settings/usage"
    )

    try:
        opened = await _open_browser(url)
        return {"type": "browser-opened", "url": url, "opened": opened}
    except Exception as e:  # noqa: BLE001
        _log_error(e)
        return {
            "type": "message",
            "value": f"Failed to open browser. Please visit {url} to manage extra usage.",
        }
