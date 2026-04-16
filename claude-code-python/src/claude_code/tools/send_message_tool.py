# Source: tools/SendMessageTool/SendMessageTool.ts
"""SendMessage tool: send messages between agent teammates (swarm protocol)."""
from __future__ import annotations

from typing import Any

from claude_code.tool import Tool, ToolInputJSONSchema, ToolUseContext

SEND_MESSAGE_TOOL_NAME = "SendMessage"


class SendMessageTool(Tool):
    """Tool for sending messages between agent teammates."""

    name = SEND_MESSAGE_TOOL_NAME
    search_hint = "send messages to agent teammates (swarm protocol)"

    async def description(self) -> str:
        return (
            "Send a message to another agent teammate. "
            "Supports plain text messages, broadcast to all teammates (*), "
            "and structured messages (shutdown requests/responses, plan approvals)."
        )

    async def prompt(self) -> str:
        return (
            "Use this tool to communicate with other agents in a multi-agent swarm. "
            "For plain text: provide 'to' (recipient name or '*' for broadcast), "
            "'message' (string), and 'summary' (5-10 word preview). "
            "For structured messages: provide 'to' and a message object with 'type'."
        )

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": (
                        "Recipient: teammate name, or \"*\" for broadcast to all teammates"
                    ),
                },
                "summary": {
                    "type": "string",
                    "description": (
                        "A 5-10 word summary shown as a preview in the UI "
                        "(required when message is a string)"
                    ),
                },
                "message": {
                    "oneOf": [
                        {"type": "string", "description": "Plain text message content"},
                        {
                            "type": "object",
                            "description": "Structured message (shutdown/plan approval)",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": [
                                        "shutdown_request",
                                        "shutdown_response",
                                        "plan_approval_response",
                                    ],
                                },
                            },
                            "required": ["type"],
                        },
                    ]
                },
            },
            "required": ["to", "message"],
        }

    async def call(self, input_data: dict[str, Any], context: ToolUseContext) -> Any:
        """Execute the SendMessage tool."""
        to = input_data.get("to", "").strip()
        message = input_data.get("message", "")
        summary = input_data.get("summary")

        if not to:
            return {"success": False, "message": "to must not be empty"}

        if isinstance(message, str):
            if to == "*":
                return {
                    "success": True,
                    "message": f"Broadcast queued (stub): {summary or message[:50]}",
                    "recipients": [],
                }
            return {
                "success": True,
                "message": f"Message queued for {to} (stub): {summary or message[:50]}",
                "routing": {
                    "sender": "agent",
                    "target": to,
                    "summary": summary,
                    "content": message,
                },
            }

        if isinstance(message, dict):
            msg_type = message.get("type")
            if msg_type == "shutdown_request":
                return {
                    "success": True,
                    "message": f"Shutdown request sent to {to} (stub)",
                    "request_id": "stub-request-id",
                    "target": to,
                }
            elif msg_type == "shutdown_response":
                approve = message.get("approve", False)
                return {
                    "success": True,
                    "message": f"Shutdown {'approved' if approve else 'rejected'} (stub)",
                    "request_id": message.get("request_id"),
                }
            elif msg_type == "plan_approval_response":
                approve = message.get("approve", False)
                return {
                    "success": True,
                    "message": f"Plan {'approved' if approve else 'rejected'} for {to} (stub)",
                    "request_id": message.get("request_id"),
                }

        return {"success": False, "message": f"Unknown message type: {type(message)}"}
