"""
Anthropic API client factory. Ported from services/api/client.ts (395 lines → core).
Supports: firstParty, bedrock, vertex, foundry, hunyuan
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

CLIENT_REQUEST_ID_HEADER = "x-client-request-id"

# ─────────────────────────────────────────────────────────────────────────────
# Hunyuan OpenAI-compat client
# Wraps /v1/chat/completions so the rest of the codebase can call
# client.messages.create(**anthropic_kwargs) unchanged.
# ─────────────────────────────────────────────────────────────────────────────

class _HunyuanMessages:
    """Mimics anthropic.resources.Messages so callers use client.messages.create()."""

    def __init__(self, api_key: str, base_url: str, model: str, timeout: float) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def create(self, **kwargs: Any) -> "_HunyuanResponse":
        """Synchronous call — mirrors anthropic.Anthropic().messages.create()."""
        import httpx
        payload = self._to_openai(kwargs)
        resp = httpx.post(
            f"{self._base_url}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return self._from_openai(resp.json())

    # ── format converters ────────────────────────────────────────────────────

    def _to_openai(self, kwargs: dict) -> dict:
        """Convert Anthropic messages.create kwargs → OpenAI chat/completions body."""
        messages = list(kwargs.get("messages", []))

        # Anthropic system prompt → system message prepended
        system = kwargs.get("system")
        if system:
            if isinstance(system, list):
                # list of {type:'text', text:'...'} blocks
                sys_text = "\n\n".join(
                    b.get("text", "") if isinstance(b, dict) else str(b)
                    for b in system
                )
            else:
                sys_text = str(system)
            messages = [{"role": "system", "content": sys_text}] + messages

        # Flatten any content-block lists in messages
        openai_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                # Anthropic content blocks → plain text + tool results
                if role == "tool":
                    # tool result message
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            result_content = block.get("content", "")
                            if isinstance(result_content, list):
                                result_content = "\n".join(
                                    b.get("text", "") if isinstance(b, dict) else str(b)
                                    for b in result_content
                                )
                            openai_messages.append({
                                "role": "tool",
                                "tool_call_id": block.get("tool_use_id", ""),
                                "content": result_content,
                            })
                    continue
                else:
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                            elif block.get("type") == "tool_use":
                                # assistant tool_use block — handled separately below
                                pass
                    content = "\n".join(text_parts)

            # Check if this is an assistant message with tool_use blocks
            raw_content = msg.get("content", "")
            tool_calls = None
            if role == "assistant" and isinstance(raw_content, list):
                tool_calls_list = []
                for block in raw_content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_calls_list.append({
                            "id": block.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": json.dumps(block.get("input", {})),
                            },
                        })
                if tool_calls_list:
                    tool_calls = tool_calls_list
                    content = None  # tool_use messages have null content

            entry: dict = {"role": role, "content": content}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            openai_messages.append(entry)

        payload: dict = {
            "model": self._model,
            "messages": openai_messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
        }

        # Convert Anthropic tools → OpenAI tools
        anthropic_tools = kwargs.get("tools")
        if anthropic_tools:
            openai_tools = []
            for t in anthropic_tools:
                if isinstance(t, dict):
                    openai_tools.append({
                        "type": "function",
                        "function": {
                            "name": t.get("name", ""),
                            "description": t.get("description", ""),
                            "parameters": t.get("input_schema", {}),
                        },
                    })
                else:
                    # anthropic SDK tool object
                    openai_tools.append({
                        "type": "function",
                        "function": {
                            "name": getattr(t, "name", ""),
                            "description": getattr(t, "description", ""),
                            "parameters": getattr(t, "input_schema", {}),
                        },
                    })
            if openai_tools:
                payload["tools"] = openai_tools
                payload["tool_choice"] = "auto"

        temperature = kwargs.get("temperature")
        if temperature is not None:
            payload["temperature"] = temperature

        return payload

    def _from_openai(self, data: dict) -> "_HunyuanResponse":
        """Convert OpenAI chat.completion response → Anthropic-style response object."""
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        finish_reason = choice.get("finish_reason", "stop")
        usage_raw = data.get("usage", {})

        # Build Anthropic content blocks
        content_blocks: list = []
        text = message.get("content")
        if text:
            content_blocks.append({"type": "text", "text": text})

        tool_calls = message.get("tool_calls") or []
        for tc in tool_calls:
            fn = tc.get("function", {})
            try:
                input_data = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                input_data = {}
            content_blocks.append({
                "type": "tool_use",
                "id": tc.get("id", ""),
                "name": fn.get("name", ""),
                "input": input_data,
            })

        # Map finish_reason → Anthropic stop_reason
        stop_reason_map = {
            "stop": "end_turn",
            "tool_calls": "tool_use",
            "length": "max_tokens",
            "content_filter": "end_turn",
        }
        stop_reason = stop_reason_map.get(finish_reason, "end_turn")

        usage = {
            "input_tokens": usage_raw.get("prompt_tokens", 0),
            "output_tokens": usage_raw.get("completion_tokens", 0),
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }

        return _HunyuanResponse(
            content=content_blocks,
            stop_reason=stop_reason,
            usage=usage,
            model=data.get("model", self._model),
            id=data.get("id", ""),
        )


class _HunyuanResponse:
    """Minimal Anthropic Message-compatible response object."""

    def __init__(
        self,
        content: list,
        stop_reason: str,
        usage: dict,
        model: str = "",
        id: str = "",
    ) -> None:
        self.content = content
        self.stop_reason = stop_reason
        self.usage = _UsageObj(usage)
        self.model = model
        self.id = id
        self.role = "assistant"

    def __repr__(self) -> str:
        return (
            f"_HunyuanResponse(stop_reason={self.stop_reason!r}, "
            f"content_blocks={len(self.content)}, usage={vars(self.usage)})"
        )


class _UsageObj:
    def __init__(self, d: dict) -> None:
        self.input_tokens = d.get("input_tokens", 0)
        self.output_tokens = d.get("output_tokens", 0)
        self.cache_read_input_tokens = d.get("cache_read_input_tokens", 0)
        self.cache_creation_input_tokens = d.get("cache_creation_input_tokens", 0)

    def __repr__(self) -> str:
        return (
            f"Usage(in={self.input_tokens}, out={self.output_tokens}, "
            f"cache_read={self.cache_read_input_tokens})"
        )


class _HunyuanClient:
    """Drop-in for anthropic.Anthropic — exposes .messages and .beta.messages."""

    def __init__(self, api_key: str, base_url: str, model: str, timeout: float) -> None:
        self.messages = _HunyuanMessages(api_key, base_url, model, timeout)
        # beta.messages fallback — just delegate to self.messages
        self.beta = type("_Beta", (), {"messages": self.messages})()


# ─────────────────────────────────────────────────────────────────────────────
# Client factory
# ─────────────────────────────────────────────────────────────────────────────


class AnthropicClientConfig:
    def __init__(self, api_key: Optional[str] = None, max_retries: int = 2,
                 model: Optional[str] = None, source: Optional[str] = None):
        self.api_key = api_key
        self.max_retries = max_retries
        self.model = model
        self.source = source


async def get_anthropic_client(
    api_key: Optional[str] = None,
    max_retries: int = 2,
    model: Optional[str] = None,
    source: Optional[str] = None,
) -> Any:
    """
    Create and return an API client for the configured provider.

    Priority:
      1. Hunyuan  (HUNYUAN_API_KEY set)
      2. Bedrock  (provider == 'bedrock')
      3. Vertex   (provider == 'vertex')
      4. Anthropic firstParty (default)
    """
    # ── 1. Hunyuan ────────────────────────────────────────────────────────────
    hunyuan_key = os.environ.get("HUNYUAN_API_KEY", "")
    if hunyuan_key:
        hunyuan_base = os.environ.get(
            "HUNYUAN_BASE_URL", "https://api.hunyuan.cloud.tencent.com/v1"
        )
        hunyuan_model = (
            model
            or os.environ.get("HUNYUAN_MODEL", "hunyuan-turbos-latest")
        )
        timeout = int(os.environ.get("API_TIMEOUT_MS", str(600_000))) / 1000
        return _HunyuanClient(
            api_key=hunyuan_key,
            base_url=hunyuan_base,
            model=hunyuan_model,
            timeout=timeout,
        )

    # ── 2-4. Anthropic / Bedrock / Vertex ────────────────────────────────────
    from claude_code.utils.model.providers import get_api_provider
    provider = get_api_provider()

    resolved_key = (
        api_key
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        or ""
    )
    timeout = int(os.environ.get("API_TIMEOUT_MS", str(600_000))) / 1000

    try:
        import anthropic
        kwargs: dict = {
            "api_key": resolved_key,
            "max_retries": max_retries,
            "timeout": timeout,
            "default_headers": _build_default_headers(),
        }
        if provider == "bedrock":
            from anthropic import AnthropicBedrock
            return AnthropicBedrock(max_retries=max_retries)
        if provider == "vertex":
            from anthropic import AnthropicVertex
            project = os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID", "")
            region = os.environ.get("CLOUD_ML_REGION", "us-east5")
            return AnthropicVertex(project_id=project, region=region,
                                   max_retries=max_retries)
        return anthropic.Anthropic(**kwargs)
    except ImportError:
        return _SimpleHttpClient(resolved_key, timeout=timeout)


def _build_default_headers() -> dict:
    headers = {"x-app": "cli"}
    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if session_id:
        headers["X-Claude-Code-Session-Id"] = session_id
    container_id = os.environ.get("CLAUDE_CODE_CONTAINER_ID")
    if container_id:
        headers["x-claude-remote-container-id"] = container_id
    return headers


class _SimpleHttpClient:
    """Minimal fallback HTTP client when anthropic SDK not installed."""
    def __init__(self, api_key: str, timeout: float = 600):
        self.api_key = api_key
        self.timeout = timeout

    async def messages_create(self, **kwargs) -> dict:
        raise RuntimeError("anthropic SDK not installed. Run: pip install anthropic")
