"""
Exec prompt hook - executes prompt-based hooks using an LLM.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional


async def exec_prompt_hook(
    hook: Dict[str, Any],
    hook_name: str,
    hook_event: str,
    json_input: str,
    signal: Any,
    tool_use_context: Any,
    messages: Optional[List[Any]] = None,
    tool_use_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a prompt-based hook using an LLM."""
    effective_tool_use_id = tool_use_id or f"hook-{uuid.uuid4()}"
    try:
        from .hook_helpers import add_arguments_to_prompt
        from ..log import log_for_debugging

        processed_prompt = add_arguments_to_prompt(hook.get("prompt", ""), json_input)
        log_for_debugging(f"Hooks: Processing prompt hook with prompt: {processed_prompt}")

        # Build messages
        user_message = {"type": "user", "message": {"role": "user", "content": processed_prompt}}
        messages_to_query = (messages or []) + [user_message]

        timeout_ms = hook.get("timeout", 30000)

        # Query the model
        try:
            from ...services.api.claude import query_model_without_streaming
            from ..system_prompt_type import as_system_prompt

            response = await query_model_without_streaming(
                messages=messages_to_query,
                system_prompt=as_system_prompt([
                    "You are evaluating a hook in Claude Code.\n"
                    "Your response must be a JSON object: {\"ok\": true} or {\"ok\": false, \"reason\": \"...\"}"
                ]),
                tools=[],
                model=hook.get("model"),
            )

            from ..messages import extract_text_content
            content = extract_text_content(response) if response else ""

            from ..json import safe_parse_json
            parsed = safe_parse_json(content)

            if parsed and isinstance(parsed, dict):
                ok = parsed.get("ok", True)
                reason = parsed.get("reason", "")
                return {
                    "type": "success",
                    "ok": ok,
                    "output": content,
                    "stdout": content,
                    "stderr": "" if ok else reason,
                    "exitCode": 0 if ok else 2,
                }
        except Exception:
            pass

        # Default: success
        return {"type": "success", "ok": True, "output": "", "stdout": "", "stderr": "", "exitCode": 0}

    except Exception as e:
        return {
            "type": "error",
            "ok": False,
            "output": str(e),
            "stdout": "",
            "stderr": str(e),
            "exitCode": 1,
        }
