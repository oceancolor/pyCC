"""
/logout command.
Ported from commands/logout/index.ts + commands/logout/logout.ts
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

log = logging.getLogger(__name__)

COMMAND_NAME = "logout"


async def call(_args: str = "", **_kwargs: Any) -> Dict[str, Any]:
    """Sign out from the current Anthropic account session."""
    try:
        from claude_code.utils.auth import logout  # type: ignore
        await logout()
        return {"type": "text", "value": "Signed out successfully."}
    except ImportError:
        log.debug("Auth module not available for logout")
        return {"type": "text", "value": "Logout unavailable in this environment."}
    except Exception as exc:
        log.error("Logout failed: %s", exc)
        return {"type": "error", "value": f"Logout failed: {exc}"}


def _is_enabled() -> bool:
    env = os.environ.get("DISABLE_LOGOUT_COMMAND", "")
    return env.lower() not in ("1", "true", "yes")


COMMAND: Dict[str, Any] = {
    "type": "local",
    "name": COMMAND_NAME,
    "description": "Sign out from your Anthropic account",
    "is_enabled": _is_enabled,
    "supports_non_interactive": False,
    "load": lambda: {"call": call},
}
