# 原始 TS: utils/auth.ts + utils/authPortable.ts + utils/authFileDescriptor.ts
"""Authentication utilities for Claude Code."""

from .auth import (
    get_anthropic_api_key,
    get_auth_token_source,
    get_subscription_type,
    is_claude_ai_subscriber,
    AuthTokenSource,
)
from .auth_portable import (
    maybe_remove_api_key_from_macos_keychain,
    normalize_api_key_for_config,
)
from .auth_file_descriptor import (
    get_api_key_from_file_descriptor,
    get_oauth_token_from_file_descriptor,
    maybe_persist_token_for_subprocesses,
    CCR_OAUTH_TOKEN_PATH,
    CCR_API_KEY_PATH,
    CCR_SESSION_INGRESS_TOKEN_PATH,
)

__all__ = [
    "get_anthropic_api_key",
    "get_auth_token_source",
    "get_subscription_type",
    "is_claude_ai_subscriber",
    "AuthTokenSource",
    "maybe_remove_api_key_from_macos_keychain",
    "normalize_api_key_for_config",
    "get_api_key_from_file_descriptor",
    "get_oauth_token_from_file_descriptor",
    "maybe_persist_token_for_subprocesses",
    "CCR_OAUTH_TOKEN_PATH",
    "CCR_API_KEY_PATH",
    "CCR_SESSION_INGRESS_TOKEN_PATH",
]
