"""
Ported from: commands/stickers/stickers.ts

/stickers command — open the Claude Code sticker page in the system browser.
"""
from __future__ import annotations

from typing import Dict

STICKER_URL = "https://www.stickermule.com/claudecode"


# ---------------------------------------------------------------------------
# Stub helper
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Command entry point
# ---------------------------------------------------------------------------

async def call() -> Dict[str, str]:
    """
    Open the sticker page and return a status message.

    Returns
    -------
    dict
        ``{"type": "text", "value": <message>}``
    """
    success = await _open_browser(STICKER_URL)

    if success:
        return {"type": "text", "value": "Opening sticker page in browser\u2026"}
    else:
        return {
            "type": "text",
            "value": f"Failed to open browser. Visit: {STICKER_URL}",
        }
