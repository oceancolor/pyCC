"""model command package stub."""
from __future__ import annotations
from typing import Literal
from dataclasses import dataclass

NAME = "model"
DESCRIPTION = "Switch the AI model"
TYPE: Literal["local-jsx"] = "local-jsx"


@dataclass
class ModelCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION

    async def call(self, args: str = "", context=None) -> dict:
        return {"type": "text", "value": "/model not yet implemented"}


default = ModelCommand()
