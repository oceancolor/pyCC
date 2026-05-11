"""
Ported from: commands/thinkback-play/thinkback-play.ts

/thinkback-play command — replay the last thinkback animation from an
installed thinkback plugin.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

_INTERNAL_MARKETPLACE_NAME = "claude-code-marketplace"
_OFFICIAL_MARKETPLACE_NAME = "claude-code"  # fallback; real value from officialMarketplace.ts
_SKILL_NAME = "thinkback"


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

def _is_ant_user() -> bool:
    return os.environ.get("USER_TYPE") == "ant"


def _get_official_marketplace_name() -> str:
    try:
        from claude_code.utils.plugins.official_marketplace import (  # type: ignore[import]
            OFFICIAL_MARKETPLACE_NAME,
        )
        return OFFICIAL_MARKETPLACE_NAME
    except ImportError:
        return _OFFICIAL_MARKETPLACE_NAME


def _get_plugin_id() -> str:
    marketplace = (
        _INTERNAL_MARKETPLACE_NAME
        if _is_ant_user()
        else _get_official_marketplace_name()
    )
    return f"thinkback@{marketplace}"


def _load_installed_plugins_v2() -> Dict[str, Any]:
    try:
        from claude_code.utils.plugins.installed_plugins_manager import (  # type: ignore[import]
            load_installed_plugins_v2,
        )
        return load_installed_plugins_v2()
    except ImportError:
        return {"plugins": {}}


async def _play_animation(skill_dir: str) -> Dict[str, str]:
    try:
        from claude_code.commands.thinkback.thinkback import play_animation  # type: ignore[import]
        return await play_animation(skill_dir)
    except (ImportError, Exception) as exc:  # noqa: BLE001
        return {"message": f"Animation playback error: {exc}"}


# ---------------------------------------------------------------------------
# Command entry point
# ---------------------------------------------------------------------------

async def call() -> Dict[str, str]:
    """
    Replay the thinkback animation from the installed thinkback plugin.

    Returns
    -------
    dict
        ``{"type": "text", "value": <message>}``
    """
    v2_data = _load_installed_plugins_v2()
    plugin_id = _get_plugin_id()
    installations: Optional[List[Dict[str, Any]]] = v2_data.get("plugins", {}).get(
        plugin_id
    )

    if not installations:
        return {
            "type": "text",
            "value": (
                "Thinkback plugin not installed. "
                "Run /think-back first to install it."
            ),
        }

    first_install = installations[0]
    if not isinstance(first_install, dict) or not first_install.get("installPath"):
        return {
            "type": "text",
            "value": "Thinkback plugin installation path not found.",
        }

    skill_dir = os.path.join(
        first_install["installPath"], "skills", _SKILL_NAME
    )
    result = await _play_animation(skill_dir)
    return {"type": "text", "value": result.get("message", "")}
