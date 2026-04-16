"""Tool use summary generator. Ported from services/toolUseSummary/toolUseSummaryGenerator.ts"""
from __future__ import annotations
import json
from typing import Any, List, Optional, TypedDict

TOOL_USE_SUMMARY_SYSTEM_PROMPT = """Write a short summary label describing what these tool calls accomplished. 
It appears as a single-line row in a mobile app and truncates around 30 characters, so think git-commit-subject, not sentence.
Keep the verb in past tense and the most distinctive noun. Drop articles, connectors, and long location context first.
Examples:
- Searched in auth/
- Fixed NPE in UserService
- Created signup endpoint
- Read config.json
- Ran failing tests"""


class ToolInfo(TypedDict):
    name: str
    input: Any
    output: Any


def _truncate_json(value: Any, max_length: int = 300) -> str:
    try:
        s = json.dumps(value)
        return s if len(s) <= max_length else s[:max_length - 3] + "..."
    except Exception:
        return "[unable to serialize]"


async def generate_tool_use_summary(
    tools: List[ToolInfo],
    signal: Any = None,
    is_non_interactive_session: bool = False,
    last_assistant_text: Optional[str] = None,
) -> Optional[str]:
    """Generate human-readable summary of completed tools using Haiku."""
    if not tools:
        return None
    try:
        from claude_code.services.api.claude import query_haiku
        summaries = "\n\n".join(
            f"Tool: {t['name']}\nInput: {_truncate_json(t['input'])}\nOutput: {_truncate_json(t['output'])}"
            for t in tools)
        prefix = (f"User's intent: {last_assistant_text[:200]}\n\n"
                  if last_assistant_text else "")
        prompt = f"{prefix}Tools completed:\n\n{summaries}\n\nLabel:"
        response = await query_haiku(
            system_prompt=TOOL_USE_SUMMARY_SYSTEM_PROMPT,
            user_prompt=prompt,
            signal=signal,
        )
        return response.strip() or None
    except Exception:
        return None
