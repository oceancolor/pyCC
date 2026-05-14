"""Environment validation. Ported from envValidation.ts.

Validates that required environment variables are present and well-formed
before Claude Code starts making API calls.  Provides both a soft-check
(returns errors) and a hard-check (raises on failure).
"""
from __future__ import annotations

import os
import re
from typing import List, Optional, Tuple

__all__ = [
    "validate_environment",
    "assert_valid_environment",
    "get_api_key",
    "is_api_key_format_valid",
    "get_validation_errors",
]

# Valid API key prefixes issued by Anthropic
_API_KEY_PREFIXES = ("sk-ant-", "sk-")
_API_KEY_RE = re.compile(r"^sk(-ant)?-[A-Za-z0-9_\-]{10,}$")


def get_api_key() -> Optional[str]:
    """Return the ANTHROPIC_API_KEY from the environment, or None."""
    return os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")


def is_api_key_format_valid(key: str) -> bool:
    """Return True if *key* matches a known Anthropic API key format."""
    return bool(_API_KEY_RE.match(key))


def get_validation_errors() -> List[str]:
    """Return a list of environment validation error messages (empty = OK)."""
    errors: List[str] = []

    api_key = get_api_key()

    # Allow keyless operation in some modes (e.g., Vertex AI, Bedrock)
    use_vertex = os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID")
    use_bedrock = os.environ.get("ANTHROPIC_BEDROCK_BASE_URL") or os.environ.get(
        "AWS_BEDROCK_ANTHROPIC_REGION"
    )

    if not use_vertex and not use_bedrock:
        if not api_key:
            errors.append(
                "ANTHROPIC_API_KEY is not set. "
                "Set it to your Anthropic API key or configure a cloud provider."
            )
        elif not is_api_key_format_valid(api_key):
            errors.append(
                f"ANTHROPIC_API_KEY appears malformed (got {api_key[:12]}…). "
                "It should start with 'sk-ant-' or 'sk-'."
            )

    return errors


def validate_environment() -> Tuple[bool, List[str]]:
    """Return ``(ok, errors)`` after checking required environment variables."""
    errors = get_validation_errors()
    return len(errors) == 0, errors


def assert_valid_environment() -> None:
    """Raise EnvironmentError if the environment is not valid."""
    ok, errors = validate_environment()
    if not ok:
        raise EnvironmentError(
            "Claude Code environment validation failed:\n"
            + "\n".join(f"  • {e}" for e in errors)
        )
