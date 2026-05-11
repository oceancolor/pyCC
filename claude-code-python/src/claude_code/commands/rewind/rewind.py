"""
Ported from: commands/rewind/rewind.ts

/rewind command — open the message selector so the user can pick an earlier
conversation point to branch from.  Returns a ``skip`` result so no new
message is appended to the transcript.
"""
from __future__ import annotations

from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Command entry point
# ---------------------------------------------------------------------------

async def call(
    _args: str = "",
    context: Optional[object] = None,
) -> Dict[str, str]:
    """
    Handle the /rewind command.

    Invokes ``context.open_message_selector()`` when available.

    Parameters
    ----------
    _args:
        Unused; the command takes no arguments.
    context:
        ToolUseContext duck-typed object; may expose ``open_message_selector``.

    Returns
    -------
    dict
        ``{"type": "skip"}`` — signals the REPL not to append any message.
    """
    if context is not None:
        open_selector = getattr(context, "open_message_selector", None)
        if callable(open_selector):
            try:
                result = open_selector()
                # Await if the method is a coroutine
                if hasattr(result, "__await__"):
                    import asyncio
                    await asyncio.ensure_future(result)
            except Exception:  # noqa: BLE001
                pass

    return {"type": "skip"}
