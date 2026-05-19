"""SendMessageTool constants.

Ported from: tools/SendMessageTool/constants.ts

Defines the canonical API-level tool name used to identify the
SendMessage tool in tool-use messages and permission rules.

SendMessage is the primary inter-agent communication mechanism in multi-
agent (swarm) workflows.  A sub-agent calls ``SendMessage`` to return a
result or status update to its parent.  The tool is only available to
non-root agents; the root agent uses ``AgentTool`` to spawn children and
receives their messages implicitly when they finish.

See also
--------
``claude_code.tools.send_message_tool.send_message_tool`` : Implementation.
``claude_code.tools.agent_tool.constants`` : Related agent tool names.
"""
from __future__ import annotations

#: The API-level tool name used to identify the SendMessage tool.
SEND_MESSAGE_TOOL_NAME: str = "SendMessage"

__all__ = ["SEND_MESSAGE_TOOL_NAME"]
