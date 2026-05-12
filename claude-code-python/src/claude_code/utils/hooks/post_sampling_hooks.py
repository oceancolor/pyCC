"""
Post-sampling hooks - internal API, not exposed through settings.json (yet).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Coroutine, Dict, List, Optional, Union

if TYPE_CHECKING:
    pass

# Generic context for REPL hooks (both post-sampling and stop hooks)
REPLHookContext = Dict[str, Any]

PostSamplingHook = Callable[[REPLHookContext], Union[Coroutine[Any, Any, None], None]]

# Internal registry for post-sampling hooks
_post_sampling_hooks: List[PostSamplingHook] = []


def register_post_sampling_hook(hook: PostSamplingHook) -> None:
    """Register a post-sampling hook that will be called after model sampling completes.
    This is an internal API not exposed through settings."""
    _post_sampling_hooks.append(hook)


def clear_post_sampling_hooks() -> None:
    """Clear all registered post-sampling hooks (for testing)."""
    _post_sampling_hooks.clear()


async def execute_post_sampling_hooks(
    messages: List[Any],
    system_prompt: Any,
    user_context: Dict[str, str],
    system_context: Dict[str, str],
    tool_use_context: Any,
    query_source: Optional[str] = None,
) -> None:
    """Execute all registered post-sampling hooks."""
    import asyncio

    context: REPLHookContext = {
        "messages": messages,
        "systemPrompt": system_prompt,
        "userContext": user_context,
        "systemContext": system_context,
        "toolUseContext": tool_use_context,
        "querySource": query_source,
    }

    for hook in list(_post_sampling_hooks):
        try:
            result = hook(context)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            from ..log import log_error
            log_error(e)
