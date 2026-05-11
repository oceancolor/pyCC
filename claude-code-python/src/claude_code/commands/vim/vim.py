"""
Ported from: commands/vim/vim.ts

/vim command — toggle the editor mode between vim key bindings and normal
(readline/standard) key bindings.
"""
from __future__ import annotations

from typing import Dict


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


def _log_event(event: str, data: dict) -> None:
    try:
        from claude_code.services.analytics.index import log_event  # type: ignore[import]
        log_event(event, data)
    except (ImportError, Exception):
        pass


# ---------------------------------------------------------------------------
# Command entry point
# ---------------------------------------------------------------------------

async def call() -> Dict[str, str]:
    """
    Toggle vim / normal editor mode.

    Reads the current ``editorMode`` from the global config, flips it
    (normal ↔ vim), persists the change, fires an analytics event, and
    returns a descriptive message.

    Returns
    -------
    dict
        ``{"type": "text", "value": <message>}``
    """
    config = _get_global_config()
    current_mode: str = config.get("editorMode") or "normal"

    # Backward-compat: "emacs" is treated as "normal"
    if current_mode == "emacs":
        current_mode = "normal"

    new_mode = "vim" if current_mode == "normal" else "normal"

    def _update(current: dict) -> dict:
        updated = dict(current)
        updated["editorMode"] = new_mode
        return updated

    _save_global_config(_update)

    _log_event(
        "tengu_editor_mode_changed",
        {"mode": new_mode, "source": "command"},
    )

    if new_mode == "vim":
        extra = (
            "Use Escape key to toggle between INSERT and NORMAL modes."
        )
    else:
        extra = "Using standard (readline) keyboard bindings."

    return {
        "type": "text",
        "value": f"Editor mode set to {new_mode}. {extra}",
    }
