"""Brief tool (proactive messaging). Ported from BriefTool."""
from __future__ import annotations
from typing import Any, List, Optional
import datetime

BRIEF_TOOL_NAME = "Brief"
LEGACY_BRIEF_TOOL_NAME = "NotifyUser"
DESCRIPTION = "Send a message to the user — use for task completion, blockers, or proactive updates"


class BriefTool:
    name = BRIEF_TOOL_NAME
    description = DESCRIPTION

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Message for the user (markdown supported)"},
                    "attachments": {"type": "array", "items": {"type": "string"},
                                    "description": "Optional file paths to attach"},
                    "status": {"type": "string", "enum": ["normal", "proactive"],
                               "description": "'proactive' for unsolicited updates, 'normal' for replies"},
                },
                "required": ["message", "status"]
            }
        }

    async def call(self, message: str, status: str = "normal",
                   attachments: Optional[List[str]] = None, **kwargs: Any) -> dict:
        return {
            "message": message,
            "status": status,
            "attachments": attachments or [],
            "sentAt": datetime.datetime.utcnow().isoformat() + "Z",
        }
