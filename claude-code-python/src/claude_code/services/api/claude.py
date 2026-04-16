"""
Claude API query functions. Ported from services/api/claude.ts (3419 lines → core).
Implements: queryHaiku, queryWithModel, queryModelWithoutStreaming,
            queryModelWithStreaming, buildSystemPromptBlocks, etc.
"""
from __future__ import annotations
import asyncio
import os
from typing import Any, AsyncIterator, Dict, List, Optional, TypedDict

from claude_code.services.api.client import get_anthropic_client
from claude_code.services.api.with_retry import with_api_retry
from claude_code.utils.model.model import get_small_fast_model


class QueryOptions(TypedDict, total=False):
    model: str
    max_tokens: int
    temperature: float
    system: str
    enable_prompt_caching: bool
    max_retries: int
    source: str


class AssistantMessage(TypedDict, total=False):
    role: str
    content: Any
    stop_reason: Optional[str]
    usage: dict


def get_extra_body_params(beta_headers: Optional[list] = None) -> dict:
    params: dict = {}
    if beta_headers:
        params["betas"] = beta_headers
    return params


def get_prompt_caching_enabled(model: str) -> bool:
    """Check if prompt caching should be enabled for this model."""
    if os.environ.get("DISABLE_PROMPT_CACHING"):
        return False
    return "haiku" in model.lower() or "sonnet" in model.lower()


def build_system_prompt_blocks(system_prompt: List[str]) -> list:
    """Build API-format system prompt blocks from string list."""
    return [{"type": "text", "text": s} for s in system_prompt if s]


def update_usage(current: dict, delta: dict) -> dict:
    """Merge usage delta into current usage totals."""
    result = dict(current)
    for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                "cache_read_input_tokens"):
        result[key] = result.get(key, 0) + delta.get(key, 0)
    return result


def accumulate_usage(usages: List[dict]) -> dict:
    total: dict = {}
    for u in usages:
        total = update_usage(total, u)
    return total


async def query_model_without_streaming(
    messages: List[dict],
    system_prompt: Optional[List[str]] = None,
    tools: Optional[list] = None,
    options: Optional[QueryOptions] = None,
    signal: Any = None,
) -> AssistantMessage:
    """Send a non-streaming request to the Anthropic API."""
    opts = options or {}
    model = opts.get("model") or get_small_fast_model()
    max_tokens = opts.get("max_tokens", 4096)
    max_retries = opts.get("max_retries", 2)
    source = opts.get("source")

    system = build_system_prompt_blocks(system_prompt or [])

    async def _call():
        client = await get_anthropic_client(max_retries=max_retries)
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        # Use beta messages if available
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.beta.messages.create(**kwargs)
            )
        except AttributeError:
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.messages.create(**kwargs)
            )
        return response

    response = await with_api_retry(_call, max_retries=max_retries, source=source)

    content = getattr(response, "content", [])
    stop_reason = getattr(response, "stop_reason", None)
    usage = getattr(response, "usage", {})
    if hasattr(usage, "__dict__"):
        usage = vars(usage)

    return {
        "role": "assistant",
        "content": content,
        "stop_reason": stop_reason,
        "usage": usage,
    }


async def query_haiku(
    system_prompt: str = "",
    user_prompt: str = "",
    signal: Any = None,
    options: Optional[QueryOptions] = None,
) -> str:
    """Query Haiku for a short text response. Returns plain text."""
    opts = dict(options or {})
    opts["model"] = get_small_fast_model()
    opts.setdefault("max_tokens", 1024)

    messages = [{"role": "user", "content": user_prompt}]
    system = [system_prompt] if system_prompt else []

    result = await query_model_without_streaming(
        messages=messages,
        system_prompt=system,
        options=opts,
        signal=signal,
    )

    content = result.get("content", [])
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content)


async def query_with_model(
    system_prompt: str = "",
    user_prompt: str = "",
    model: Optional[str] = None,
    signal: Any = None,
    options: Optional[QueryOptions] = None,
) -> str:
    """Query a specific model. Returns plain text."""
    opts = dict(options or {})
    if model:
        opts["model"] = model
    return await query_haiku(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        signal=signal,
        options=opts,
    )


async def verify_api_key(api_key: str) -> bool:
    """Verify an API key by making a minimal test request."""
    try:
        client = await get_anthropic_client(api_key=api_key, max_retries=0)
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.messages.create(
                model=get_small_fast_model(),
                max_tokens=1,
                messages=[{"role": "user", "content": "hi"}],
            )
        )
        return True
    except Exception:
        return False


def get_api_metadata() -> dict:
    return {
        "user_agent": os.environ.get("CLAUDE_CODE_USER_AGENT", "ClaudeCode/1.0"),
        "session_id": os.environ.get("CLAUDE_CODE_SESSION_ID", ""),
    }


async def query_model_with_streaming(
    messages: List[dict],
    system_prompt: Optional[List[str]] = None,
    tools: Optional[list] = None,
    options: Optional[QueryOptions] = None,
    signal: Any = None,
) -> AsyncIterator[dict]:
    """Stream response from Claude API."""
    opts = options or {}
    model = opts.get("model") or get_small_fast_model()
    max_tokens = opts.get("max_tokens", 4096)
    max_retries = opts.get("max_retries", 2)
    system = build_system_prompt_blocks(system_prompt or [])

    client = await get_anthropic_client(max_retries=max_retries)
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
        "stream": True,
    }
    if system:
        kwargs["system"] = system
    if tools:
        kwargs["tools"] = tools

    try:
        loop = asyncio.get_event_loop()
        stream = await loop.run_in_executor(
            None, lambda: client.messages.create(**kwargs)
        )
        for event in stream:
            yield {"type": getattr(event, "type", "unknown"), "data": event}
    except Exception as e:
        yield {"type": "error", "error": str(e)}


# ============================================================================
# Ported from services/api/claude.ts
# Functions: get_extra_body_params (full), get_cache_control,
#            configure_task_budget_params, strip_excess_media_items,
#            add_cache_breakpoints, execute_non_streaming_request,
#            user_message_to_message_param, assistant_message_to_message_param,
#            get_max_output_tokens_for_model, adjust_params_for_non_streaming
# ============================================================================

import json
import re

# ---------------------------------------------------------------------------
# get_extra_body_params  (line 272 in claude.ts)
# ---------------------------------------------------------------------------

def get_extra_body_params(beta_headers: Optional[List[str]] = None) -> dict:
    """
    Assemble extra body parameters for the Anthropic API request.

    Reads CLAUDE_CODE_EXTRA_BODY (must be a JSON object string) and merges any
    beta_headers into the result.  Mirrors the TS implementation.
    """
    result: dict = {}

    extra_body_str = os.environ.get("CLAUDE_CODE_EXTRA_BODY")
    if extra_body_str:
        try:
            parsed = json.loads(extra_body_str)
            if isinstance(parsed, dict):
                result = dict(parsed)
            else:
                import logging
                logging.getLogger(__name__).error(
                    "CLAUDE_CODE_EXTRA_BODY env var must be a JSON object, "
                    "but was given %s", extra_body_str
                )
        except (json.JSONDecodeError, ValueError) as exc:
            import logging
            logging.getLogger(__name__).error(
                "Error parsing CLAUDE_CODE_EXTRA_BODY: %s", exc
            )

    if beta_headers:
        existing = result.get("anthropic_beta")
        if isinstance(existing, list):
            new_headers = [h for h in beta_headers if h not in existing]
            result["anthropic_beta"] = existing + new_headers
        else:
            result["anthropic_beta"] = list(beta_headers)

    return result


# ---------------------------------------------------------------------------
# get_cache_control  (line 358 in claude.ts)
# ---------------------------------------------------------------------------

def get_cache_control(
    scope: Optional[str] = None,
    query_source: Optional[str] = None,
) -> dict:
    """
    Return a cache_control dict.

    - type is always "ephemeral"
    - ttl "1h" is added when should_1h_cache_ttl() returns True
    - scope "global" is added when scope == "global"
    """
    ctrl: dict = {"type": "ephemeral"}
    if _should_1h_cache_ttl(query_source):
        ctrl["ttl"] = "1h"
    if scope == "global":
        ctrl["scope"] = scope
    return ctrl


def _should_1h_cache_ttl(query_source: Optional[str]) -> bool:
    """
    Simplified version: returns True only when explicitly opted-in via
    ENABLE_PROMPT_CACHING_1H env var (for Bedrock or dev testing).
    The GrowthBook + subscriber eligibility checks from TS are omitted —
    those depend on internal Anthropic infra not available in the Python port.
    """
    from claude_code.utils.env_utils import is_env_truthy
    if is_env_truthy(os.environ.get("ENABLE_PROMPT_CACHING_1H_BEDROCK")):
        return True
    return False


# ---------------------------------------------------------------------------
# configure_task_budget_params  (line 479 in claude.ts)
# ---------------------------------------------------------------------------

def configure_task_budget_params(
    task_budget: Optional[dict],
    output_config: dict,
    betas: List[str],
) -> None:
    """
    Attach task_budget to output_config and add TASK_BUDGETS beta header.

    task_budget = {"total": int, "remaining": int (optional)}
    Mutates output_config and betas in-place (mirrors the TS void return).
    Skipped when:
      - task_budget is None/empty
      - "task_budget" already exists in output_config
      - CLAUDE_CODE_FIRST_PARTY_ONLY_BETAS is not truthy
    """
    from claude_code.utils.env_utils import is_env_truthy

    TASK_BUDGETS_BETA_HEADER = "task-budgets-2026-03-13"

    if not task_budget:
        return
    if "task_budget" in output_config:
        return
    # In the TS this is gated on shouldIncludeFirstPartyOnlyBetas(); we mirror
    # with a simple env-var check so callers can gate if needed.
    if not is_env_truthy(os.environ.get("CLAUDE_CODE_FIRST_PARTY_ONLY_BETAS")):
        return

    budget_param: dict = {
        "type": "tokens",
        "total": task_budget["total"],
    }
    if task_budget.get("remaining") is not None:
        budget_param["remaining"] = task_budget["remaining"]

    output_config["task_budget"] = budget_param

    if TASK_BUDGETS_BETA_HEADER not in betas:
        betas.append(TASK_BUDGETS_BETA_HEADER)


# ---------------------------------------------------------------------------
# strip_excess_media_items  (line 956 in claude.ts)
# ---------------------------------------------------------------------------

def _is_media(block: dict) -> bool:
    """Return True if block is an image or document block."""
    return isinstance(block, dict) and block.get("type") in ("image", "document")


def _is_tool_result(block: dict) -> bool:
    """Return True if block is a tool_result block."""
    return isinstance(block, dict) and block.get("type") == "tool_result"


def strip_excess_media_items(
    messages: List[dict],
    limit: int,
) -> List[dict]:
    """
    Ensure messages contain at most ``limit`` media items (images + documents).
    Strips the oldest media first to preserve the most recent.

    Each message is expected to have a structure like:
      {"type": "user"|"assistant", "message": {"content": str | list}}

    Returns a (possibly new) list of messages.
    """
    # Count total media items across all messages
    to_remove = 0
    for msg in messages:
        content = _get_content(msg)
        if not isinstance(content, list):
            continue
        for block in content:
            if _is_media(block):
                to_remove += 1
            elif _is_tool_result(block):
                nested = block.get("content")
                if isinstance(nested, list):
                    for n in nested:
                        if _is_media(n):
                            to_remove += 1

    to_remove -= limit
    if to_remove <= 0:
        return messages

    result = []
    for msg in messages:
        if to_remove <= 0:
            result.append(msg)
            continue

        content = _get_content(msg)
        if not isinstance(content, list):
            result.append(msg)
            continue

        before = to_remove
        stripped = []
        for block in content:
            if _is_tool_result(block) and to_remove > 0:
                nested = block.get("content")
                if isinstance(nested, list):
                    filtered_nested = []
                    for n in nested:
                        if to_remove > 0 and _is_media(n):
                            to_remove -= 1
                        else:
                            filtered_nested.append(n)
                    if len(filtered_nested) != len(nested):
                        block = dict(block)
                        block["content"] = filtered_nested
                stripped.append(block)
            elif _is_media(block) and to_remove > 0:
                to_remove -= 1
                # skip (drop) this block
            else:
                stripped.append(block)

        if before == to_remove:
            result.append(msg)
        else:
            new_msg = dict(msg)
            new_message = dict(msg.get("message", {}))
            new_message["content"] = stripped
            new_msg["message"] = new_message
            result.append(new_msg)

    return result


def _get_content(msg: dict) -> Any:
    """Extract content from a message dict (handles both flat and nested)."""
    if "message" in msg:
        return msg["message"].get("content")
    return msg.get("content")


# ---------------------------------------------------------------------------
# user_message_to_message_param  (line 588 in claude.ts)
# ---------------------------------------------------------------------------

def user_message_to_message_param(
    message: dict,
    add_cache: bool = False,
    enable_prompt_caching: bool = False,
    query_source: Optional[str] = None,
) -> dict:
    """
    Convert an internal UserMessage to an Anthropic API MessageParam.

    message: {"type": "user", "message": {"role": "user", "content": str|list}}
    """
    inner = message.get("message", message)
    content = inner.get("content", "")

    if add_cache:
        if isinstance(content, str):
            block: dict = {"type": "text", "text": content}
            if enable_prompt_caching:
                block["cache_control"] = get_cache_control(
                    query_source=query_source
                )
            return {"role": "user", "content": [block]}
        else:
            # content is a list; add cache_control to the last item
            items = list(content)
            new_items = []
            for i, block in enumerate(items):
                if i == len(items) - 1:
                    new_block = dict(block)
                    if enable_prompt_caching:
                        new_block["cache_control"] = get_cache_control(
                            query_source=query_source
                        )
                    new_items.append(new_block)
                else:
                    new_items.append(block)
            return {"role": "user", "content": new_items}

    # No cache: shallow-copy array content to prevent mutation side effects
    if isinstance(content, list):
        return {"role": "user", "content": list(content)}
    return {"role": "user", "content": content}


# ---------------------------------------------------------------------------
# assistant_message_to_message_param  (line 633 in claude.ts)
# ---------------------------------------------------------------------------

def assistant_message_to_message_param(
    message: dict,
    add_cache: bool = False,
    enable_prompt_caching: bool = False,
    query_source: Optional[str] = None,
) -> dict:
    """
    Convert an internal AssistantMessage to an Anthropic API MessageParam.

    Mirrors TS: cache_control is added to the last non-thinking/non-redacted
    block when add_cache=True.
    """
    inner = message.get("message", message)
    content = inner.get("content", "")

    if add_cache:
        if isinstance(content, str):
            block = {"type": "text", "text": content}
            if enable_prompt_caching:
                block["cache_control"] = get_cache_control(
                    query_source=query_source
                )
            return {"role": "assistant", "content": [block]}
        else:
            items = list(content)
            new_items = []
            for i, block in enumerate(items):
                if i == len(items) - 1:
                    block_type = block.get("type", "") if isinstance(block, dict) else ""
                    # Skip thinking / redacted_thinking blocks
                    is_thinking = block_type in ("thinking", "redacted_thinking")
                    new_block = dict(block) if isinstance(block, dict) else block
                    if not is_thinking and enable_prompt_caching:
                        new_block["cache_control"] = get_cache_control(
                            query_source=query_source
                        )
                    new_items.append(new_block)
                else:
                    new_items.append(block)
            return {"role": "assistant", "content": new_items}

    return {"role": "assistant", "content": content}


# ---------------------------------------------------------------------------
# add_cache_breakpoints  (line 3063 in claude.ts)
# ---------------------------------------------------------------------------

def add_cache_breakpoints(
    messages: List[dict],
    enable_prompt_caching: bool,
    query_source: Optional[str] = None,
    use_cached_mc: bool = False,
    new_cache_edits: Optional[dict] = None,
    pinned_edits: Optional[List[dict]] = None,
    skip_cache_write: bool = False,
) -> List[dict]:
    """
    Insert prompt-cache breakpoints into messages before sending to the API.

    - Exactly one cache_control marker per request (at the last or
      second-to-last message depending on skip_cache_write).
    - When use_cached_mc=True, also handles cache_edits blocks.
    - Returns a new list of API-ready MessageParam dicts.

    Args:
        messages: Internal message list (UserMessage / AssistantMessage dicts).
        enable_prompt_caching: Whether to include cache_control markers.
        query_source: Query source string for 1h TTL eligibility.
        use_cached_mc: Whether microcompact cache editing is active.
        new_cache_edits: New cache_edits block to insert into last user message.
        pinned_edits: Previously-pinned cache_edits to re-insert at their
                      original positions.
        skip_cache_write: When True, use second-to-last message as marker.
    Returns:
        List of API MessageParam dicts (role + content).
    """
    # Determine which message index gets the cache_control marker
    marker_index = (len(messages) - 2) if skip_cache_write else (len(messages) - 1)

    result: List[dict] = []
    for index, msg in enumerate(messages):
        add_cache = index == marker_index
        msg_type = msg.get("type", "")
        if msg_type == "user":
            result.append(
                user_message_to_message_param(
                    msg,
                    add_cache=add_cache,
                    enable_prompt_caching=enable_prompt_caching,
                    query_source=query_source,
                )
            )
        else:
            result.append(
                assistant_message_to_message_param(
                    msg,
                    add_cache=add_cache,
                    enable_prompt_caching=enable_prompt_caching,
                    query_source=query_source,
                )
            )

    if not use_cached_mc:
        return result

    # ---- microcompact cache_edits handling ----
    # (simplified: TS version also adds cache_reference to tool_result blocks,
    #  but that requires server-side context we omit here)

    seen_delete_refs: set = set()

    def deduplicate_edits(block: dict) -> dict:
        unique = [
            e for e in block.get("edits", [])
            if e.get("cache_reference") not in seen_delete_refs
        ]
        for e in unique:
            seen_delete_refs.add(e.get("cache_reference"))
        return {**block, "edits": unique}

    # Re-insert previously-pinned cache_edits at their original positions
    for pinned in (pinned_edits or []):
        idx = pinned.get("userMessageIndex", -1)
        if 0 <= idx < len(result):
            msg = result[idx]
            if msg.get("role") == "user":
                if not isinstance(msg.get("content"), list):
                    msg = {**msg, "content": [{"type": "text", "text": msg.get("content", "")}]}
                    result[idx] = msg
                deduped = deduplicate_edits(pinned.get("block", {}))
                if deduped.get("edits"):
                    content_list = list(msg["content"])
                    content_list.append(deduped)
                    result[idx] = {**msg, "content": content_list}

    # Insert new cache_edits into the last user message
    if new_cache_edits and result:
        deduped_new = deduplicate_edits(new_cache_edits)
        if deduped_new.get("edits"):
            for i in range(len(result) - 1, -1, -1):
                msg = result[i]
                if msg.get("role") == "user":
                    if not isinstance(msg.get("content"), list):
                        msg = {**msg, "content": [{"type": "text", "text": msg.get("content", "")}]}
                    content_list = list(msg["content"])
                    content_list.append(deduped_new)
                    result[i] = {**msg, "content": content_list}
                    break

    return result


# ---------------------------------------------------------------------------
# adjust_params_for_non_streaming  (line 3364 in claude.ts)
# ---------------------------------------------------------------------------

#: Non-streaming requests support up to 64 k output tokens (10-min API limit).
MAX_NON_STREAMING_TOKENS = 64_000


def adjust_params_for_non_streaming(params: dict, max_tokens_cap: int) -> dict:
    """
    Cap max_tokens to max_tokens_cap and adjust the thinking budget accordingly.

    The API requires:  max_tokens > thinking.budget_tokens
    so we shrink budget_tokens to (capped_max - 1) when it would overflow.

    Returns a *new* dict; the input is not mutated.
    """
    capped_max_tokens = min(params.get("max_tokens", max_tokens_cap), max_tokens_cap)

    adjusted = dict(params)
    thinking = adjusted.get("thinking")

    if (
        isinstance(thinking, dict)
        and thinking.get("type") == "enabled"
        and thinking.get("budget_tokens") is not None
    ):
        adjusted["thinking"] = {
            **thinking,
            "budget_tokens": min(
                thinking["budget_tokens"],
                capped_max_tokens - 1,  # Must be strictly less than max_tokens
            ),
        }

    adjusted["max_tokens"] = capped_max_tokens
    return adjusted


# ---------------------------------------------------------------------------
# get_max_output_tokens_for_model  (line 3399 in claude.ts)
# ---------------------------------------------------------------------------

def get_max_output_tokens_for_model(model: str) -> int:
    """
    Return the effective max output tokens for ``model``.

    Reads CLAUDE_CODE_MAX_OUTPUT_TOKENS env var; falls back to a model-based
    default.  Mirrors the TS implementation (simplified: skips GrowthBook slot
    reservation cap which is internal-Anthropic-only).
    """
    # Default token limits per model family
    default_limits: dict = {
        "haiku":  8_192,
        "sonnet": 64_000,
        "opus":   32_000,
    }
    upper_limits: dict = {
        "haiku":  8_192,
        "sonnet": 64_000,
        "opus":   32_000,
    }

    model_lower = model.lower()
    default_tokens = 8_192
    upper_limit = 64_000
    for key, val in default_limits.items():
        if key in model_lower:
            default_tokens = val
            upper_limit = upper_limits[key]
            break

    # Env-var override
    env_val = os.environ.get("CLAUDE_CODE_MAX_OUTPUT_TOKENS")
    if env_val:
        try:
            parsed = int(env_val)
            if 1 <= parsed <= upper_limit:
                return parsed
        except ValueError:
            pass

    return default_tokens


# ---------------------------------------------------------------------------
# execute_non_streaming_request  (line 818 in claude.ts)
# ---------------------------------------------------------------------------

async def execute_non_streaming_request(
    messages: List[dict],
    system_prompt: Optional[List[str]] = None,
    tools: Optional[list] = None,
    options: Optional[QueryOptions] = None,
    signal: Any = None,
    originating_request_id: Optional[str] = None,
) -> AssistantMessage:
    """
    Non-streaming API request with retry and per-attempt timeout.

    Mirrors executeNonStreamingRequest from claude.ts:
      - Caps max_tokens via adjust_params_for_non_streaming
      - Uses MAX_NON_STREAMING_TOKENS (64k) as the ceiling
      - Timeout: API_TIMEOUT_MS env var, or 300s (120s in remote sessions)

    Returns an AssistantMessage dict.  Unlike the TS generator version we
    return the final result directly; system-event emission is handled by
    the caller if needed.
    """
    from claude_code.utils.env_utils import is_env_truthy

    opts = options or {}
    model = opts.get("model") or get_small_fast_model()
    max_retries = opts.get("max_retries", 2)
    source = opts.get("source", "execute_non_streaming_request")

    # Determine timeout
    env_timeout = os.environ.get("API_TIMEOUT_MS")
    if env_timeout and env_timeout.isdigit():
        timeout_s = int(env_timeout) / 1000.0
    elif is_env_truthy(os.environ.get("CLAUDE_CODE_REMOTE")):
        timeout_s = 120.0
    else:
        timeout_s = 300.0

    base_params: dict = {
        "model": model,
        "max_tokens": opts.get("max_tokens", get_max_output_tokens_for_model(model)),
        "messages": messages,
    }

    system = build_system_prompt_blocks(system_prompt or [])
    if system:
        base_params["system"] = system
    if tools:
        base_params["tools"] = tools

    # Apply the non-streaming token cap
    params = adjust_params_for_non_streaming(base_params, MAX_NON_STREAMING_TOKENS)

    async def _call():
        client = await get_anthropic_client(max_retries=0)
        try:
            response = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: client.beta.messages.create(**params),
                ),
                timeout=timeout_s,
            )
        except AttributeError:
            response = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: client.messages.create(**params),
                ),
                timeout=timeout_s,
            )
        return response

    response = await with_api_retry(_call, max_retries=max_retries, source=source)

    content = getattr(response, "content", [])
    stop_reason = getattr(response, "stop_reason", None)
    usage = getattr(response, "usage", {})
    if hasattr(usage, "__dict__"):
        usage = vars(usage)

    return {
        "role": "assistant",
        "content": content,
        "stop_reason": stop_reason,
        "usage": usage,
        "request_id": originating_request_id,
    }
