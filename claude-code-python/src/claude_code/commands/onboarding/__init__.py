"""onboarding command package stub (ANT-internal)."""
from __future__ import annotations

NAME = "onboarding"
DESCRIPTION = "Restart the onboarding flow (ANT-only)"
TYPE = "local"


async def call(args: str = "", context=None) -> dict:
    return {"type": "text", "value": "/onboarding not yet implemented"}
