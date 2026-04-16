"""Subprocess environment - Python port of subprocessEnv.ts.

Builds a safe environment dict for child processes, optionally scrubbing
sensitive secrets (API keys, cloud credentials, GHA tokens).
"""

from __future__ import annotations

import os
from typing import Callable, Dict, Optional

# Variables to scrub when CLAUDE_CODE_SUBPROCESS_ENV_SCRUB is set.
# Mirrors the GHA_SUBPROCESS_SCRUB list in subprocessEnv.ts.
GHA_SUBPROCESS_SCRUB: tuple[str, ...] = (
    # Anthropic auth
    'ANTHROPIC_API_KEY',
    'CLAUDE_CODE_OAUTH_TOKEN',
    'ANTHROPIC_AUTH_TOKEN',
    'ANTHROPIC_FOUNDRY_API_KEY',
    'ANTHROPIC_CUSTOM_HEADERS',
    # OTLP exporter headers
    'OTEL_EXPORTER_OTLP_HEADERS',
    'OTEL_EXPORTER_OTLP_LOGS_HEADERS',
    'OTEL_EXPORTER_OTLP_METRICS_HEADERS',
    'OTEL_EXPORTER_OTLP_TRACES_HEADERS',
    # Cloud provider creds
    'AWS_SECRET_ACCESS_KEY',
    'AWS_SESSION_TOKEN',
    'AWS_BEARER_TOKEN_BEDROCK',
    'GOOGLE_APPLICATION_CREDENTIALS',
    'AZURE_CLIENT_SECRET',
    'AZURE_CLIENT_CERTIFICATE_PATH',
    # GitHub Actions OIDC
    'ACTIONS_ID_TOKEN_REQUEST_TOKEN',
    'ACTIONS_ID_TOKEN_REQUEST_URL',
    # GitHub Actions runtime tokens
    'ACTIONS_RUNTIME_TOKEN',
    'ACTIONS_RUNTIME_URL',
    # claude-code-action-specific
    'ALL_INPUTS',
    'OVERRIDE_GITHUB_TOKEN',
    'DEFAULT_WORKFLOW_TOKEN',
    'SSH_SIGNING_KEY',
)

_upstream_proxy_env_fn: Optional[Callable[[], Dict[str, str]]] = None


def register_upstream_proxy_env_fn(fn: Callable[[], Dict[str, str]]) -> None:
    """Wire up the CCR upstream proxy env function (called from init)."""
    global _upstream_proxy_env_fn
    _upstream_proxy_env_fn = fn


def _is_env_truthy(value: Optional[str]) -> bool:
    return bool(value) and value.lower() not in ('0', 'false', 'no', '')


def build_subprocess_env(extra_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Return a copy of os.environ suitable for subprocess spawning.

    If CLAUDE_CODE_SUBPROCESS_ENV_SCRUB is set, sensitive variables are removed.
    If a CCR upstream proxy fn is registered, its vars are merged in.

    *extra_env* is merged on top after scrubbing.
    """
    proxy_env = _upstream_proxy_env_fn() if _upstream_proxy_env_fn else {}

    base: Dict[str, str] = {k: v for k, v in os.environ.items()}
    base.update(proxy_env)

    if _is_env_truthy(os.environ.get('CLAUDE_CODE_SUBPROCESS_ENV_SCRUB')):
        for key in GHA_SUBPROCESS_SCRUB:
            base.pop(key, None)
            base.pop(f'INPUT_{key}', None)

    if extra_env:
        base.update(extra_env)

    return base


def get_safe_env(extra_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Always scrub sensitive variables, regardless of env flags.

    Useful for non-GHA contexts where unconditional scrubbing is desired.
    """
    base: Dict[str, str] = {k: v for k, v in os.environ.items()}
    for key in GHA_SUBPROCESS_SCRUB:
        base.pop(key, None)
        base.pop(f'INPUT_{key}', None)
    if extra_env:
        base.update(extra_env)
    return base


# Alias matching the TS export name
subprocess_env = build_subprocess_env
