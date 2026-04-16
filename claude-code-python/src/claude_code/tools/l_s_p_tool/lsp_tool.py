"""LSP tool stub. Ported from LSPTool (860 lines → stub)."""
from __future__ import annotations
from typing import Any

LSP_TOOL_NAME = "LSP"
DESCRIPTION = "Query Language Server Protocol for code intelligence (definitions, references, hover)"


class LSPTool:
    name = LSP_TOOL_NAME
    description = DESCRIPTION
    enabled = False  # Requires LSP server setup

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["definition", "references", "hover", "symbols"]},
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "character": {"type": "integer"},
                },
                "required": ["action", "file"]
            }
        }

    async def call(self, action: str = "definition", file: str = "", **kwargs: Any) -> dict:
        return {"error": "LSP tool requires a running language server — not available"}
