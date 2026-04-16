"""
Telemetry attributes - Python port of telemetryAttributes.ts

Provides getTelemetryAttributes() to build OpenTelemetry-style attribute
dicts for metrics/tracing, respecting env-var cardinality toggles.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Cardinality defaults
# ---------------------------------------------------------------------------
_CARDINALITY_DEFAULTS: Dict[str, bool] = {
    "OTEL_METRICS_INCLUDE_SESSION_ID": True,
    "OTEL_METRICS_INCLUDE_VERSION": False,
    "OTEL_METRICS_INCLUDE_ACCOUNT_UUID": True,
}

# App version (populated at build time; falls back to "dev")
APP_VERSION: str = os.environ.get("CLAUDE_CODE_VERSION", "dev")


def _is_env_truthy(value: str) -> bool:
    """Return True for '1', 'true', 'yes' (case-insensitive)."""
    return value.strip().lower() in {"1", "true", "yes"}


def _should_include_attribute(env_var: str) -> bool:
    default = _CARDINALITY_DEFAULTS.get(env_var, False)
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    return _is_env_truthy(raw)


def get_telemetry_attributes(
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    oauth_account: Optional[Dict[str, Any]] = None,
    terminal: Optional[str] = None,
) -> Dict[str, Any]:
    """Build telemetry attribute dict.

    Parameters mirror the TS getOauthAccountInfo / getSessionId / envDynamic
    call-sites; callers pass resolved values directly for testability.
    """
    # Lazy import to avoid circular deps when used standalone
    try:
        if user_id is None:
            from claude_code.utils.config import get_or_create_user_id  # type: ignore
            user_id = get_or_create_user_id()
    except Exception:
        user_id = user_id or "unknown"

    attributes: Dict[str, Any] = {"user.id": user_id}

    if session_id and _should_include_attribute("OTEL_METRICS_INCLUDE_SESSION_ID"):
        attributes["session.id"] = session_id

    if _should_include_attribute("OTEL_METRICS_INCLUDE_VERSION"):
        attributes["app.version"] = APP_VERSION

    if oauth_account:
        org_id = oauth_account.get("organization_uuid") or oauth_account.get("organizationUuid")
        email = oauth_account.get("email_address") or oauth_account.get("emailAddress")
        account_uuid = oauth_account.get("account_uuid") or oauth_account.get("accountUuid")

        if org_id:
            attributes["organization.id"] = org_id
        if email:
            attributes["user.email"] = email
        if account_uuid and _should_include_attribute("OTEL_METRICS_INCLUDE_ACCOUNT_UUID"):
            attributes["user.account_uuid"] = account_uuid
            tagged = os.environ.get("CLAUDE_CODE_ACCOUNT_TAGGED_ID") or f"user_{account_uuid}"
            attributes["user.account_id"] = tagged

    if terminal:
        attributes["terminal.type"] = terminal

    return attributes
