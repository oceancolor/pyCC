"""mock_limits command package stub (ANT-internal)."""
from __future__ import annotations

NAME = "mock-limits"
DESCRIPTION = "Simulate rate limiting for testing (ANT-only)"
TYPE = "local"


async def call(args: str = "", context=None) -> dict:
    return {"type": "text", "value": "/mock-limits not yet implemented"}
