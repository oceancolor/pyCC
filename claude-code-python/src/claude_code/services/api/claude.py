"""
Claude API query functions. Ported from services/api/claude.ts (3419 lines → core).
Implements: queryHaiku, queryWithModel, queryModelWithoutStreaming,
            queryModelWithStreaming, buildSystemPromptBlocks, etc.
"""
from __future__ import annotations
import asyncio
import logging
import os
from typing import Any, AsyncGenerator, AsyncIterator, Dict, List, Optional, TypedDict, Union

from claude_code.services.api.client import get_anthropic_client
from claude_code.services.api.with_retry import with_api_retry
from claude_code.utils.model.model import get_small_fast_model

log = logging.getLogger(__name__)


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
    request_id: Optional[str]
    type: str
    uuid: str
    timestamp: str


class NonNullableUsage(TypedDict, total=False):
    """Full usage structure matching TS NonNullableUsage interface."""
    input_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    output_tokens: int
    server_tool_use: Dict[str, int]  # {web_search_requests, web_fetch_requests}
    service_tier: str
    cache_creation: Dict[str, int]  # {ephemeral_1h_input_tokens, ephemeral_5m_input_tokens}
    inference_geo: str
    iterations: list
    speed: str


def get_prompt_caching_enabled(model: str) -> bool:
    """
    Check if prompt caching should be enabled for this model.
    Mirrors getPromptCachingEnabled from claude.ts — supports per-model disable env vars.
    """
    from claude_code.utils.env_utils import is_env_truthy
    # Global disable
    if is_env_truthy(os.environ.get("DISABLE_PROMPT_CACHING")):
        return False
    # Per-model disables
    if is_env_truthy(os.environ.get("DISABLE_PROMPT_CACHING_HAIKU")):
        try:
            small_fast = get_small_fast_model()
            if model == small_fast:
                return False
        except Exception:
            pass
    if is_env_truthy(os.environ.get("DISABLE_PROMPT_CACHING_SONNET")):
        try:
            from claude_code.utils.model.model import get_default_sonnet_model
            default_sonnet = get_default_sonnet_model()
            if model == default_sonnet:
                return False
        except Exception:
            pass
    if is_env_truthy(os.environ.get("DISABLE_PROMPT_CACHING_OPUS")):
        try:
            from claude_code.utils.model.model import get_default_opus_model
            default_opus = get_default_opus_model()
            if model == default_opus:
                return False
        except Exception:
            pass
    return True


def build_system_prompt_blocks(
    system_prompt: Union[List[str], str],
    enable_prompt_caching: bool = False,
    options: Optional[dict] = None,
) -> list:
    """
    Build API-format system prompt blocks from a string list.

    Extended signature matches buildSystemPromptBlocks from claude.ts:
      - enable_prompt_caching: whether to add cache_control markers
      - options: {skip_global_cache_for_system_prompt, query_source}
    """
    if isinstance(system_prompt, str):
        system_prompt = [system_prompt] if system_prompt else []

    opts = options or {}
    skip_global = opts.get("skip_global_cache_for_system_prompt", False)
    query_source = opts.get("query_source")

    blocks = []
    for s in system_prompt:
        if not s:
            continue
        block: dict = {"type": "text", "text": s}
        if enable_prompt_caching and not skip_global:
            block["cache_control"] = get_cache_control(query_source=query_source)
        blocks.append(block)
    return blocks


def _EMPTY_NON_NULLABLE_USAGE() -> dict:
    """Return a zeroed NonNullableUsage dict (matches EMPTY_USAGE from logging.ts)."""
    return {
        "input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "output_tokens": 0,
        "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0},
        "service_tier": "standard",
        "cache_creation": {
            "ephemeral_1h_input_tokens": 0,
            "ephemeral_5m_input_tokens": 0,
        },
        "inference_geo": "",
        "iterations": [],
        "speed": "standard",
    }


def update_usage(current: dict, delta: Optional[dict]) -> dict:
    """
    Update usage statistics with new values from streaming API events.

    Mirrors updateUsage from claude.ts.  Input-related tokens are only updated
    when the incoming value is > 0 (message_delta may send explicit 0s for
    fields already set in message_start).
    """
    if not delta:
        return dict(current)

    def _positive(val: Any) -> bool:
        return val is not None and val > 0

    result = dict(current)

    # Input tokens: only update when explicitly positive
    if _positive(delta.get("input_tokens")):
        result["input_tokens"] = delta["input_tokens"]
    if _positive(delta.get("cache_creation_input_tokens")):
        result["cache_creation_input_tokens"] = delta["cache_creation_input_tokens"]
    if _positive(delta.get("cache_read_input_tokens")):
        result["cache_read_input_tokens"] = delta["cache_read_input_tokens"]

    # Output tokens: always take latest value
    if delta.get("output_tokens") is not None:
        result["output_tokens"] = delta["output_tokens"]

    # server_tool_use (nested)
    delta_stu = delta.get("server_tool_use", {})
    cur_stu = result.get("server_tool_use", {"web_search_requests": 0, "web_fetch_requests": 0})
    result["server_tool_use"] = {
        "web_search_requests": delta_stu.get("web_search_requests") or cur_stu.get("web_search_requests", 0),
        "web_fetch_requests": delta_stu.get("web_fetch_requests") or cur_stu.get("web_fetch_requests", 0),
    }

    # service_tier: keep current unless delta provides one
    if delta.get("service_tier"):
        result["service_tier"] = delta["service_tier"]
    elif "service_tier" not in result:
        result["service_tier"] = "standard"

    # cache_creation (nested)
    delta_cc = delta.get("cache_creation", {})
    cur_cc = result.get("cache_creation", {"ephemeral_1h_input_tokens": 0, "ephemeral_5m_input_tokens": 0})
    result["cache_creation"] = {
        "ephemeral_1h_input_tokens": delta_cc.get("ephemeral_1h_input_tokens") or cur_cc.get("ephemeral_1h_input_tokens", 0),
        "ephemeral_5m_input_tokens": delta_cc.get("ephemeral_5m_input_tokens") or cur_cc.get("ephemeral_5m_input_tokens", 0),
    }

    # inference_geo, iterations, speed: use latest
    if delta.get("inference_geo") is not None:
        result["inference_geo"] = delta["inference_geo"]
    if delta.get("iterations") is not None:
        result["iterations"] = delta["iterations"]
    if delta.get("speed") is not None:
        result["speed"] = delta["speed"]

    return result


def accumulate_usage(total_usage: dict, message_usage: dict) -> dict:
    """
    Accumulate usage from one message into a total usage object.
    Mirrors accumulateUsage from claude.ts — sums token counts, uses latest
    for tier/geo/iterations/speed.
    """
    return {
        "input_tokens": total_usage.get("input_tokens", 0) + message_usage.get("input_tokens", 0),
        "cache_creation_input_tokens": (
            total_usage.get("cache_creation_input_tokens", 0)
            + message_usage.get("cache_creation_input_tokens", 0)
        ),
        "cache_read_input_tokens": (
            total_usage.get("cache_read_input_tokens", 0)
            + message_usage.get("cache_read_input_tokens", 0)
        ),
        "output_tokens": (
            total_usage.get("output_tokens", 0)
            + message_usage.get("output_tokens", 0)
        ),
        "server_tool_use": {
            "web_search_requests": (
                total_usage.get("server_tool_use", {}).get("web_search_requests", 0)
                + message_usage.get("server_tool_use", {}).get("web_search_requests", 0)
            ),
            "web_fetch_requests": (
                total_usage.get("server_tool_use", {}).get("web_fetch_requests", 0)
                + message_usage.get("server_tool_use", {}).get("web_fetch_requests", 0)
            ),
        },
        "service_tier": message_usage.get("service_tier", total_usage.get("service_tier", "standard")),
        "cache_creation": {
            "ephemeral_1h_input_tokens": (
                total_usage.get("cache_creation", {}).get("ephemeral_1h_input_tokens", 0)
                + message_usage.get("cache_creation", {}).get("ephemeral_1h_input_tokens", 0)
            ),
            "ephemeral_5m_input_tokens": (
                total_usage.get("cache_creation", {}).get("ephemeral_5m_input_tokens", 0)
                + message_usage.get("cache_creation", {}).get("ephemeral_5m_input_tokens", 0)
            ),
        },
        "inference_geo": message_usage.get("inference_geo", total_usage.get("inference_geo", "")),
        "iterations": message_usage.get("iterations", total_usage.get("iterations", [])),
        "speed": message_usage.get("speed", total_usage.get("speed", "standard")),
    }


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


async def verify_api_key(api_key: str, is_non_interactive_session: bool = False) -> bool:
    """
    Verify an API key by making a minimal test request.
    Mirrors verifyApiKey from claude.ts: skips verification in non-interactive mode.
    """
    if is_non_interactive_session:
        return True
    try:
        client = await get_anthropic_client(api_key=api_key, max_retries=0)
        model = get_small_fast_model()
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.messages.create(
                model=model,
                max_tokens=1,
                messages=[{"role": "user", "content": "test"}],
                temperature=1,
                metadata=get_api_metadata(),
                **get_extra_body_params(),
            )
        )
        return True
    except Exception as e:
        msg = str(e)
        if 'authentication_error' in msg and 'invalid x-api-key' in msg:
            return False
        raise


def get_api_metadata() -> dict:
    """
    Assemble API metadata dict sent with every request.
    Mirrors getAPIMetadata from claude.ts.
    Reads CLAUDE_CODE_EXTRA_METADATA env var for additional fields.
    """
    extra: dict = {}
    extra_str = os.environ.get("CLAUDE_CODE_EXTRA_METADATA")
    if extra_str:
        try:
            import json as _jm
            parsed = _jm.loads(extra_str)
            if isinstance(parsed, dict):
                extra = parsed
            else:
                log.error(
                    "CLAUDE_CODE_EXTRA_METADATA must be a JSON object, got: %s",
                    extra_str,
                )
        except (ValueError, Exception) as exc:
            log.error("Error parsing CLAUDE_CODE_EXTRA_METADATA: %s", exc)

    try:
        from claude_code.utils.config import get_or_create_user_id
        device_id = get_or_create_user_id()
    except Exception:
        device_id = ""

    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    account_uuid = ""

    import json as _json
    user_id_payload = {**extra, "device_id": device_id, "account_uuid": account_uuid, "session_id": session_id}
    return {
        "user_id": _json.dumps(user_id_payload, separators=(",", ":")),
    }


async def query_model_with_streaming(  # type: ignore[override]
    messages: List[dict],
    system_prompt: Optional[List[str]] = None,
    tools: Optional[list] = None,
    options: Optional[QueryOptions] = None,
    signal: Any = None,
) -> AsyncGenerator[dict, None]:
    """
    Stream response from Claude API with retry and non-streaming fallback.

    Yields dicts of the form:
      {"type": "stream_event", "event": <raw_event>}
      {"type": "assistant", ...}   — assembled assistant message (on content_block_stop)
      {"type": "error", "error": <str>}

    This is a simplified Python equivalent of the full queryModel generator from
    claude.ts.  The streaming watchdog, GrowthBook feature flags, and first-party
    analytics are omitted; the core retry/fallback loop is faithfully reproduced.
    """
    opts = options or {}
    model = opts.get("model") or get_small_fast_model()
    max_tokens = opts.get("max_tokens", get_max_output_tokens_for_model(model))
    max_retries = opts.get("max_retries", 2)
    source = opts.get("source", "stream")
    enable_prompt_caching = opts.get("enable_prompt_caching", get_prompt_caching_enabled(model))

    system = build_system_prompt_blocks(system_prompt or [], enable_prompt_caching=enable_prompt_caching)

    params: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system:
        params["system"] = system
    if tools:
        params["tools"] = tools
    extra = get_extra_body_params()
    params.update(extra)

    loop = asyncio.get_event_loop()
    content_blocks: dict = {}
    usage = _EMPTY_NON_NULLABLE_USAGE()
    partial_message: Optional[dict] = None
    stop_reason: Optional[str] = None
    new_messages: List[dict] = []
    stream_obj = None

    async def _cleanup_stream() -> None:
        nonlocal stream_obj
        if stream_obj is not None:
            cleanup_stream(stream_obj)
            stream_obj = None

    # --- attempt streaming ---
    try:
        client = await get_anthropic_client(max_retries=0)
        streaming_params = {**params, "stream": True}
        stream_obj = await loop.run_in_executor(
            None, lambda: client.messages.create(**streaming_params)
        )
    except Exception as stream_err:
        # Streaming endpoint unavailable — fall back to non-streaming
        log.warning("Streaming unavailable, falling back to non-streaming: %s", stream_err)
        await _cleanup_stream()
        try:
            ns_params = adjust_params_for_non_streaming(params, MAX_NON_STREAMING_TOKENS)
            client = await get_anthropic_client(max_retries=max_retries)
            response = await with_api_retry(
                lambda: loop.run_in_executor(
                    None,
                    lambda: client.messages.create(**ns_params),
                ),
                max_retries=max_retries,
                source=source,
            )
            content = getattr(response, "content", [])
            stop_r = getattr(response, "stop_reason", None)
            usage_obj = getattr(response, "usage", {})
            if hasattr(usage_obj, "__dict__"):
                usage_obj = vars(usage_obj)
            m = {
                "type": "assistant",
                "role": "assistant",
                "content": content,
                "stop_reason": stop_r,
                "usage": usage_obj,
            }
            yield m
        except Exception as fb_err:
            yield {"type": "error", "error": str(fb_err)}
        return

    # --- process streaming events ---
    try:
        for part in stream_obj:
            part_type = getattr(part, "type", "unknown")

            if part_type == "message_start":
                msg_data = getattr(part, "message", None)
                if msg_data is not None:
                    partial_message = vars(msg_data) if hasattr(msg_data, "__dict__") else dict(msg_data)
                    raw_usage = getattr(msg_data, "usage", {})
                    usage_dict = vars(raw_usage) if hasattr(raw_usage, "__dict__") else (raw_usage or {})
                    usage = update_usage(usage, usage_dict)

            elif part_type == "content_block_start":
                idx = getattr(part, "index", 0)
                cb = getattr(part, "content_block", None)
                if cb is not None:
                    cb_dict = vars(cb) if hasattr(cb, "__dict__") else dict(cb)
                    cb_type = cb_dict.get("type", "")
                    if cb_type == "tool_use":
                        cb_dict["input"] = ""
                    elif cb_type == "text":
                        cb_dict["text"] = ""
                    elif cb_type == "thinking":
                        cb_dict["thinking"] = ""
                        cb_dict["signature"] = ""
                    content_blocks[idx] = cb_dict

            elif part_type == "content_block_delta":
                idx = getattr(part, "index", 0)
                delta = getattr(part, "delta", None)
                if delta is not None and idx in content_blocks:
                    delta_type = getattr(delta, "type", "")
                    cb = content_blocks[idx]
                    if delta_type == "text_delta":
                        cb["text"] = cb.get("text", "") + getattr(delta, "text", "")
                    elif delta_type == "input_json_delta":
                        cb["input"] = cb.get("input", "") + getattr(delta, "partial_json", "")
                    elif delta_type == "thinking_delta":
                        cb["thinking"] = cb.get("thinking", "") + getattr(delta, "thinking", "")
                    elif delta_type == "signature_delta":
                        cb["signature"] = getattr(delta, "signature", "")

            elif part_type == "content_block_stop":
                idx = getattr(part, "index", 0)
                cb = content_blocks.get(idx)
                if cb is not None and partial_message is not None:
                    # Parse tool_use input JSON
                    if cb.get("type") == "tool_use" and isinstance(cb.get("input"), str):
                        try:
                            import json as _j
                            cb["input"] = _j.loads(cb["input"]) if cb["input"] else {}
                        except Exception:
                            pass

                    import uuid as _uuid
                    m: dict = {
                        "type": "assistant",
                        "role": "assistant",
                        "message": {
                            **partial_message,
                            "content": [cb],
                        },
                        "uuid": str(_uuid.uuid4()),
                        "timestamp": __import__('datetime').datetime.utcnow().isoformat() + "Z",
                    }
                    new_messages.append(m)
                    yield m

            elif part_type == "message_delta":
                raw_usage = getattr(part, "usage", None)
                if raw_usage is not None:
                    usage_dict = vars(raw_usage) if hasattr(raw_usage, "__dict__") else dict(raw_usage)
                    usage = update_usage(usage, usage_dict)

                delta_obj = getattr(part, "delta", None)
                stop_reason = getattr(delta_obj, "stop_reason", None) if delta_obj else None

                # Write final usage + stop_reason back to last yielded message
                if new_messages:
                    last = new_messages[-1]
                    if "message" in last:
                        last["message"]["usage"] = usage
                        last["message"]["stop_reason"] = stop_reason

            yield {"type": "stream_event", "event": part}

        # Guard: if stream completed without any content and no stop reason, try fallback
        if not partial_message or (not new_messages and not stop_reason):
            log.error("Stream completed without useful events; attempting non-streaming fallback")
            raise RuntimeError("Stream ended without receiving any events")

    except Exception as streaming_err:
        await _cleanup_stream()
        from claude_code.utils.env_utils import is_env_truthy
        if is_env_truthy(os.environ.get("CLAUDE_CODE_DISABLE_NONSTREAMING_FALLBACK")):
            yield {"type": "error", "error": str(streaming_err)}
            return

        log.warning("Streaming error, falling back to non-streaming: %s", streaming_err)
        try:
            ns_params = adjust_params_for_non_streaming(params, MAX_NON_STREAMING_TOKENS)
            client = await get_anthropic_client(max_retries=0)
            response = await with_api_retry(
                lambda: loop.run_in_executor(
                    None,
                    lambda: client.messages.create(**ns_params),
                ),
                max_retries=max_retries,
                source=source,
            )
            content = getattr(response, "content", [])
            stop_r = getattr(response, "stop_reason", None)
            usage_obj = getattr(response, "usage", {})
            if hasattr(usage_obj, "__dict__"):
                usage_obj = vars(usage_obj)
            m = {
                "type": "assistant",
                "role": "assistant",
                "content": content,
                "stop_reason": stop_r,
                "usage": usage_obj,
            }
            yield m
        except Exception as fb_err:
            yield {"type": "error", "error": str(fb_err)}
    finally:
        await _cleanup_stream()


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


# ===========================================================================
# cleanup_stream  (line ~2682 in claude.ts)
# ===========================================================================

def cleanup_stream(stream: Any) -> None:
    """
    Clean up stream resources to prevent memory/socket leaks.
    Mirrors cleanupStream from claude.ts.

    The stream object may be an Anthropic SDK Stream or any object with a
    ``controller`` attribute that has a ``signal`` property.
    """
    if stream is None:
        return
    try:
        controller = getattr(stream, "controller", None)
        if controller is not None:
            signal = getattr(controller, "signal", None)
            aborted = getattr(signal, "aborted", True)
            if not aborted:
                controller.abort()
    except Exception:
        pass

    # Python httpx / aiohttp streams
    try:
        close_fn = getattr(stream, "close", None)
        if close_fn is not None:
            close_fn()
    except Exception:
        pass


# ===========================================================================
# token_count_from_last_api_response  (utils/tokens.ts line 55)
# ===========================================================================

def get_token_count_from_usage(usage: dict) -> int:
    """
    Calculate total context window tokens from usage dict.
    Includes input_tokens + cache tokens + output_tokens.
    Mirrors getTokenCountFromUsage from utils/tokens.ts.
    """
    if not usage:
        return 0
    return (
        usage.get("input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
        + usage.get("output_tokens", 0)
    )


def token_count_from_last_api_response(messages: List[dict]) -> int:
    """
    Get total context window token count from the last assistant message
    that has real (non-zero) usage data.

    Mirrors tokenCountFromLastAPIResponse from utils/tokens.ts.
    Walks messages in reverse until it finds one with usage.
    Returns 0 when no messages have usage data.
    """
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        msg_type = msg.get("type", msg.get("role", ""))
        if msg_type != "assistant":
            continue

        # Accept both flat dicts and nested {message: {...}} shapes
        inner = msg.get("message", msg)
        usage = inner.get("usage")
        if not usage:
            continue

        # Normalise SDK usage objects to plain dicts
        if hasattr(usage, "__dict__"):
            usage = vars(usage)

        count = get_token_count_from_usage(usage)
        if count > 0:
            return count

    return 0


# ===========================================================================
# configure_effort_params  (line ~444 in claude.ts)
# ===========================================================================

# Beta header constant (matches src/constants/betas.js)
EFFORT_BETA_HEADER = "interleaved-thinking-2025-05-14"


def configure_effort_params(
    effort_value: Optional[Any],  # EffortValue = str | float | None
    output_config: dict,
    extra_body_params: dict,
    betas: List[str],
    model: str,
) -> None:
    """
    Configure effort parameters for an API request.
    Mirrors configureEffortParams from claude.ts.

    Rules:
    - If model doesn't support effort OR 'effort' already in output_config: no-op.
    - effort_value is None  → push EFFORT_BETA_HEADER (model decides)
    - effort_value is str   → set output_config['effort'] + push header
    - effort_value is float → ant-only numeric override via anthropic_internal
    """
    if not _model_supports_effort(model) or "effort" in output_config:
        return

    if effort_value is None:
        if EFFORT_BETA_HEADER not in betas:
            betas.append(EFFORT_BETA_HEADER)
    elif isinstance(effort_value, str):
        output_config["effort"] = effort_value
        if EFFORT_BETA_HEADER not in betas:
            betas.append(EFFORT_BETA_HEADER)
    elif isinstance(effort_value, (int, float)):
        # Ant-only: numeric override via anthropic_internal
        if os.environ.get("USER_TYPE") == "ant":
            existing_internal = extra_body_params.get("anthropic_internal") or {}
            extra_body_params["anthropic_internal"] = {
                **existing_internal,
                "effort_override": effort_value,
            }


def _model_supports_effort(model: str) -> bool:
    """
    Simplified effort-support check.
    Mirrors modelSupportsEffort from utils/effort.ts.
    Claude 3.7+ sonnet and opus models support effort.
    """
    ml = model.lower()
    # claude-3-7-sonnet and later support effort
    if "claude-3-7" in ml or "claude-sonnet-4" in ml or "claude-opus-4" in ml:
        return True
    # claude-3-5-sonnet also supports effort per the API
    if "claude-3-5-sonnet" in ml:
        return True
    return False


# ===========================================================================
# stream_with_retry / create_with_retry  (pattern from claude.ts withRetry usage)
# ===========================================================================

async def stream_with_retry(
    params: dict,
    source: str = "stream",
    max_retries: int = 3,
    fallback_to_non_streaming: bool = True,
    signal: Any = None,
) -> AsyncGenerator[dict, None]:
    """
    Stream Anthropic API messages with automatic retry.
    On streaming failure, optionally falls back to non-streaming.

    Yields dicts with keys:
      - type='stream_event' + event=<raw SDK event>
      - type='assistant'    + content/usage/stop_reason (on block completion)
      - type='error'        + error=<str>
    """
    async for event in query_model_with_streaming(
        messages=params.get("messages", []),
        system_prompt=params.get("system"),
        tools=params.get("tools"),
        options={
            "model": params.get("model", get_small_fast_model()),
            "max_tokens": params.get("max_tokens", 4096),
            "max_retries": max_retries,
            "source": source,
        },
        signal=signal,
    ):
        yield event


async def create_with_retry(
    params: dict,
    source: str = "non_streaming",
    max_retries: int = 3,
    signal: Any = None,
) -> dict:
    """
    Non-streaming Anthropic API call with automatic retry.
    Mirrors the withRetry(getClient, async (client) => client.beta.messages.create(...))
    pattern used throughout claude.ts.

    Returns an AssistantMessage-shaped dict.
    """
    return await execute_non_streaming_request(
        messages=params.get("messages", []),
        system_prompt=params.get("system"),
        tools=params.get("tools"),
        options={
            "model": params.get("model", get_small_fast_model()),
            "max_tokens": params.get("max_tokens", 4096),
            "max_retries": max_retries,
            "source": source,
        },
        signal=signal,
    )
