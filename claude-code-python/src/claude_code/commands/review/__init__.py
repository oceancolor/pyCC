"""Review command package stub."""
from __future__ import annotations
from typing import Literal
from dataclasses import dataclass

NAME = "review"
DESCRIPTION = "Review code changes"
TYPE: Literal["local-jsx"] = "local-jsx"


@dataclass
class ReviewCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION

    async def call(self, args: str = "", context=None) -> dict:
        return {"type": "text", "value": "/review not yet implemented"}


default = ReviewCommand()
