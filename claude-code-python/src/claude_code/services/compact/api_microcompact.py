"""API MicroCompact service. Ported from services/compact/apiMicrocompact.ts"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

# Default token thresholds matching client-side microcompact values
_DEFAULT_MAX_INPUT_TOKENS = 180_000
_DEFAULT_TARGET_INPUT_TOKENS = 40_000

# Tools whose results can be cleared
_TOOLS_CLEARABLE_RESULTS = [
    "Bash", "bash", "BashTool", "Glob", "Grep",
    "Read", "WebFetch", "WebSearch",
]
_TOOLS_CLEARABLE_USES = ["Edit", "Write", "NotebookEdit"]


async def api_micro_compact(
    messages: List[Dict[str, Any]],
    model: str = "",
    max_input_tokens: int = _DEFAULT_MAX_INPUT_TOKENS,
    target_input_tokens: int = _DEFAULT_TARGET_INPUT_TOKENS,
) -> Optional[List[Dict[str, Any]]]:
    """Apply API-level micro-compaction by clearing tool results/uses to reduce token count.

    Returns compacted messages, or None if compaction is not needed/possible.
    """
    if not messages:
        return None

    # Estimate token count from message content length
    total_chars = sum(
        len(str(m.get("content", ""))) for m in messages
    )
    estimated_tokens = total_chars // 4  # rough approximation

    if estimated_tokens <= max_input_tokens:
        return None  # No compaction needed

    compacted = []
    for msg in messages:
        msg_copy = dict(msg)
        content = msg_copy.get("content", "")

        if isinstance(content, list):
            new_content = []
            for block in content:
                if isinstance(block, dict):
                    block_type = block.get("type", "")
                    tool_name = block.get("name", "") or block.get("tool_name", "")

                    if block_type == "tool_result" and tool_name in _TOOLS_CLEARABLE_RESULTS:
                        block = {**block, "content": "[cleared for compaction]"}
                    elif block_type == "tool_use" and tool_name in _TOOLS_CLEARABLE_USES:
                        block = {**block, "input": {}}
                new_content.append(block)
            msg_copy["content"] = new_content

        compacted.append(msg_copy)

    return compacted
