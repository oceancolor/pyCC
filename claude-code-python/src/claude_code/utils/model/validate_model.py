# Ported from utils/model/validateModel.ts
"""
Model validation utilities.

Validates a model string by:
1. Checking the enterprise allowlist.
2. Accepting known aliases immediately.
3. Accepting ANTHROPIC_CUSTOM_MODEL_OPTION without an API call.
4. Attempting a live minimal API call (sideQuery) for unknown models.

Results for valid models are cached in-process.
"""
from __future__ import annotations

import os
from typing import Optional, TypedDict

# ---------------------------------------------------------------------------
# Dependency imports (all guarded)
# ---------------------------------------------------------------------------
try:
    from claude_code.utils.model.aliases import MODEL_ALIASES
    _HAS_ALIASES = True
except ImportError:
    MODEL_ALIASES = [  # type: ignore[assignment]
        "sonnet", "opus", "haiku", "best", "opusplan", "sonnet[1m]", "opus[1m]",
    ]
    _HAS_ALIASES = False

try:
    from claude_code.utils.model.model_allowlist import is_model_allowed
except ImportError:
    def is_model_allowed(model: str) -> bool:  # type: ignore[misc]
        return True

try:
    from claude_code.utils.model.providers import get_api_provider
except ImportError:
    def get_api_provider() -> str:  # type: ignore[misc]
        return "firstParty"

try:
    from claude_code.utils.model.model_strings import get_model_strings
except ImportError:
    def get_model_strings() -> dict:  # type: ignore[misc]
        return {
            "opus41": "claude-opus-4-1-20250805",
            "sonnet45": "claude-sonnet-4-5-20250929",
            "sonnet40": "claude-sonnet-4-20250514",
        }

try:
    from claude_code.utils.side_query import side_query, SideQueryOptions
    _HAS_SIDE_QUERY = True
except ImportError:
    _HAS_SIDE_QUERY = False

# ---------------------------------------------------------------------------
# In-process cache (model → validated)
# ---------------------------------------------------------------------------

_valid_model_cache: dict[str, bool] = {}


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class ValidationResult(TypedDict, total=False):
    valid: bool
    error: str


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------

def _get_3p_fallback_suggestion(model: str) -> Optional[str]:
    """Return an alternative model suggestion when the given model is unavailable on 3P.

    @[MODEL LAUNCH]: Add a fallback chain for the new model → previous version.
    """
    if get_api_provider() == "firstParty":
        return None
    ms = get_model_strings()
    lower = model.lower()
    if "opus-4-6" in lower or "opus_4_6" in lower:
        return ms.get("opus41")
    if "sonnet-4-6" in lower or "sonnet_4_6" in lower:
        return ms.get("sonnet45")
    if "sonnet-4-5" in lower or "sonnet_4_5" in lower:
        return ms.get("sonnet40")
    return None


def _handle_validation_error(error: BaseException, model_name: str) -> ValidationResult:
    """Translate an exception from the API call into a ValidationResult."""
    error_type = type(error).__name__

    # Try to import Anthropic SDK error types; fall back to name-based matching
    try:
        from anthropic import NotFoundError, APIError, APIConnectionError, AuthenticationError  # type: ignore
    except ImportError:
        NotFoundError = None  # type: ignore[assignment,misc]
        APIError = None  # type: ignore[assignment,misc]
        APIConnectionError = None  # type: ignore[assignment,misc]
        AuthenticationError = None  # type: ignore[assignment,misc]

    # NotFoundError (404) → model doesn't exist
    if (NotFoundError and isinstance(error, NotFoundError)) or error_type == "NotFoundError":
        fallback = _get_3p_fallback_suggestion(model_name)
        suggestion = f". Try '{fallback}' instead" if fallback else ""
        return ValidationResult(valid=False, error=f"Model '{model_name}' not found{suggestion}")

    # AuthenticationError
    if (AuthenticationError and isinstance(error, AuthenticationError)) or error_type == "AuthenticationError":
        return ValidationResult(
            valid=False,
            error="Authentication failed. Please check your API credentials.",
        )

    # APIConnectionError
    if (APIConnectionError and isinstance(error, APIConnectionError)) or error_type == "APIConnectionError":
        return ValidationResult(
            valid=False,
            error="Network error. Please check your internet connection.",
        )

    # Generic APIError — check for model-specific error body
    is_api_error = (APIError and isinstance(error, APIError)) or error_type in ("APIError", "APIStatusError")
    if is_api_error:
        # Check for model-specific errors embedded in the body
        try:
            body = getattr(error, "error", None) or getattr(error, "body", None)
            if (
                isinstance(body, dict)
                and body.get("type") == "not_found_error"
                and "model:" in str(body.get("message", ""))
            ):
                return ValidationResult(valid=False, error=f"Model '{model_name}' not found")
        except Exception:
            pass
        api_msg = getattr(error, "message", str(error))
        return ValidationResult(valid=False, error=f"API error: {api_msg}")

    # Unknown error — be safe and reject
    msg = error.args[0] if error.args else str(error)
    return ValidationResult(valid=False, error=f"Unable to validate model: {msg}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def validate_model(model: str) -> ValidationResult:
    """Validate *model* by:

    1. Rejecting empty strings.
    2. Checking the enterprise allowlist (``is_model_allowed``).
    3. Accepting known aliases without an API round-trip.
    4. Accepting ``ANTHROPIC_CUSTOM_MODEL_OPTION`` (pre-validated by the user).
    5. Returning from the in-process cache if already validated.
    6. Making a minimal live API call (``sideQuery``) to confirm the model exists.
    """
    normalized = model.strip()

    # 1. Empty model is invalid
    if not normalized:
        return ValidationResult(valid=False, error="Model name cannot be empty")

    # 2. Allowlist check
    if not is_model_allowed(normalized):
        return ValidationResult(
            valid=False,
            error=f"Model '{normalized}' is not in the list of available models",
        )

    # 3. Known aliases are always valid
    lower = normalized.lower()
    if lower in [a.lower() for a in MODEL_ALIASES]:
        return ValidationResult(valid=True)

    # 4. ANTHROPIC_CUSTOM_MODEL_OPTION is pre-validated
    if normalized == os.environ.get("ANTHROPIC_CUSTOM_MODEL_OPTION", ""):
        return ValidationResult(valid=True)

    # 5. In-process cache
    if normalized in _valid_model_cache:
        return ValidationResult(valid=True)

    # 6. Live API validation
    if not _HAS_SIDE_QUERY:
        # No side_query available; optimistically accept
        return ValidationResult(valid=True)

    try:
        await side_query(SideQueryOptions(
            model=normalized,
            max_tokens=1,
            max_retries=0,
            query_source="model_validation",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Hi",
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                }
            ],
        ))
        # Success → cache and return valid
        _valid_model_cache[normalized] = True
        return ValidationResult(valid=True)
    except BaseException as exc:
        return _handle_validation_error(exc, normalized)
