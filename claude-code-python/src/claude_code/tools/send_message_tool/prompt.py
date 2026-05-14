"""SendMessageTool prompt. Ported from SendMessageTool/prompt.ts"""
from __future__ import annotations

DESCRIPTION = "Send a message to another agent"


def get_prompt() -> str:
    return """Send a message to another agent in the same team or a remote session.

## Usage

```json
{"to": "<agent-id>", "message": "your message here"}
```

## Target formats

| Target | Description |
|--------|-------------|
| `"<agent-id>"` | Local agent in the same team session |
| `"uds:/path/to.sock"` | Local Claude session's socket (same machine; use ListPeers) |
| `"bridge:session_..."` | Remote Control peer session (cross-machine; use ListPeers) |

A listed peer is alive and will process your message — no "busy" state; messages enqueue and drain at the receiver's next tool round. Your message arrives wrapped as `<cross-session-message from="...">`. **To reply to an incoming message, copy its `from` attribute as your `to`.**

## When to Use

- To coordinate with teammates in a multi-agent swarm
- To delegate a subtask to a specialized agent
- To receive results from or send updates to another agent
"""
