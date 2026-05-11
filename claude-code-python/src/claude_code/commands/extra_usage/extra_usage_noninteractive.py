"""
Ported from: commands/extra-usage/extra-usage-noninteractive.ts

Non-interactive entry point for the /extra-usage command.
Delegates to extra_usage_core.run_extra_usage() and converts the result
to a plain text message.
"""
from __future__ import annotations

from typing import Dict


async def call() -> Dict[str, str]:
    """
    Handle /extra-usage in a non-interactive (headless) context.

    Returns
    -------
    dict
        ``{"type": "text", "value": <message>}``
    """
    from .extra_usage_core import run_extra_usage  # local import to avoid circulars

    result = await run_extra_usage()

    if result.get("type") == "message":
        return {"type": "text", "value": result["value"]}

    url: str = result.get("url", "")
    opened: bool = result.get("opened", False)
    if opened:
        return {
            "type": "text",
            "value": (
                f"Browser opened to manage extra usage. "
                f"If it didn't open, visit: {url}"
            ),
        }
    return {
        "type": "text",
        "value": f"Please visit {url} to manage extra usage.",
    }
