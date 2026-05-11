"""
Ported from: commands/install-slack-app/install-slack-app.ts

/install-slack-app command — open the Claude Slack app installation page
in the system browser, track the click, and return a status message.
"""
from __future__ import annotations

from typing import Dict

SLACK_APP_URL = "https://slack.com/marketplace/A08SF47R6P4-claude"


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

def _log_event(event: str, data: dict) -> None:
    try:
        from claude_code.services.analytics.index import log_event  # type: ignore[import]
        log_event(event, data)
    except (ImportError, Exception):
        pass


def _save_global_config(updater) -> None:
    try:
        from claude_code.utils.config import save_global_config  # type: ignore[import]
        save_global_config(updater)
    except (ImportError, Exception):
        pass


def _get_global_config() -> dict:
    try:
        from claude_code.utils.config import get_global_config  # type: ignore[import]
        return get_global_config()
    except ImportError:
        return {}


async def _open_browser(url: str) -> bool:
    """Open *url* in the system browser.  Returns True on success."""
    try:
        from claude_code.utils.browser import open_browser  # type: ignore[import]
        return await open_browser(url)
    except ImportError:
        pass

    # Fallback: use webbrowser from stdlib
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
    Open the Slack app Marketplace page and return a status message.

    Returns
    -------
    dict
        ``{"type": "text", "value": <message>}``
    """
    _log_event("tengu_install_slack_app_clicked", {})

    # Track installation click count in global config
    def _increment_count(current: dict) -> dict:
        updated = dict(current)
        updated["slackAppInstallCount"] = current.get("slackAppInstallCount", 0) + 1
        return updated

    _save_global_config(_increment_count)

    success = await _open_browser(SLACK_APP_URL)

    if success:
        return {
            "type": "text",
            "value": "Opening Slack app installation page in browser\u2026",
        }
    else:
        return {
            "type": "text",
            "value": f"Couldn't open browser. Visit: {SLACK_APP_URL}",
        }
