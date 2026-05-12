"""
beta_session_tracing.py - Beta Session Tracing for Claude Code.

Port of TypeScript betaSessionTracing.ts.
"""

import hashlib
import json
import os
from typing import Any, Dict, Optional, Set

MAX_CONTENT_SIZE = 60 * 1024  # 60KB

_seen_hashes: Set[str] = set()
_last_reported_message_hash: Dict[str, str] = {}


def clear_beta_tracing_state() -> None:
    """Clear tracking state after compaction."""
    global _seen_hashes, _last_reported_message_hash
    _seen_hashes.clear()
    _last_reported_message_hash.clear()


def is_beta_tracing_enabled() -> bool:
    """Check if beta detailed tracing is enabled."""
    base_enabled = (
        os.environ.get('ENABLE_BETA_TRACING_DETAILED', '').lower() in ('1', 'true')
        and bool(os.environ.get('BETA_TRACING_ENDPOINT'))
    )

    if not base_enabled:
        return False

    if os.environ.get('USER_TYPE') != 'ant':
        try:
            from ...bootstrap.state import get_is_non_interactive_session
            from ...services.analytics.growthbook import get_feature_value_cached_may_be_stale
            return (
                get_is_non_interactive_session()
                or get_feature_value_cached_may_be_stale('tengu_trace_lantern', False)
            )
        except ImportError:
            return False

    return True


def truncate_content(
    content: str,
    max_size: int = MAX_CONTENT_SIZE,
) -> Dict[str, Any]:
    """Truncate content to fit within Honeycomb limits."""
    if len(content.encode('utf-8')) <= max_size:
        return {'content': content, 'truncated': False}
    return {
        'content': content[:max_size] + '\n\n[TRUNCATED - Content exceeds 60KB limit]',
        'truncated': True,
    }


def _short_hash(content: str) -> str:
    """Generate a short hash (first 12 hex chars of SHA-256)."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:12]


def _hash_system_prompt(system_prompt: str) -> str:
    return f"sp_{_short_hash(system_prompt)}"


def _hash_message(message: Any) -> str:
    content = json.dumps(getattr(message, 'message', {}).get('content', ''), ensure_ascii=False)
    return f"msg_{_short_hash(content)}"


def add_beta_interaction_attributes(span: Any, user_prompt: str) -> None:
    """Add beta attributes to an interaction span."""
    if not is_beta_tracing_enabled():
        return

    result = truncate_content(f"[USER PROMPT]\n{user_prompt}")
    attrs = {'new_context': result['content']}
    if result['truncated']:
        attrs['new_context_truncated'] = True
        attrs['new_context_original_length'] = len(user_prompt)
    if hasattr(span, 'set_attributes'):
        span.set_attributes(attrs)


def add_beta_llm_request_attributes(
    span: Any,
    new_context: Optional[Dict] = None,
    messages_for_api: Optional[list] = None,
) -> None:
    """Add beta attributes to an LLM request span."""
    if not is_beta_tracing_enabled():
        return

    if new_context and new_context.get('systemPrompt'):
        prompt = new_context['systemPrompt']
        prompt_hash = _hash_system_prompt(prompt)
        preview = prompt[:500]

        if hasattr(span, 'set_attribute'):
            span.set_attribute('system_prompt_hash', prompt_hash)
            span.set_attribute('system_prompt_preview', preview)
            span.set_attribute('system_prompt_length', len(prompt))

        if prompt_hash not in _seen_hashes:
            _seen_hashes.add(prompt_hash)


def add_beta_llm_response_attributes(
    end_attributes: Dict[str, Any],
    metadata: Optional[Dict] = None,
) -> None:
    """Add beta attributes to endLLMRequestSpan."""
    if not is_beta_tracing_enabled() or not metadata:
        return

    if metadata.get('modelOutput') is not None:
        result = truncate_content(metadata['modelOutput'])
        end_attributes['response.model_output'] = result['content']
        if result['truncated']:
            end_attributes['response.model_output_truncated'] = True
            end_attributes['response.model_output_original_length'] = len(metadata['modelOutput'])

    if os.environ.get('USER_TYPE') == 'ant' and metadata.get('thinkingOutput') is not None:
        result = truncate_content(metadata['thinkingOutput'])
        end_attributes['response.thinking_output'] = result['content']
        if result['truncated']:
            end_attributes['response.thinking_output_truncated'] = True
            end_attributes['response.thinking_output_original_length'] = len(metadata['thinkingOutput'])


def add_beta_tool_input_attributes(span: Any, tool_name: str, tool_input: str) -> None:
    """Add beta attributes to startToolSpan."""
    if not is_beta_tracing_enabled():
        return

    result = truncate_content(f"[TOOL INPUT: {tool_name}]\n{tool_input}")
    attrs = {'tool_input': result['content']}
    if result['truncated']:
        attrs['tool_input_truncated'] = True
        attrs['tool_input_original_length'] = len(tool_input)
    if hasattr(span, 'set_attributes'):
        span.set_attributes(attrs)


def add_beta_tool_result_attributes(
    end_attributes: Dict[str, Any],
    tool_name: Any,
    tool_result: str,
) -> None:
    """Add beta attributes to endToolSpan."""
    if not is_beta_tracing_enabled():
        return

    result = truncate_content(f"[TOOL RESULT: {tool_name}]\n{tool_result}")
    end_attributes['new_context'] = result['content']
    if result['truncated']:
        end_attributes['new_context_truncated'] = True
        end_attributes['new_context_original_length'] = len(tool_result)
