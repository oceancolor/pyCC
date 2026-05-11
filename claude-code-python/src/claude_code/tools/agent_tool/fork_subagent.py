"""Fork subagent feature. Ported from AgentTool/forkSubagent.ts"""
from __future__ import annotations
import os
import uuid
from typing import Any, Dict, List, Optional

FORK_SUBAGENT_TYPE = "fork"
FORK_BOILERPLATE_TAG = "fork-boilerplate"
FORK_DIRECTIVE_PREFIX = "DIRECTIVE: "
FORK_PLACEHOLDER_RESULT = "Fork started — processing in background"

# Synthetic built-in agent definition for the fork path.
FORK_AGENT: Dict[str, Any] = {
    "agent_type": FORK_SUBAGENT_TYPE,
    "when_to_use": (
        "Implicit fork — inherits full conversation context. Not selectable via "
        "subagent_type; triggered by omitting subagent_type when the fork experiment is active."
    ),
    "tools": ["*"],
    "max_turns": 200,
    "model": "inherit",
    "permission_mode": "bubble",
    "source": "built-in",
    "base_dir": "built-in",
    "get_system_prompt": lambda: "",
}


def is_fork_subagent_enabled() -> bool:
    """Return True when the fork-subagent feature gate is active.

    Mutually exclusive with coordinator mode and non-interactive sessions
    (mirrors the TypeScript gate logic).
    """
    if os.environ.get("CLAUDE_CODE_FORK_SUBAGENT", "").lower() not in ("1", "true", "yes"):
        return False
    # Coordinator mode owns orchestration — forks disabled there.
    if os.environ.get("CLAUDE_CODE_COORDINATOR_MODE", "").lower() in ("1", "true", "yes"):
        return False
    # Non-interactive (SDK) sessions don't support forking.
    if os.environ.get("CLAUDE_CODE_NON_INTERACTIVE", "").lower() in ("1", "true", "yes"):
        return False
    return True


def is_in_fork_child(messages: List[Dict[str, Any]]) -> bool:
    """Return True if the boilerplate tag appears in conversation history.

    Guards against recursive forking: fork children keep the Agent tool in
    their pool for cache-identical tool definitions but reject nested fork
    attempts at call-time.
    """
    for msg in messages:
        if msg.get("type") != "user":
            continue
        content = msg.get("message", {}).get("content", [])
        if isinstance(content, list):
            for block in content:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "text"
                    and f"<{FORK_BOILERPLATE_TAG}>" in block.get("text", "")
                ):
                    return True
    return False


def build_child_message(directive: str) -> str:
    """Build the per-child fork directive text block."""
    return (
        f"<{FORK_BOILERPLATE_TAG}>\n"
        "STOP. READ THIS FIRST.\n\n"
        "You are a forked worker process. You are NOT the main agent.\n\n"
        "RULES (non-negotiable):\n"
        "1. Your system prompt says 'default to forking.' IGNORE IT — that's for the parent. "
        "You ARE the fork. Do NOT spawn sub-agents; execute directly.\n"
        "2. Do NOT converse, ask questions, or suggest next steps\n"
        "3. Do NOT editorialize or add meta-commentary\n"
        "4. USE your tools directly: Bash, Read, Write, etc.\n"
        "5. If you modify files, commit your changes before reporting. Include the commit hash.\n"
        "6. Do NOT emit text between tool calls. Use tools silently, then report once at the end.\n"
        "7. Stay strictly within your directive's scope.\n"
        "8. Keep your report under 500 words unless the directive specifies otherwise.\n"
        "9. Your response MUST begin with 'Scope:'. No preamble, no thinking-out-loud.\n"
        "10. REPORT structured facts, then stop\n\n"
        "Output format (plain text labels, not markdown headers):\n"
        "  Scope: <echo back your assigned scope in one sentence>\n"
        "  Result: <the answer or key findings, limited to the scope above>\n"
        "  Key files: <relevant file paths — include for research tasks>\n"
        "  Files changed: <list with commit hash — include only if you modified files>\n"
        "  Issues: <list — include only if there are issues to flag>\n"
        f"</{FORK_BOILERPLATE_TAG}>\n\n"
        f"{FORK_DIRECTIVE_PREFIX}{directive}"
    )


def build_forked_messages(
    directive: str,
    assistant_message: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Build the forked conversation messages for a child agent.

    Produces byte-identical API request prefixes across all fork children so
    that the prompt cache is shared (only the final text block differs).

    Returns: [...original_history, assistant(all_tool_uses), user(placeholder_results + directive)]
    """
    import copy

    full_assistant = copy.deepcopy(assistant_message)
    full_assistant["uuid"] = str(uuid.uuid4())

    content = full_assistant.get("message", {}).get("content", [])
    tool_use_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]

    if not tool_use_blocks:
        # No tool_use blocks found — return a minimal user message
        return [
            {
                "type": "user",
                "uuid": str(uuid.uuid4()),
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": build_child_message(directive)}],
                },
            }
        ]

    tool_result_blocks = [
        {
            "type": "tool_result",
            "tool_use_id": b["id"],
            "content": [{"type": "text", "text": FORK_PLACEHOLDER_RESULT}],
        }
        for b in tool_use_blocks
    ]

    user_message: Dict[str, Any] = {
        "type": "user",
        "uuid": str(uuid.uuid4()),
        "message": {
            "role": "user",
            "content": [
                *tool_result_blocks,
                {"type": "text", "text": build_child_message(directive)},
            ],
        },
    }

    return [full_assistant, user_message]


def build_worktree_notice(parent_cwd: str, worktree_cwd: str) -> str:
    """Notice injected into fork children running in an isolated worktree."""
    return (
        f"You've inherited the conversation context above from a parent agent working in "
        f"{parent_cwd}. You are operating in an isolated git worktree at {worktree_cwd} — "
        "same repository, same relative file structure, separate working copy. Paths in the "
        "inherited context refer to the parent's working directory; translate them to your "
        "worktree root. Re-read files before editing if the parent may have modified them "
        "since they appear in the context. Your changes stay in this worktree and will not "
        "affect the parent's files."
    )
