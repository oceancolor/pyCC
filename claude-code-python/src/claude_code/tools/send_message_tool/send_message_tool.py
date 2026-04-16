"""
SendMessageTool — send a message to a teammate/agent in swarm mode.
Ported from SendMessageTool/SendMessageTool.ts.
"""
from __future__ import annotations
from typing import Any, Dict

SEND_MESSAGE_TOOL_NAME = "SendMessage"


class SendMessageTool:
    name = SEND_MESSAGE_TOOL_NAME
    description = "Send a message to a teammate agent."
    is_read_only = False

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "recipient": {"type": "string"},
                "message_type": {"type": "string"},
            },
            "required": ["message"],
        }

    async def call(self, input: Dict[str, Any], context: Any = None) -> dict:
        message = input.get("message", "")
        recipient = input.get("recipient", "team-lead")
        # In swarm mode: write to mailbox. Stub: just ack.
        return {"text": f"Message sent to {recipient}: {message[:100]}"}
