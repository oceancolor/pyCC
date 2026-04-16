"""Remote trigger tool stub. Ported from RemoteTriggerTool."""
from __future__ import annotations

REMOTE_TRIGGER_TOOL_NAME = "RemoteTrigger"
DESCRIPTION = "Manage scheduled remote Claude Code agents (triggers) via the claude.ai CCR API."
PROMPT = """Call the claude.ai remote-trigger API. Use this instead of curl — the OAuth token is added automatically in-process and never exposed.

Actions:
- list: GET /v1/code/triggers
- get: GET /v1/code/triggers/{trigger_id}
- create: POST /v1/code/triggers (requires body)
- update: POST /v1/code/triggers/{trigger_id} (requires body, partial update)
- run: POST /v1/code/triggers/{trigger_id}/run

The response is the raw JSON from the API."""


class RemoteTriggerTool:
    name = REMOTE_TRIGGER_TOOL_NAME
    description = DESCRIPTION
    enabled = False  # Requires claude.ai OAuth context

    async def call(self, action: str = "list", trigger_id: str = None, body: dict = None, **kwargs):
        return {"error": "RemoteTrigger not available in this environment"}
