"""
Tool orchestration - partitions and runs tool calls concurrently or serially.

原始 TS: services/tools/toolOrchestration.ts (188 lines)
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple


def _get_max_tool_use_concurrency() -> int:
    """Get maximum concurrent tool executions from environment."""
    try:
        return int(os.environ.get("CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY", "") or "10")
    except (ValueError, TypeError):
        return 10


class MessageUpdate:
    """A message update with optional new context."""

    def __init__(
        self,
        message: Optional[Any] = None,
        new_context: Optional[Any] = None,
    ) -> None:
        self.message = message
        self.new_context = new_context


def _find_tool_by_name(tools: Any, name: str) -> Optional[Any]:
    if isinstance(tools, (list, tuple)):
        for t in tools:
            if getattr(t, "name", None) == name:
                return t
    return None


def _mark_tool_use_complete(tool_use_context: Any, tool_use_id: str) -> None:
    fn = getattr(tool_use_context, "set_in_progress_tool_use_ids", None)
    if fn and callable(fn):
        try:
            fn(lambda prev: prev - {tool_use_id} if hasattr(prev, "discard") else {k for k in prev if k != tool_use_id})
        except Exception:
            pass


def _find_assistant_message_for_tool_use(
    assistant_messages: List[Any],
    tool_use_id: str,
) -> Optional[Any]:
    """Find the assistant message that contains a specific tool use."""
    for am in assistant_messages:
        msg = getattr(am, "message", am)
        content = getattr(msg, "content", None)
        if isinstance(content, (list, tuple)):
            for block in content:
                block_type = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
                block_id = getattr(block, "id", None) or (block.get("id") if isinstance(block, dict) else None)
                if block_type == "tool_use" and block_id == tool_use_id:
                    return am
    return None


class _Batch:
    """A batch of tool calls, either all concurrent or a single serial."""

    def __init__(self, is_concurrency_safe: bool, blocks: List[Any]) -> None:
        self.is_concurrency_safe = is_concurrency_safe
        self.blocks = blocks


def _partition_tool_calls(
    tool_use_messages: List[Any],
    tool_use_context: Any,
) -> List[_Batch]:
    """Partition tool calls into batches of concurrent-safe or single serial."""
    options = getattr(tool_use_context, "options", None) or {}
    tools = getattr(options, "tools", []) if hasattr(options, "tools") else options.get("tools", [])

    batches: List[_Batch] = []

    for tool_use in tool_use_messages:
        tool_name = getattr(tool_use, "name", "") or (tool_use.get("name", "") if isinstance(tool_use, dict) else "")
        block_input = getattr(tool_use, "input", {})
        if isinstance(tool_use, dict):
            block_input = tool_use.get("input", {})

        tool = _find_tool_by_name(tools, tool_name)
        is_concurrency_safe = False

        if tool:
            input_schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None)
            if input_schema:
                try:
                    parse_result = input_schema.safe_parse(block_input) if hasattr(input_schema, "safe_parse") else None
                    if parse_result and parse_result.success:
                        cc_fn = getattr(tool, "is_concurrency_safe", None) or getattr(tool, "isConcurrencySafe", None)
                        if cc_fn and callable(cc_fn):
                            try:
                                is_concurrency_safe = bool(cc_fn(parse_result.data))
                            except Exception:
                                is_concurrency_safe = False
                except Exception:
                    pass

        if is_concurrency_safe and batches and batches[-1].is_concurrency_safe:
            batches[-1].blocks.append(tool_use)
        else:
            batches.append(_Batch(is_concurrency_safe, [tool_use]))

    return batches


async def run_tools(
    tool_use_messages: List[Any],
    assistant_messages: List[Any],
    can_use_tool: Any,
    tool_use_context: Any,
) -> AsyncGenerator[MessageUpdate, None]:
    """Run all tool uses, partitioned into concurrent/serial batches.

    Args:
        tool_use_messages: List of tool use blocks to execute.
        assistant_messages: List of assistant messages containing the tool uses.
        can_use_tool: Permission check function.
        tool_use_context: Context object for tool execution.

    Yields:
        MessageUpdate objects with message and updated context.
    """
    current_context = tool_use_context

    for batch in _partition_tool_calls(tool_use_messages, current_context):
        if batch.is_concurrency_safe:
            queued_context_modifiers: Dict[str, List[Any]] = {}

            async for update in _run_tools_concurrently(
                batch.blocks,
                assistant_messages,
                can_use_tool,
                current_context,
            ):
                cm = getattr(update, "context_modifier", None)
                if cm:
                    tool_use_id = (
                        cm.get("tool_use_id") or cm.get("toolUseID")
                        if isinstance(cm, dict)
                        else getattr(cm, "tool_use_id", None) or getattr(cm, "toolUseID", None)
                    )
                    modify_fn = (
                        cm.get("modify_context") or cm.get("modifyContext")
                        if isinstance(cm, dict)
                        else getattr(cm, "modify_context", None) or getattr(cm, "modifyContext", None)
                    )
                    if tool_use_id and modify_fn:
                        if tool_use_id not in queued_context_modifiers:
                            queued_context_modifiers[tool_use_id] = []
                        queued_context_modifiers[tool_use_id].append(modify_fn)

                msg = getattr(update, "message", None)
                yield MessageUpdate(message=msg, new_context=current_context)

            # Apply context modifiers for each block
            for block in batch.blocks:
                block_id = getattr(block, "id", "") or (block.get("id", "") if isinstance(block, dict) else "")
                modifiers = queued_context_modifiers.get(block_id, [])
                for modifier in modifiers:
                    current_context = modifier(current_context)

            yield MessageUpdate(new_context=current_context)

        else:
            # Run non-concurrent batch serially
            async for update in _run_tools_serially(
                batch.blocks,
                assistant_messages,
                can_use_tool,
                current_context,
            ):
                new_ctx = getattr(update, "new_context", None)
                if new_ctx is not None:
                    current_context = new_ctx
                yield MessageUpdate(
                    message=getattr(update, "message", None),
                    new_context=current_context,
                )


async def _run_tools_serially(
    tool_use_messages: List[Any],
    assistant_messages: List[Any],
    can_use_tool: Any,
    tool_use_context: Any,
) -> AsyncGenerator[MessageUpdate, None]:
    """Run tools serially, applying context modifiers after each."""
    from .tool_execution import run_tool_use

    current_context = tool_use_context

    for tool_use in tool_use_messages:
        tool_use_id = getattr(tool_use, "id", "") or (tool_use.get("id", "") if isinstance(tool_use, dict) else "")

        fn = getattr(current_context, "set_in_progress_tool_use_ids", None)
        if fn and callable(fn):
            try:
                fn(lambda prev: prev | {tool_use_id})
            except Exception:
                pass

        assistant_msg = _find_assistant_message_for_tool_use(assistant_messages, tool_use_id)

        async for update in run_tool_use(
            tool_use,
            assistant_msg,
            can_use_tool,
            current_context,
        ):
            cm = getattr(update, "context_modifier", None)
            if cm:
                modify_fn = (
                    cm.get("modify_context") or cm.get("modifyContext")
                    if isinstance(cm, dict)
                    else getattr(cm, "modify_context", None) or getattr(cm, "modifyContext", None)
                )
                if modify_fn:
                    current_context = modify_fn(current_context)

            msg = getattr(update, "message", None)
            yield MessageUpdate(message=msg, new_context=current_context)

        _mark_tool_use_complete(tool_use_context, tool_use_id)


async def _run_tools_concurrently(
    tool_use_messages: List[Any],
    assistant_messages: List[Any],
    can_use_tool: Any,
    tool_use_context: Any,
) -> AsyncGenerator[Any, None]:
    """Run tools concurrently, up to max concurrency limit."""
    from .tool_execution import run_tool_use

    max_concurrency = _get_max_tool_use_concurrency()

    async def _run_single(tool_use: Any) -> List[Any]:
        """Run a single tool use and collect all updates."""
        tool_use_id = getattr(tool_use, "id", "") or (tool_use.get("id", "") if isinstance(tool_use, dict) else "")

        fn = getattr(tool_use_context, "set_in_progress_tool_use_ids", None)
        if fn and callable(fn):
            try:
                fn(lambda prev: prev | {tool_use_id})
            except Exception:
                pass

        assistant_msg = _find_assistant_message_for_tool_use(assistant_messages, tool_use_id)
        updates = []
        async for update in run_tool_use(tool_use, assistant_msg, can_use_tool, tool_use_context):
            updates.append(update)

        _mark_tool_use_complete(tool_use_context, tool_use_id)
        return updates

    # Use semaphore for concurrency control
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _run_with_semaphore(tool_use: Any) -> List[Any]:
        async with semaphore:
            return await _run_single(tool_use)

    # Run all concurrently up to limit
    tasks = [asyncio.ensure_future(_run_with_semaphore(tu)) for tu in tool_use_messages]

    # Yield results as they complete, maintaining order
    for task in asyncio.as_completed(tasks):
        try:
            updates = await task
            for update in updates:
                yield update
        except Exception as e:
            from ...utils.log import log_error  # type: ignore
            log_error(e)
