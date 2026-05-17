"""Sleep tool implementation. Ported from SleepTool."""
from __future__ import annotations

import asyncio
from typing import Any

SLEEP_TOOL_NAME = "Sleep"
DESCRIPTION = "Wait for a specified duration"
SLEEP_TOOL_PROMPT = """Wait for a specified duration. The user can interrupt the sleep at any time.

Use this when the user tells you to sleep or rest, when you have nothing to do, or when you're
waiting for something.

You may receive <tick> prompts — these are periodic check-ins. Look for useful work to do before
sleeping.

You can call this concurrently with other tools — it won't interfere with them.

Prefer this over `Bash(sleep ...)` — it doesn't hold a shell process.

Each wake-up costs an API call, but the prompt cache expires after 5 minutes of inactivity —
balance accordingly."""


class SleepTool:
    """Tool that suspends execution for a given duration.

    Direct Python port of SleepTool/prompt.ts + the implicit SleepTool class.
    Behaves gracefully when cancelled (e.g., user interrupts).
    """

    name = SLEEP_TOOL_NAME
    description = DESCRIPTION
    is_concurrency_safe = True
    is_read_only = True

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "duration_seconds": {
                        "type": "number",
                        "description": "Duration to sleep in seconds",
                    }
                },
                "required": ["duration_seconds"],
            },
        }

    async def call(self, duration_seconds: float = 1.0, **kwargs: Any) -> dict:
        try:
            await asyncio.sleep(duration_seconds)
            return {"result": f"Slept for {duration_seconds} seconds"}
        except asyncio.CancelledError:
            return {"result": "Sleep interrupted"}
