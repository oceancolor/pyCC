"""
StreamingToolExecutor - executes tools as they stream in with concurrency control.

Concurrent-safe tools can execute in parallel with other concurrent-safe tools.
Non-concurrent tools must execute alone (exclusive access).
Results are buffered and emitted in the order tools were received.

原始 TS: services/tools/StreamingToolExecutor.ts
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional, AsyncGenerator

from ...utils.log import log_error
from ...utils.debug import log_for_debugging


@dataclass
class TrackedTool:
    """A tool being tracked through the execution pipeline."""

    id: str
    block: Any  # ToolUseBlock
    assistant_message: Any  # AssistantMessage
    status: str  # 'queued' | 'executing' | 'completed' | 'yielded'
    is_concurrency_safe: bool
    promise: Optional[asyncio.Task] = None
    results: Optional[List[Any]] = None  # Message[]
    pending_progress: List[Any] = field(default_factory=list)  # progress messages
    context_modifiers: Optional[List[Any]] = None


class MessageUpdate:
    """A message update with optional new context."""

    def __init__(
        self,
        message: Optional[Any] = None,
        new_context: Optional[Any] = None,
    ) -> None:
        self.message = message
        self.new_context = new_context


def _create_user_message(**kwargs: Any) -> Any:
    from ...utils.messages import create_user_message  # type: ignore
    return create_user_message(**kwargs)


def _find_tool_by_name(tools: Any, name: str) -> Optional[Any]:
    if isinstance(tools, (list, tuple)):
        for t in tools:
            if getattr(t, "name", None) == name:
                return t
    return None


def _create_abort_controller(parent_signal: Any = None) -> Any:
    """Create a child abort controller."""
    try:
        from ...utils.abort_controller import create_child_abort_controller  # type: ignore
        return create_child_abort_controller(parent_signal)
    except (ImportError, Exception):
        try:
            from ...utils.abort import create_abort_controller  # type: ignore
            return create_abort_controller()
        except (ImportError, Exception):
            class _Ctrl:
                def __init__(self) -> None:
                    self._aborted = False
                    self.reason: Any = None

                def abort(self, reason: Any = None) -> None:
                    self._aborted = True
                    self.reason = reason

                @property
                def signal(self) -> "_Sig":
                    return _Sig(self)

            class _Sig:
                def __init__(self, c: "_Ctrl") -> None:
                    self._c = c

                @property
                def aborted(self) -> bool:
                    return self._c._aborted

                @property
                def reason(self) -> Any:
                    return self._c.reason

                def add_event_listener(self, event: str, cb: Any, **kw: Any) -> None:
                    pass

            return _Ctrl()


class StreamingToolExecutor:
    """Executes tools as they stream in with concurrency control."""

    def __init__(
        self,
        tool_definitions: Any,
        can_use_tool: Any,
        tool_use_context: Any,
    ) -> None:
        self._tool_definitions = tool_definitions
        self._can_use_tool = can_use_tool
        self._tool_use_context = tool_use_context
        self._tools: List[TrackedTool] = []
        self._has_errored = False
        self._errored_tool_description = ""
        self._discarded = False
        self._progress_available_event: asyncio.Event = asyncio.Event()

        # Child abort controller for sibling cancellation
        parent_abort = getattr(tool_use_context, "abort_controller", None)
        self._sibling_abort_controller = _create_abort_controller(parent_abort)

    def discard(self) -> None:
        """Discard all pending/in-progress tools (streaming fallback)."""
        self._discarded = True

    def add_tool(self, block: Any, assistant_message: Any) -> None:
        """Add a tool to the execution queue."""
        block_name = getattr(block, "name", "") or (block.get("name", "") if isinstance(block, dict) else "")
        block_id = getattr(block, "id", "") or (block.get("id", "") if isinstance(block, dict) else "")

        tool_def = _find_tool_by_name(self._tool_definitions, block_name)
        if not tool_def:
            # Add as completed with error
            err_msg = _create_user_message(
                content=[{
                    "type": "tool_result",
                    "content": f"<tool_use_error>Error: No such tool available: {block_name}</tool_use_error>",
                    "is_error": True,
                    "tool_use_id": block_id,
                }],
                tool_use_result=f"Error: No such tool available: {block_name}",
                source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
            )
            self._tools.append(TrackedTool(
                id=block_id,
                block=block,
                assistant_message=assistant_message,
                status="completed",
                is_concurrency_safe=True,
                results=[err_msg],
            ))
            return

        # Check concurrency safety
        is_concurrency_safe = False
        block_input = getattr(block, "input", {})
        if isinstance(block, dict):
            block_input = block.get("input", {})

        input_schema = getattr(tool_def, "input_schema", None) or getattr(tool_def, "inputSchema", None)
        if input_schema:
            try:
                parse_result = input_schema.safe_parse(block_input) if hasattr(input_schema, "safe_parse") else None
                if parse_result and parse_result.success:
                    cc_fn = getattr(tool_def, "is_concurrency_safe", None) or getattr(tool_def, "isConcurrencySafe", None)
                    if cc_fn and callable(cc_fn):
                        try:
                            is_concurrency_safe = bool(cc_fn(parse_result.data))
                        except Exception:
                            is_concurrency_safe = False
            except Exception:
                pass

        tracked = TrackedTool(
            id=block_id,
            block=block,
            assistant_message=assistant_message,
            status="queued",
            is_concurrency_safe=is_concurrency_safe,
        )
        self._tools.append(tracked)
        asyncio.ensure_future(self._process_queue())

    def _can_execute_tool(self, is_concurrency_safe: bool) -> bool:
        """Check if a tool can execute based on current concurrency state."""
        executing = [t for t in self._tools if t.status == "executing"]
        return (
            len(executing) == 0
            or (is_concurrency_safe and all(t.is_concurrency_safe for t in executing))
        )

    async def _process_queue(self) -> None:
        """Process the queue, starting tools when concurrency conditions allow."""
        for tool in self._tools:
            if tool.status != "queued":
                continue
            if self._can_execute_tool(tool.is_concurrency_safe):
                await self._execute_tool(tool)
            else:
                if not tool.is_concurrency_safe:
                    break

    def _create_synthetic_error_message(
        self,
        tool_use_id: str,
        reason: str,  # 'sibling_error' | 'user_interrupted' | 'streaming_fallback'
        assistant_message: Any,
    ) -> Any:
        """Create a synthetic error message for cancelled tools."""
        if reason == "user_interrupted":
            try:
                from ...utils.messages import with_memory_correction_hint, REJECT_MESSAGE  # type: ignore
                content = with_memory_correction_hint(REJECT_MESSAGE)
            except (ImportError, Exception):
                content = "User rejected tool use"
            return _create_user_message(
                content=[{
                    "type": "tool_result",
                    "content": content,
                    "is_error": True,
                    "tool_use_id": tool_use_id,
                }],
                tool_use_result="User rejected tool use",
                source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
            )
        if reason == "streaming_fallback":
            return _create_user_message(
                content=[{
                    "type": "tool_result",
                    "content": "<tool_use_error>Error: Streaming fallback - tool execution discarded</tool_use_error>",
                    "is_error": True,
                    "tool_use_id": tool_use_id,
                }],
                tool_use_result="Streaming fallback - tool execution discarded",
                source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
            )

        desc = self._errored_tool_description
        msg = (
            f"Cancelled: parallel tool call {desc} errored"
            if desc
            else "Cancelled: parallel tool call errored"
        )
        return _create_user_message(
            content=[{
                "type": "tool_result",
                "content": f"<tool_use_error>{msg}</tool_use_error>",
                "is_error": True,
                "tool_use_id": tool_use_id,
            }],
            tool_use_result=msg,
            source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
        )

    def _get_abort_reason(self, tool: TrackedTool) -> Optional[str]:
        """Determine why a tool should be cancelled."""
        if self._discarded:
            return "streaming_fallback"
        if self._has_errored:
            return "sibling_error"

        abort_ctrl = getattr(self._tool_use_context, "abort_controller", None)
        abort_signal = getattr(abort_ctrl, "signal", abort_ctrl) if abort_ctrl else None
        if abort_signal and getattr(abort_signal, "aborted", False):
            reason = getattr(abort_signal, "reason", None)
            if reason == "interrupt":
                return (
                    "user_interrupted"
                    if self._get_tool_interrupt_behavior(tool) == "cancel"
                    else None
                )
            return "user_interrupted"
        return None

    def _get_tool_interrupt_behavior(self, tool: TrackedTool) -> str:
        """Get whether a tool should be 'cancel' or 'block' on interrupt."""
        tool_def = _find_tool_by_name(self._tool_definitions, getattr(tool.block, "name", ""))
        if not tool_def:
            return "block"
        ib_fn = getattr(tool_def, "interrupt_behavior", None) or getattr(tool_def, "interruptBehavior", None)
        if ib_fn and callable(ib_fn):
            try:
                return ib_fn()
            except Exception:
                return "block"
        return "block"

    def _get_tool_description(self, tool: TrackedTool) -> str:
        """Get a short description of the tool for error messages."""
        block_input = getattr(tool.block, "input", {})
        if isinstance(tool.block, dict):
            block_input = tool.block.get("input", {})
        if isinstance(block_input, dict):
            summary = (
                block_input.get("command")
                or block_input.get("file_path")
                or block_input.get("pattern")
                or ""
            )
            if isinstance(summary, str) and summary:
                truncated = summary[:40] + ("…" if len(summary) > 40 else "")
                block_name = getattr(tool.block, "name", "")
                return f"{block_name}({truncated})"
        return getattr(tool.block, "name", "unknown")

    def _update_interruptible_state(self) -> None:
        """Update the interruptible state in the tool use context."""
        executing = [t for t in self._tools if t.status == "executing"]
        fn = getattr(self._tool_use_context, "set_has_interruptible_tool_in_progress", None)
        if fn and callable(fn):
            try:
                fn(
                    len(executing) > 0
                    and all(self._get_tool_interrupt_behavior(t) == "cancel" for t in executing)
                )
            except Exception:
                pass

    async def _execute_tool(self, tool: TrackedTool) -> None:
        """Execute a tool and collect its results."""
        tool.status = "executing"

        # Track in-progress IDs
        fn = getattr(self._tool_use_context, "set_in_progress_tool_use_ids", None)
        if fn and callable(fn):
            try:
                fn(lambda prev: prev | {tool.id})
            except Exception:
                pass

        self._update_interruptible_state()

        messages: List[Any] = []
        context_modifiers: List[Any] = []

        async def collect_results() -> None:
            from .tool_execution import run_tool_use

            initial_abort_reason = self._get_abort_reason(tool)
            if initial_abort_reason:
                messages.append(
                    self._create_synthetic_error_message(tool.id, initial_abort_reason, tool.assistant_message)
                )
                tool.results = messages
                tool.context_modifiers = context_modifiers
                tool.status = "completed"
                self._update_interruptible_state()
                return

            # Per-tool child controller
            tool_abort_controller = _create_abort_controller(self._sibling_abort_controller)

            sibling_signal = getattr(self._sibling_abort_controller, "signal", self._sibling_abort_controller)

            def _on_tool_abort() -> None:
                sig = getattr(tool_abort_controller, "signal", tool_abort_controller)
                reason = getattr(sig, "reason", None)
                ctx_abort = getattr(self._tool_use_context, "abort_controller", None)
                ctx_sig = getattr(ctx_abort, "signal", ctx_abort) if ctx_abort else None
                ctx_aborted = getattr(ctx_sig, "aborted", False) if ctx_sig else False
                if (
                    reason != "sibling_error"
                    and not ctx_aborted
                    and not self._discarded
                ):
                    if ctx_abort:
                        try:
                            ctx_abort.abort(reason)
                        except Exception:
                            pass

            try:
                add_el = getattr(getattr(tool_abort_controller, "signal", None), "add_event_listener", None)
                if add_el:
                    add_el("abort", _on_tool_abort, once=True)
            except Exception:
                pass

            # Build modified context with tool's abort controller
            import copy
            try:
                ctx = copy.copy(self._tool_use_context)
                ctx.abort_controller = tool_abort_controller
            except Exception:
                ctx = self._tool_use_context

            generator = run_tool_use(
                tool.block,
                tool.assistant_message,
                self._can_use_tool,
                ctx,
            )

            this_tool_errored = False
            async for update in generator:
                abort_reason = self._get_abort_reason(tool)
                if abort_reason and not this_tool_errored:
                    messages.append(
                        self._create_synthetic_error_message(tool.id, abort_reason, tool.assistant_message)
                    )
                    break

                msg = getattr(update, "message", None)
                is_error_result = False
                if msg and getattr(msg, "type", None) == "user":
                    content = getattr(getattr(msg, "message", msg), "content", None)
                    if isinstance(content, list):
                        is_error_result = any(
                            getattr(c, "type", None) == "tool_result"
                            and getattr(c, "is_error", False)
                            for c in content
                        )
                        if not is_error_result:
                            is_error_result = any(
                                isinstance(c, dict)
                                and c.get("type") == "tool_result"
                                and c.get("is_error")
                                for c in content
                            )

                if is_error_result:
                    this_tool_errored = True
                    block_name = getattr(tool.block, "name", "") or (tool.block.get("name", "") if isinstance(tool.block, dict) else "")
                    try:
                        from ...tools.bash_tool.tool_name import BASH_TOOL_NAME  # type: ignore
                        is_bash = block_name == BASH_TOOL_NAME
                    except (ImportError, Exception):
                        is_bash = "bash" in block_name.lower()
                    if is_bash:
                        self._has_errored = True
                        self._errored_tool_description = self._get_tool_description(tool)
                        try:
                            self._sibling_abort_controller.abort("sibling_error")
                        except Exception:
                            pass

                if msg:
                    if getattr(msg, "type", None) == "progress":
                        tool.pending_progress.append(msg)
                        self._progress_available_event.set()
                    else:
                        messages.append(msg)

                cm = getattr(update, "context_modifier", None)
                if cm:
                    modifier_fn = cm.get("modify_context") or cm.get("modifyContext") if isinstance(cm, dict) else getattr(cm, "modify_context", None) or getattr(cm, "modifyContext", None)
                    if modifier_fn:
                        context_modifiers.append(modifier_fn)

            tool.results = messages
            tool.context_modifiers = context_modifiers
            tool.status = "completed"
            self._update_interruptible_state()

            # Apply context modifiers for non-concurrent tools
            if not tool.is_concurrency_safe and context_modifiers:
                for modifier in context_modifiers:
                    self._tool_use_context = modifier(self._tool_use_context)

        task = asyncio.ensure_future(collect_results())
        tool.promise = task

        def _on_done(_: Any) -> None:
            asyncio.ensure_future(self._process_queue())

        task.add_done_callback(_on_done)

    def get_completed_results(self) -> Generator[MessageUpdate, None, None]:
        """Get completed results ready to yield (non-blocking)."""
        if self._discarded:
            return

        for tool in self._tools:
            # Always yield pending progress
            while tool.pending_progress:
                progress_msg = tool.pending_progress.pop(0)
                yield MessageUpdate(message=progress_msg, new_context=self._tool_use_context)

            if tool.status == "yielded":
                continue

            if tool.status == "completed" and tool.results is not None:
                tool.status = "yielded"
                for msg in tool.results:
                    yield MessageUpdate(message=msg, new_context=self._tool_use_context)
                _mark_tool_use_complete(self._tool_use_context, tool.id)
            elif tool.status == "executing" and not tool.is_concurrency_safe:
                break

    def _has_pending_progress(self) -> bool:
        return any(len(t.pending_progress) > 0 for t in self._tools)

    async def get_remaining_results(self) -> AsyncGenerator[MessageUpdate, None]:
        """Wait for remaining tools and yield their results."""
        if self._discarded:
            return

        while self._has_unfinished_tools():
            await self._process_queue()

            for result in self.get_completed_results():
                yield result

            if (
                self._has_executing_tools()
                and not self._has_completed_results()
                and not self._has_pending_progress()
            ):
                executing_tasks = [
                    t.promise for t in self._tools
                    if t.status == "executing" and t.promise is not None
                ]

                self._progress_available_event.clear()
                progress_wait = asyncio.ensure_future(
                    self._progress_available_event.wait()
                )

                if executing_tasks:
                    await asyncio.wait(
                        executing_tasks + [progress_wait],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

        for result in self.get_completed_results():
            yield result

    def _has_completed_results(self) -> bool:
        return any(t.status == "completed" for t in self._tools)

    def _has_executing_tools(self) -> bool:
        return any(t.status == "executing" for t in self._tools)

    def _has_unfinished_tools(self) -> bool:
        return any(t.status != "yielded" for t in self._tools)

    def get_updated_context(self) -> Any:
        """Get the current tool use context (may have been modified by context modifiers)."""
        return self._tool_use_context


def _mark_tool_use_complete(tool_use_context: Any, tool_use_id: str) -> None:
    """Mark a tool use as complete in the context."""
    fn = getattr(tool_use_context, "set_in_progress_tool_use_ids", None)
    if fn and callable(fn):
        try:
            fn(lambda prev: prev - {tool_use_id} if hasattr(prev, "discard") else {k for k in prev if k != tool_use_id})
        except Exception:
            pass
