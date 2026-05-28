"""
QueryEngine — higher-level wrapper around query() with session management.
Ported from QueryEngine.ts (1295 lines → core class).

Provides:
- submit_message()  — async generator, core turn entry-point
- interrupt()       — abort in-flight query
- fork()            — clone engine with different config (worktree support)
- set_system_prompt()
- get_messages()
- clear_messages()
- is_running property
- ask()             — convenience single-turn query (also exported standalone)
"""
from __future__ import annotations

import asyncio
import uuid as _uuid_mod
from typing import Any, AsyncIterator, Dict, List, Optional

from claude_code.query import query, QueryParams, get_messages_after_compact_boundary


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

class QueryEngineConfig:
    """Configuration for a QueryEngine instance."""

    def __init__(
        self,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        permission_mode: str = "default",
        tools: Optional[list] = None,
        system_prompt: Optional[List[str]] = None,
        is_non_interactive: bool = False,
        session_id: Optional[str] = None,
        custom_system_prompt: Optional[str] = None,
        append_system_prompt: Optional[str] = None,
        max_turns: Optional[int] = None,
        max_budget_usd: Optional[float] = None,
        thinking_config: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
        fallback_model: Optional[str] = None,
        pre_tool_hooks: Optional[List[Any]] = None,
        post_tool_hooks: Optional[List[Any]] = None,
        post_sampling_hooks: Optional[List[Any]] = None,
        permission_context: Optional[Any] = None,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.permission_mode = permission_mode
        self.tools = tools or []
        # Prefer custom_system_prompt as the canonical prompt
        if custom_system_prompt is not None:
            base = [custom_system_prompt]
        else:
            base = list(system_prompt or [])
        if append_system_prompt:
            base.append(append_system_prompt)
        self.system_prompt: List[str] = base
        self.is_non_interactive = is_non_interactive
        self.session_id = session_id or str(_uuid_mod.uuid4())
        self.custom_system_prompt = custom_system_prompt
        self.append_system_prompt = append_system_prompt
        self.max_turns = max_turns
        self.max_budget_usd = max_budget_usd
        self.thinking_config = thinking_config
        self.verbose = verbose
        self.fallback_model = fallback_model
        self.pre_tool_hooks: List[Any] = pre_tool_hooks or []
        self.post_tool_hooks: List[Any] = post_tool_hooks or []
        self.post_sampling_hooks: List[Any] = post_sampling_hooks or []
        self.permission_context = permission_context

    def clone(self, **overrides) -> "QueryEngineConfig":
        """Return a shallow copy with selective field overrides."""
        c = QueryEngineConfig.__new__(QueryEngineConfig)
        c.__dict__.update(self.__dict__)
        for k, v in overrides.items():
            setattr(c, k, v)
        return c


# ─────────────────────────────────────────────────────────────────────────────
# QueryEngine
# ─────────────────────────────────────────────────────────────────────────────

class QueryEngine:
    """
    Stateful query engine that manages conversation history
    and orchestrates tool-use loops.

    One QueryEngine per conversation.  Each ``submit_message()`` call starts
    a new turn within the same conversation.  State (messages, usage, etc.)
    persists across turns.
    """

    def __init__(
        self,
        config: Optional[QueryEngineConfig] = None,
        initial_messages: Optional[List[dict]] = None,
    ):
        self.config = config or QueryEngineConfig()
        self._messages: List[dict] = list(initial_messages or [])
        self._abort_event: asyncio.Event = asyncio.Event()
        self._running: bool = False
        self._total_usage: Dict[str, int] = {}
        self._turn_count: int = 0
        self._permission_denials: List[dict] = []

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """True while a submit_message() generator is being consumed."""
        return self._running

    @property
    def messages(self) -> List[dict]:
        """All messages in the conversation (read-only copy)."""
        return list(self._messages)

    # ── Core API ──────────────────────────────────────────────────────────────

    async def submit_message(
        self,
        user_message: Any,
        options: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[dict]:
        """
        Add a user message and stream response events for one turn.

        Parameters
        ----------
        user_message:
            str  → wrapped in a text content block automatically
            list → used as-is (content block array)
        options:
            uuid, is_meta, model_override, max_tokens_override

        Yields dicts with ``type`` key. Notable types:
            system_init, request_start, thinking, assistant_message,
            tool_use, tool_result, final_response, result, error,
            user_interruption, max_turns_reached
        """
        opts = options or {}
        self._running = True
        # Reset the abort event for this turn (re-arm after previous interrupt)
        self._abort_event.clear()

        try:
            async for event in self._run_turn(user_message, opts):
                yield event
        finally:
            self._running = False

    async def _run_turn(
        self,
        user_message: Any,
        options: Dict[str, Any],
    ) -> AsyncIterator[dict]:
        """Internal turn implementation."""
        cfg = self.config

        # ── Build user message content ────────────────────────────────────────
        if isinstance(user_message, str):
            content: Any = [{"type": "text", "text": user_message}]
        elif isinstance(user_message, list):
            content = user_message
        else:
            content = [{"type": "text", "text": str(user_message)}]

        # Attach uuid / meta if provided
        user_msg_obj: dict = {"role": "user", "content": content}
        if options.get("uuid"):
            user_msg_obj["uuid"] = options["uuid"]
        if options.get("is_meta"):
            user_msg_obj["is_meta"] = True

        self._messages.append(user_msg_obj)

        # ── Yield system_init event ───────────────────────────────────────────
        yield {
            "type": "system_init",
            "session_id": cfg.session_id,
            "model": options.get("model_override") or cfg.model,
            "permission_mode": cfg.permission_mode,
        }

        # ── Build query params ────────────────────────────────────────────────
        # Pre-serialize tools: resolve async description() before entering query()
        serialized_tools: List[Any] = []
        for t in cfg.tools:
            if isinstance(t, dict):
                serialized_tools.append(t)
                continue
            schema_fn = getattr(t, "input_schema", None)
            schema = schema_fn() if callable(schema_fn) else {"type": "object", "properties": {}}
            desc_attr = getattr(t, "description", "")
            import inspect as _inspect
            if _inspect.iscoroutinefunction(desc_attr):
                try:
                    desc = await desc_attr()
                except Exception:
                    desc = getattr(t, "name", "tool")
            elif callable(desc_attr):
                try:
                    desc = desc_attr()
                except Exception:
                    desc = getattr(t, "name", "tool")
            else:
                desc = str(desc_attr) if desc_attr else ""
            serialized_tools.append({
                "name": getattr(t, "name", "unknown"),
                "description": desc,
                "input_schema": schema,
                "_tool_obj": t,   # keep original for actual call dispatch
            })

        params: QueryParams = {
            "model": options.get("model_override") or cfg.model,
            "max_tokens": options.get("max_tokens_override") or cfg.max_tokens,
            "system_prompt": cfg.system_prompt,
            "tools": serialized_tools,
            "source": "query_engine",
            "is_non_interactive": cfg.is_non_interactive,
            "thinking_config": cfg.thinking_config,
            "max_turns": cfg.max_turns,
            "fallback_model": cfg.fallback_model,
            "pre_tool_hooks": cfg.pre_tool_hooks,
            "post_tool_hooks": cfg.post_tool_hooks,
            "post_sampling_hooks": cfg.post_sampling_hooks,
            "permission_context": cfg.permission_context,
        }

        # ── Run query loop ────────────────────────────────────────────────────
        start_ms = _now_ms()
        last_stop_reason: Optional[str] = None
        turn_count = 1
        total_usage: Dict[str, int] = {}

        async for event in query(self._messages, params, self._abort_event):
            evt_type = event.get("type")

            # ── Accumulate usage ──────────────────────────────────────────────
            if evt_type == "assistant_message":
                usage = event.get("usage", {})
                _accumulate_usage(total_usage, usage)
                stop_reason = event.get("stop_reason")
                if stop_reason:
                    last_stop_reason = stop_reason
                # Push to mutable history (full content)
                assistant_content = event.get("content", [])
                self._messages.append({"role": "assistant", "content": assistant_content})

            elif evt_type == "tool_result":
                # query() already appended assistant+tool_results to its own
                # copy. We track in our mutable store by rebuilding from events.
                # (query loop handles its own history; we mirror final state
                # by looking at what query returns as final_response)
                turn_count += 1

            elif evt_type == "final_response":
                last_stop_reason = event.get("stop_reason") or last_stop_reason
                # Yield result envelope
                yield {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "duration_ms": _now_ms() - start_ms,
                    "num_turns": turn_count,
                    "result": _extract_text_result(event.get("content", [])),
                    "stop_reason": last_stop_reason,
                    "session_id": cfg.session_id,
                    "usage": total_usage,
                    "permission_denials": self._permission_denials,
                }
                # Sync mutable messages from query's final state
                self._sync_messages_from_query(self._messages, event)
                yield event  # also yield the raw final_response
                return

            elif evt_type == "error":
                yield {
                    "type": "result",
                    "subtype": "error_during_execution",
                    "is_error": True,
                    "duration_ms": _now_ms() - start_ms,
                    "num_turns": turn_count,
                    "stop_reason": last_stop_reason,
                    "session_id": cfg.session_id,
                    "usage": total_usage,
                    "errors": [event.get("error", "unknown error")],
                }
                yield event
                return

            elif evt_type == "user_interruption":
                yield event
                return

            elif evt_type == "max_turns_reached":
                yield {
                    "type": "result",
                    "subtype": "error_max_turns",
                    "is_error": True,
                    "duration_ms": _now_ms() - start_ms,
                    "num_turns": turn_count,
                    "stop_reason": last_stop_reason,
                    "session_id": cfg.session_id,
                    "usage": total_usage,
                    "errors": ["Reached maximum number of turns"],
                }
                return

            # ── Budget check ──────────────────────────────────────────────────
            if cfg.max_budget_usd is not None:
                try:
                    from claude_code.cost_tracker import get_total_cost
                    if get_total_cost() >= cfg.max_budget_usd:
                        yield {
                            "type": "result",
                            "subtype": "error_max_budget_usd",
                            "is_error": True,
                            "duration_ms": _now_ms() - start_ms,
                            "num_turns": turn_count,
                            "stop_reason": last_stop_reason,
                            "session_id": cfg.session_id,
                            "usage": total_usage,
                            "errors": [f"Reached maximum budget (${cfg.max_budget_usd})"],
                        }
                        return
                except ImportError:
                    pass

            yield event

    def _sync_messages_from_query(
        self,
        messages: List[dict],
        final_event: dict,
    ) -> None:
        """
        After query() completes, the messages list already has the
        assistant message appended (done in _run_turn).  Nothing more needed
        for the basic implementation — the query loop handles its own copy.
        """
        pass

    # ── Control ───────────────────────────────────────────────────────────────

    def interrupt(self) -> None:
        """
        Interrupt an in-flight query.
        Sets the abort event that query() polls between iterations.
        """
        self._abort_event.set()

    # ── Fork ─────────────────────────────────────────────────────────────────

    def fork(self, new_config: Optional[QueryEngineConfig] = None) -> "QueryEngine":
        """
        Return a new QueryEngine that shares the same message history snapshot
        but has an independent abort controller and optionally a different config.

        Used for worktree / sub-agent scenarios (mirrors TS fork pattern).
        """
        forked_config = new_config or self.config.clone()
        engine = QueryEngine(
            config=forked_config,
            initial_messages=list(self._messages),
        )
        return engine

    # ── System prompt ─────────────────────────────────────────────────────────

    def set_system_prompt(self, prompt: str) -> None:
        """Replace the system prompt."""
        self.config.system_prompt = [prompt]
        self.config.custom_system_prompt = prompt

    def get_system_prompt(self) -> List[str]:
        """Return the current system prompt parts."""
        return list(self.config.system_prompt)

    # ── Messages ──────────────────────────────────────────────────────────────

    def get_messages(self) -> List[dict]:
        """Return full conversation history."""
        return list(self._messages)

    def set_messages(self, messages: List[dict]) -> None:
        """Replace conversation history."""
        self._messages = list(messages)

    def clear_messages(self) -> None:
        """
        Clear conversation history (preserves system prompt in config).
        Equivalent to starting a fresh session.
        """
        self._messages = []
        self._turn_count = 0
        self._total_usage = {}
        self._permission_denials = []
        # Re-arm abort event for the next turn
        self._abort_event.clear()

    def add_user_message(self, content: Any) -> None:
        """Append a user message to history without triggering a query."""
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        self._messages.append({"role": "user", "content": content})

    # ── Convenience: ask() method ─────────────────────────────────────────────

    async def ask(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Simplified single-turn query. Returns the final text response.

        Parameters
        ----------
        user_prompt:   The user's message text.
        system_prompt: Override system prompt for this call only.
        options:       Passed through to submit_message().

        Returns the concatenated text content of the final assistant response.
        """
        if system_prompt is not None:
            saved = self.config.system_prompt
            self.config.system_prompt = [system_prompt]

        try:
            full_text: List[str] = []
            async for event in self.submit_message(user_prompt, options):
                if event.get("type") == "final_response":
                    for block in event.get("content", []):
                        if isinstance(block, dict) and block.get("type") == "text":
                            full_text.append(block.get("text", ""))
                    break
            return "".join(full_text)
        finally:
            if system_prompt is not None:
                self.config.system_prompt = saved

    # ── Legacy compat ─────────────────────────────────────────────────────────

    async def stream(
        self,
        user_message: str,
        signal: Any = None,
    ) -> AsyncIterator[dict]:
        """
        Backward-compatible streaming method.
        New code should use submit_message() instead.
        """
        if signal is not None:
            # Honour external signal by bridging to our abort event
            if hasattr(signal, "is_set") and signal.is_set():
                self._abort_event.set()

        async for event in self.submit_message(user_message):
            yield event
            if event.get("type") in ("final_response", "user_interruption", "error"):
                break

    def clear(self) -> None:
        """Alias for clear_messages() (backward compat)."""
        self.clear_messages()


# ─────────────────────────────────────────────────────────────────────────────
# Module-level convenience functions
# ─────────────────────────────────────────────────────────────────────────────

async def ask(
    user_message: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    tools: Optional[list] = None,
    signal: Any = None,
    options: Optional[Dict[str, Any]] = None,
) -> AsyncIterator[dict]:
    """
    Convenience function for one-shot queries.

    Matches the exported ``ask()`` from QueryEngine.ts:
      - Creates a temporary QueryEngine
      - Runs a single turn
      - Yields all events
    """
    config = QueryEngineConfig(
        model=model,
        tools=tools or [],
        custom_system_prompt=system_prompt,
    )
    engine = QueryEngine(config)
    async for event in engine.submit_message(user_message, options):
        yield event


async def ask_text(
    user_message: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    tools: Optional[list] = None,
    signal: Any = None,
) -> str:
    """
    Like ask() but returns the final text response as a string.
    Convenience wrapper for callers that don't need streaming.
    """
    engine = QueryEngine(
        QueryEngineConfig(
            model=model,
            tools=tools or [],
            custom_system_prompt=system_prompt,
        )
    )
    return await engine.ask(user_message)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now_ms() -> int:
    """Current time in milliseconds."""
    import time
    return int(time.time() * 1000)


def _accumulate_usage(total: Dict[str, int], delta: Dict[str, Any]) -> None:
    """Add delta token counts into total."""
    for key, val in delta.items():
        if isinstance(val, (int, float)):
            total[key] = total.get(key, 0) + int(val)


def _extract_text_result(content: List[Any]) -> str:
    """Extract concatenated text from content blocks."""
    parts: List[str] = []
    for block in content:
        if isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
    return "".join(parts)
