"""
Memory extraction service.
Ported from services/extractMemories/extractMemories.ts (615 lines)

Extracts durable memories from the current session transcript and writes
them to the auto-memory directory (~/.claude/projects/<path>/memory/).

It runs once at the end of each complete query loop (when the model
produces a final response with no tool calls) via handleStopHooks.

Uses the forked agent pattern — a perfect fork of the main conversation
that shares the parent's prompt cache.

State is closure-scoped inside init_extract_memories() rather than
module-level, following the same pattern as the TS original.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Callable, Optional

from .prompts import build_extract_auto_only_prompt, build_extract_combined_prompt

logger = logging.getLogger(__name__)

# Tool name constants
FILE_EDIT_TOOL_NAME = "Edit"
FILE_READ_TOOL_NAME = "Read"
FILE_WRITE_TOOL_NAME = "Write"
GLOB_TOOL_NAME = "Glob"
GREP_TOOL_NAME = "Grep"
BASH_TOOL_NAME = "Bash"
REPL_TOOL_NAME = "REPL"

ENTRYPOINT_NAME = "MEMORY.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_auto_mem_path() -> str:
    return os.environ.get(
        "CLAUDE_CODE_AUTO_MEM_PATH",
        str(Path.home() / ".claude" / "memory"),
    )


def _is_auto_memory_enabled() -> bool:
    return os.environ.get("CLAUDE_CODE_AUTO_MEMORY", "").lower() in ("1", "true")


def _is_auto_mem_path(file_path: str) -> bool:
    """Check if a file_path is inside the auto-memory directory."""
    mem_path = Path(_get_auto_mem_path()).resolve()
    try:
        Path(file_path).resolve().relative_to(mem_path)
        return True
    except ValueError:
        return False


def _is_model_visible_message(message: dict) -> bool:
    """Returns True if a message is visible to the model (user or assistant)."""
    return message.get("type") in ("user", "assistant")


def _count_model_visible_messages_since(
    messages: list[dict],
    since_uuid: Optional[str],
) -> int:
    """Count model-visible messages since a given UUID cursor."""
    if since_uuid is None:
        return sum(1 for m in messages if _is_model_visible_message(m))

    found_start = False
    count = 0
    for message in messages:
        if not found_start:
            if message.get("uuid") == since_uuid:
                found_start = True
            continue
        if _is_model_visible_message(message):
            count += 1

    # If sinceUuid was not found, fall back to counting all
    if not found_start:
        return sum(1 for m in messages if _is_model_visible_message(m))

    return count


def _get_written_file_path(block: dict) -> Optional[str]:
    """Extract file_path from a tool_use block, if it's an Edit or Write block."""
    if block.get("type") != "tool_use":
        return None
    if block.get("name") not in (FILE_EDIT_TOOL_NAME, FILE_WRITE_TOOL_NAME):
        return None
    inp = block.get("input")
    if not isinstance(inp, dict):
        return None
    fp = inp.get("file_path")
    return fp if isinstance(fp, str) else None


def _has_memory_writes_since(
    messages: list[dict],
    since_uuid: Optional[str],
) -> bool:
    """
    Returns True if any assistant message after the cursor UUID contains a
    Write/Edit tool_use block targeting an auto-memory path.
    """
    found_start = since_uuid is None
    for message in messages:
        if not found_start:
            if message.get("uuid") == since_uuid:
                found_start = True
            continue
        if message.get("type") != "assistant":
            continue
        content = message.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            fp = _get_written_file_path(block)
            if fp and _is_auto_mem_path(fp):
                return True
    return False


def _extract_written_paths(agent_messages: list[dict]) -> list[str]:
    """Extract unique file paths written by the agent."""
    paths: list[str] = []
    seen: set[str] = set()
    for message in agent_messages:
        if message.get("type") != "assistant":
            continue
        content = message.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            fp = _get_written_file_path(block)
            if fp and fp not in seen:
                seen.add(fp)
                paths.append(fp)
    return paths


# ---------------------------------------------------------------------------
# Tool permission helper
# ---------------------------------------------------------------------------

async def create_auto_mem_can_use_tool(memory_dir: str) -> Callable:
    """
    Creates a canUseTool function that:
    - Allows Read/Grep/Glob unrestricted
    - Allows read-only Bash commands
    - Allows Edit/Write only for paths within the auto-memory directory
    Shared by extractMemories and autoDream.
    """
    async def can_use_tool(tool: Any, input_data: dict) -> dict:
        tool_name = getattr(tool, "name", None) or tool.get("name", "")

        if tool_name == REPL_TOOL_NAME:
            return {"behavior": "allow", "updatedInput": input_data}

        if tool_name in (FILE_READ_TOOL_NAME, GREP_TOOL_NAME, GLOB_TOOL_NAME):
            return {"behavior": "allow", "updatedInput": input_data}

        if tool_name == BASH_TOOL_NAME:
            # In a real impl, check tool.isReadOnly(parsed_data)
            # Here: allow if the command looks read-only
            command = input_data.get("command", "")
            read_only_cmds = ("ls", "find", "grep", "cat", "stat", "wc", "head", "tail", "echo", "pwd")
            first_word = command.strip().split()[0] if command.strip() else ""
            if first_word in read_only_cmds:
                return {"behavior": "allow", "updatedInput": input_data}
            reason = "Only read-only shell commands are permitted in this context"
            logger.debug("[autoMem] denied %s: %s", tool_name, reason)
            return {
                "behavior": "deny",
                "message": reason,
                "decisionReason": {"type": "other", "reason": reason},
            }

        if tool_name in (FILE_EDIT_TOOL_NAME, FILE_WRITE_TOOL_NAME):
            file_path = input_data.get("file_path", "")
            if isinstance(file_path, str) and _is_auto_mem_path(file_path):
                return {"behavior": "allow", "updatedInput": input_data}

        reason = (
            f"only {FILE_READ_TOOL_NAME}, {GREP_TOOL_NAME}, {GLOB_TOOL_NAME}, "
            f"read-only {BASH_TOOL_NAME}, and {FILE_EDIT_TOOL_NAME}/{FILE_WRITE_TOOL_NAME} "
            f"within {memory_dir} are allowed"
        )
        logger.debug("[autoMem] denied %s: %s", tool_name, reason)
        return {
            "behavior": "deny",
            "message": reason,
            "decisionReason": {"type": "other", "reason": reason},
        }

    return can_use_tool


# ---------------------------------------------------------------------------
# Initialization & closure-scoped state
# ---------------------------------------------------------------------------

AppendSystemMessageFn = Callable[[dict], None]

_extractor: Optional[Callable] = None
_drainer: Callable = lambda timeout_ms=60_000: asyncio.sleep(0)


def init_extract_memories() -> None:
    """
    Initialize the memory extraction system.
    Creates a fresh closure capturing all mutable state (cursor position,
    overlap guard, pending context). Call once at startup, or per-test.
    """
    # Closure-scoped mutable state via list cells
    in_flight_extractions: set = set()
    last_memory_message_uuid: list[Optional[str]] = [None]
    has_logged_gate_failure: list[bool] = [False]
    in_progress: list[bool] = [False]
    turns_since_last_extraction: list[int] = [0]
    pending_context: list[Optional[dict]] = [None]

    async def run_extraction(
        context: dict,
        append_system_message: Optional[AppendSystemMessageFn] = None,
        is_trailing_run: bool = False,
    ) -> None:
        messages = context.get("messages", [])
        memory_dir = _get_auto_mem_path()
        new_message_count = _count_model_visible_messages_since(
            messages, last_memory_message_uuid[0]
        )

        # Mutual exclusion: skip if main agent already wrote memories
        if _has_memory_writes_since(messages, last_memory_message_uuid[0]):
            logger.debug(
                "[extractMemories] skipping — conversation already wrote to memory files"
            )
            last_msg = messages[-1] if messages else None
            if last_msg and last_msg.get("uuid"):
                last_memory_message_uuid[0] = last_msg["uuid"]
            return

        team_memory_enabled = False  # Simplified; real impl checks feature flag

        # Throttle: skip if not enough turns have passed (simplified)
        if not is_trailing_run:
            turns_since_last_extraction[0] += 1
            # Default throttle = 1 (every turn)
            throttle = int(os.environ.get("CLAUDE_CODE_MEM_EXTRACT_THROTTLE", "1"))
            if turns_since_last_extraction[0] < throttle:
                return
        turns_since_last_extraction[0] = 0

        in_progress[0] = True
        start_time = asyncio.get_event_loop().time()
        try:
            logger.debug(
                "[extractMemories] starting — %d new messages, memoryDir=%s",
                new_message_count,
                memory_dir,
            )

            # In real impl: scan existing memory files
            existing_memories = ""

            if team_memory_enabled:
                user_prompt = build_extract_combined_prompt(
                    new_message_count,
                    existing_memories,
                    team_memory_enabled=True,
                )
            else:
                user_prompt = build_extract_auto_only_prompt(
                    new_message_count,
                    existing_memories,
                )

            # In real impl: call runForkedAgent with user_prompt
            # Here: log and simulate completion
            logger.debug(
                "[extractMemories] would run forked agent (%d chars prompt)",
                len(user_prompt),
            )
            result_messages: list[dict] = []

            # Advance cursor after successful run
            last_msg = messages[-1] if messages else None
            if last_msg and last_msg.get("uuid"):
                last_memory_message_uuid[0] = last_msg["uuid"]

            written_paths = _extract_written_paths(result_messages)
            memory_paths = [
                p for p in written_paths if os.path.basename(p) != ENTRYPOINT_NAME
            ]

            if memory_paths and append_system_message:
                append_system_message({
                    "type": "system",
                    "content": f"Saved {len(memory_paths)} memory file(s): {', '.join(memory_paths)}",
                })

            logger.debug(
                "[extractMemories] finished — %d files written",
                len(written_paths),
            )

        except Exception as exc:
            logger.debug("[extractMemories] error: %s", exc)
        finally:
            in_progress[0] = False
            trailing = pending_context[0]
            pending_context[0] = None
            if trailing:
                logger.debug(
                    "[extractMemories] running trailing extraction for stashed context"
                )
                await run_extraction(
                    trailing["context"],
                    trailing.get("append_system_message"),
                    is_trailing_run=True,
                )

    async def execute_extract_memories_impl(
        context: dict,
        append_system_message: Optional[AppendSystemMessageFn] = None,
    ) -> None:
        # Only run for the main agent, not subagents
        if context.get("toolUseContext", {}).get("agentId"):
            return

        # Feature gate
        if not os.environ.get("CLAUDE_CODE_EXTRACT_MEMORIES", "").lower() in ("1", "true"):
            if not has_logged_gate_failure[0]:
                has_logged_gate_failure[0] = True
            return

        if not _is_auto_memory_enabled():
            return

        if os.environ.get("CLAUDE_CODE_REMOTE_MODE", "").lower() in ("1", "true"):
            return

        if in_progress[0]:
            logger.debug(
                "[extractMemories] extraction in progress — stashing for trailing run"
            )
            pending_context[0] = {
                "context": context,
                "append_system_message": append_system_message,
            }
            return

        await run_extraction(context, append_system_message)

    async def extractor_fn(
        context: dict,
        append_system_message: Optional[AppendSystemMessageFn] = None,
    ) -> None:
        p = asyncio.ensure_future(
            execute_extract_memories_impl(context, append_system_message)
        )
        in_flight_extractions.add(p)
        try:
            await p
        finally:
            in_flight_extractions.discard(p)

    async def drainer_fn(timeout_ms: float = 60_000) -> None:
        if not in_flight_extractions:
            return
        try:
            await asyncio.wait_for(
                asyncio.gather(*in_flight_extractions, return_exceptions=True),
                timeout=timeout_ms / 1000,
            )
        except asyncio.TimeoutError:
            pass

    global _extractor, _drainer
    _extractor = extractor_fn
    _drainer = drainer_fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def execute_extract_memories(
    context: Any,
    append_system_message: Optional[AppendSystemMessageFn] = None,
) -> None:
    """
    Run memory extraction at the end of a query loop.
    Called fire-and-forget from handleStopHooks.
    No-ops until init_extract_memories() has been called.
    """
    if _extractor is not None:
        await _extractor(context, append_system_message)


async def drain_pending_extraction(timeout_ms: float = 60_000) -> None:
    """
    Await all in-flight extractions with a soft timeout.
    No-op until init_extract_memories() has been called.
    """
    await _drainer(timeout_ms)
