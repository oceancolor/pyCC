"""SendMessageTool package.

Re-exports SendMessageTool and its canonical name constant.

SendMessageTool allows a sub-agent to send a message back to its parent
agent.  It is the primary mechanism for inter-agent communication in
multi-agent (swarm) workflows and is only available to non-root agents.

Ported from: tools/SendMessageTool/ (TypeScript)

Usage::

    from claude_code.tools.send_message_tool import (
        SendMessageTool,
        SEND_MESSAGE_TOOL_NAME,
    )
"""
from __future__ import annotations

from claude_code.tools.send_message_tool.send_message_tool import SendMessageTool
from claude_code.tools.send_message_tool.constants import SEND_MESSAGE_TOOL_NAME

__all__ = [
    "SendMessageTool",
    "SEND_MESSAGE_TOOL_NAME",
]
