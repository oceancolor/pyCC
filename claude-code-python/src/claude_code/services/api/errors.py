"""
API error helpers — 完整移植自 services/api/errors.ts

提供错误消息常量、分类函数、以及从各类异常构建 AssistantMessage 的 helper。
Python 环境中 Anthropic SDK 的异常层级与 TS 保持一致。
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_ERROR_MESSAGE_PREFIX = "API Error"

PROMPT_TOO_LONG_ERROR_MESSAGE = "Prompt is too long"

CREDIT_BALANCE_TOO_LOW_ERROR_MESSAGE = "Credit balance is too low"

INVALID_API_KEY_ERROR_MESSAGE = "Not logged in · Please run /login"

INVALID_API_KEY_ERROR_MESSAGE_EXTERNAL = "Invalid API key · Fix external API key"

ORG_DISABLED_ERROR_MESSAGE_ENV_KEY_WITH_OAUTH = (
    "Your ANTHROPIC_API_KEY belongs to a disabled organization"
    " · Unset the environment variable to use your subscription instead"
)

ORG_DISABLED_ERROR_MESSAGE_ENV_KEY = (
    "Your ANTHROPIC_API_KEY belongs to a disabled organization"
    " · Update or unset the environment variable"
)

TOKEN_REVOKED_ERROR_MESSAGE = "OAuth token revoked · Please run /login"

CCR_AUTH_ERROR_MESSAGE = (
    "Authentication error · This may be a temporary network issue, please try again"
)

REPEATED_529_ERROR_MESSAGE = "Repeated 529 Overloaded errors"

CUSTOM_OFF_SWITCH_MESSAGE = (
    "Opus is experiencing high load, please use /model to switch to Sonnet"
)

API_TIMEOUT_ERROR_MESSAGE = "Request timed out"

OAUTH_ORG_NOT_ALLOWED_ERROR_MESSAGE = (
    "Your account does not have access to Claude Code. Please run /login."
)

# ---------------------------------------------------------------------------
# PDF / image size limits (mirrors src/constants/apiLimits.ts)
# ---------------------------------------------------------------------------

API_PDF_MAX_PAGES: int = 100
PDF_TARGET_RAW_SIZE: int = 32 * 1024 * 1024  # 32 MB


def _format_file_size(size_bytes: int) -> str:
    """Format a byte count to human-readable size string (mirrors formatFileSize)."""
    if size_bytes < 1024:
        return f"{size_bytes} bytes"
    if size_bytes < 1024 * 1024:
        kb = size_bytes / 1024
        if kb == int(kb):
            return f"{int(kb)}KB"
        return f"{kb:.1f}KB"
    mb = size_bytes / (1024 * 1024)
    if mb == int(mb):
        return f"{int(mb)}MB"
    return f"{mb:.1f}MB"


def _is_non_interactive_session() -> bool:
    """
    Returns True when running in non-interactive / SDK / pipe mode.
    Mirrors getIsNonInteractiveSession() — simplified for Python port.
    """
    return not os.isatty(sys.stdin.fileno()) if hasattr(sys, "stdin") else True


# ---------------------------------------------------------------------------
# startsWithApiErrorPrefix
# ---------------------------------------------------------------------------

def starts_with_api_error_prefix(text: str) -> bool:
    """
    Returns True if `text` begins with the standard API error prefix or the
    'please run /login' variant.
    Mirrors startsWithApiErrorPrefix().
    """
    return text.startswith(API_ERROR_MESSAGE_PREFIX) or text.startswith(
        f"Please run /login · {API_ERROR_MESSAGE_PREFIX}"
    )


# ---------------------------------------------------------------------------
# Prompt-too-long helpers
# ---------------------------------------------------------------------------

def is_prompt_too_long_message(msg: Any) -> bool:
    """
    Returns True if `msg` is an API-error assistant message whose content
    starts with PROMPT_TOO_LONG_ERROR_MESSAGE.
    Mirrors isPromptTooLongMessage().

    `msg` is expected to be a dict with:
      - isApiErrorMessage: bool
      - message: {"content": list[{"type": str, "text": str}] | str}
    """
    if not isinstance(msg, dict):
        return False
    if not msg.get("isApiErrorMessage"):
        return False
    content = (msg.get("message") or {}).get("content")
    if not isinstance(content, list):
        return False
    return any(
        block.get("type") == "text"
        and isinstance(block.get("text"), str)
        and block["text"].startswith(PROMPT_TOO_LONG_ERROR_MESSAGE)
        for block in content
    )


def parse_prompt_too_long_token_counts(
    raw_message: str,
) -> Dict[str, Optional[int]]:
    """
    Parse actual/limit token counts from a raw prompt-too-long API error string
    like "prompt is too long: 137500 tokens > 135000 maximum".
    Returns {"actualTokens": int|None, "limitTokens": int|None}.
    Mirrors parsePromptTooLongTokenCounts().
    """
    match = re.search(
        r"prompt is too long[^0-9]*(\d+)\s*tokens?\s*>\s*(\d+)", raw_message, re.IGNORECASE
    )
    if match:
        return {
            "actualTokens": int(match.group(1)),
            "limitTokens": int(match.group(2)),
        }
    return {"actualTokens": None, "limitTokens": None}


def get_prompt_too_long_token_gap(msg: Any) -> Optional[int]:
    """
    Returns the number of tokens over the limit from a prompt-too-long message,
    or None if not applicable / unparseable.
    Mirrors getPromptTooLongTokenGap().
    """
    if not is_prompt_too_long_message(msg):
        return None
    error_details = msg.get("errorDetails")
    if not error_details:
        return None
    counts = parse_prompt_too_long_token_counts(error_details)
    actual = counts.get("actualTokens")
    limit = counts.get("limitTokens")
    if actual is None or limit is None:
        return None
    gap = actual - limit
    return gap if gap > 0 else None


# ---------------------------------------------------------------------------
# Media size error helpers
# ---------------------------------------------------------------------------

def is_media_size_error(raw: str) -> bool:
    """
    Returns True if `raw` is a media-size rejection string that
    stripImagesFromMessages can fix.
    Mirrors isMediaSizeError().
    """
    if "image exceeds" in raw and "maximum" in raw:
        return True
    if "image dimensions exceed" in raw and "many-image" in raw:
        return True
    if re.search(r"maximum of \d+ PDF pages", raw):
        return True
    return False


def is_media_size_error_message(msg: Any) -> bool:
    """
    Message-level predicate: is this assistant message a media-size rejection?
    Mirrors isMediaSizeErrorMessage().
    """
    if not isinstance(msg, dict):
        return False
    if not msg.get("isApiErrorMessage"):
        return False
    error_details = msg.get("errorDetails")
    if error_details is None:
        return False
    return is_media_size_error(str(error_details))


# ---------------------------------------------------------------------------
# PDF / image error message factories
# ---------------------------------------------------------------------------

def get_pdf_too_large_error_message() -> str:
    """Mirrors getPdfTooLargeErrorMessage()."""
    limits = f"max {API_PDF_MAX_PAGES} pages, {_format_file_size(PDF_TARGET_RAW_SIZE)}"
    non_interactive = _is_non_interactive_session()
    if non_interactive:
        return (
            f"PDF too large ({limits}). "
            "Try reading the file a different way (e.g., extract text with pdftotext)."
        )
    return (
        f"PDF too large ({limits}). "
        "Double press esc to go back and try again, or use pdftotext to convert to text first."
    )


def get_pdf_password_protected_error_message() -> str:
    """Mirrors getPdfPasswordProtectedErrorMessage()."""
    if _is_non_interactive_session():
        return "PDF is password protected. Try using a CLI tool to extract or convert the PDF."
    return (
        "PDF is password protected. "
        "Please double press esc to edit your message and try again."
    )


def get_pdf_invalid_error_message() -> str:
    """Mirrors getPdfInvalidErrorMessage()."""
    if _is_non_interactive_session():
        return "The PDF file was not valid. Try converting it to text first (e.g., pdftotext)."
    return (
        "The PDF file was not valid. "
        "Double press esc to go back and try again with a different file."
    )


def get_image_too_large_error_message() -> str:
    """Mirrors getImageTooLargeErrorMessage()."""
    if _is_non_interactive_session():
        return "Image was too large. Try resizing the image or using a different approach."
    return (
        "Image was too large. "
        "Double press esc to go back and try again with a smaller image."
    )


def get_request_too_large_error_message() -> str:
    """Mirrors getRequestTooLargeErrorMessage()."""
    limits = f"max {_format_file_size(PDF_TARGET_RAW_SIZE)}"
    if _is_non_interactive_session():
        return f"Request too large ({limits}). Try with a smaller file."
    return (
        f"Request too large ({limits}). "
        "Double press esc to go back and try with a smaller file."
    )


# ---------------------------------------------------------------------------
# Auth-related message factories
# ---------------------------------------------------------------------------

def get_token_revoked_error_message() -> str:
    """Mirrors getTokenRevokedErrorMessage()."""
    if _is_non_interactive_session():
        return (
            "Your account does not have access to Claude. "
            "Please login again or contact your administrator."
        )
    return TOKEN_REVOKED_ERROR_MESSAGE


def get_oauth_org_not_allowed_error_message() -> str:
    """Mirrors getOauthOrgNotAllowedErrorMessage()."""
    if _is_non_interactive_session():
        return (
            "Your organization does not have access to Claude. "
            "Please login again or contact your administrator."
        )
    return OAUTH_ORG_NOT_ALLOWED_ERROR_MESSAGE


# ---------------------------------------------------------------------------
# AssistantMessage factory helpers (lightweight for Python port)
# ---------------------------------------------------------------------------

def _create_assistant_api_error_message(
    content: str,
    error: str = "unknown",
    error_details: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Python equivalent of createAssistantAPIErrorMessage().
    Returns a minimal AssistantMessage dict compatible with the Python port.
    """
    msg: Dict[str, Any] = {
        "type": "assistant",
        "isApiErrorMessage": True,
        "errorType": error,
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": content}],
        },
    }
    if error_details is not None:
        msg["errorDetails"] = error_details
    return msg


# ---------------------------------------------------------------------------
# isValidAPIMessage
# ---------------------------------------------------------------------------

def is_valid_api_message(value: Any) -> bool:
    """
    Type guard: is `value` a valid Message response from the API?
    Mirrors isValidAPIMessage().
    """
    if not isinstance(value, dict):
        return False
    return (
        "content" in value
        and "model" in value
        and "usage" in value
        and isinstance(value.get("content"), list)
        and isinstance(value.get("model"), str)
        and isinstance(value.get("usage"), dict)
    )


# ---------------------------------------------------------------------------
# extractUnknownErrorFormat
# ---------------------------------------------------------------------------

def extract_unknown_error_format(value: Any) -> Optional[str]:
    """
    Given a response that doesn't look right, see if it contains known error types.
    Mirrors extractUnknownErrorFormat().
    """
    if not isinstance(value, dict):
        return None
    output = value.get("Output")
    if isinstance(output, dict):
        t = output.get("__type")
        if t:
            return str(t)
    return None


# ---------------------------------------------------------------------------
# classify_api_error
# ---------------------------------------------------------------------------

def classify_api_error(error: Any) -> str:
    """
    Classify an API error into a standardized string for analytics/tagging.
    Mirrors classifyAPIError().

    Works with both raw Exception objects and Anthropic SDK APIError-like dicts.
    """
    from anthropic import (
        APIConnectionError,
        APIConnectionTimeoutError,
        APIError,
    )  # imported lazily to avoid hard dependency

    if isinstance(error, Exception):
        msg = str(error)
    else:
        msg = ""

    # Aborted
    if isinstance(error, Exception) and msg == "Request was aborted.":
        return "aborted"

    # Timeout
    if isinstance(error, APIConnectionTimeoutError):
        return "api_timeout"
    if isinstance(error, APIConnectionError) and "timeout" in msg.lower():
        return "api_timeout"

    # Repeated 529
    if REPEATED_529_ERROR_MESSAGE in msg:
        return "repeated_529"

    # Emergency capacity off switch
    if CUSTOM_OFF_SWITCH_MESSAGE in msg:
        return "capacity_off_switch"

    # Rate limit
    if isinstance(error, APIError) and getattr(error, "status", None) == 429:
        return "rate_limit"

    # Server overload 529
    if isinstance(error, APIError) and (
        getattr(error, "status", None) == 529
        or '"type":"overloaded_error"' in msg
    ):
        return "server_overload"

    # Prompt too long
    if PROMPT_TOO_LONG_ERROR_MESSAGE.lower() in msg.lower():
        return "prompt_too_long"

    # PDF too large
    if re.search(r"maximum of \d+ PDF pages", msg):
        return "pdf_too_large"

    # PDF password protected
    if "The PDF specified is password protected" in msg:
        return "pdf_password_protected"

    # Image too large (API 400)
    status = getattr(error, "status", None)
    if isinstance(error, APIError) and status == 400:
        if "image exceeds" in msg and "maximum" in msg:
            return "image_too_large"
        if "image dimensions exceed" in msg and "many-image" in msg:
            return "image_too_large"
        if "`tool_use` ids were found without `tool_result` blocks immediately after" in msg:
            return "tool_use_mismatch"
        if "unexpected `tool_use_id` found in `tool_result`" in msg:
            return "unexpected_tool_result"
        if "`tool_use` ids must be unique" in msg:
            return "duplicate_tool_use_id"
        if "invalid model name" in msg.lower():
            return "invalid_model"

    # Credit / billing
    if CREDIT_BALANCE_TOO_LOW_ERROR_MESSAGE.lower() in msg.lower():
        return "credit_balance_low"

    # Auth
    if "x-api-key" in msg.lower():
        return "invalid_api_key"

    if isinstance(error, APIError) and status == 403 and "OAuth token has been revoked" in msg:
        return "token_revoked"

    if isinstance(error, APIError) and status in (401, 403):
        if "OAuth authentication is currently not allowed for this organization" in msg:
            return "oauth_org_not_allowed"
        return "auth_error"

    # Bedrock
    if (
        os.environ.get("CLAUDE_CODE_USE_BEDROCK")
        and isinstance(error, Exception)
        and "model id" in msg.lower()
    ):
        return "bedrock_model_access"

    # Generic status-based
    if isinstance(error, APIError) and status is not None:
        if status >= 500:
            return "server_error"
        if status >= 400:
            return "client_error"

    # Connection error
    if isinstance(error, APIConnectionError):
        return "connection_error"

    return "unknown"


# ---------------------------------------------------------------------------
# categorize_retryable_api_error
# ---------------------------------------------------------------------------

def categorize_retryable_api_error(error: Any) -> str:
    """
    Categorises an APIError for retry decisions.
    Mirrors categorizeRetryableAPIError().
    Returns one of: 'rate_limit', 'authentication_failed', 'server_error', 'unknown'.
    """
    status = getattr(error, "status", None)
    msg = str(error)

    if status == 529 or '"type":"overloaded_error"' in msg:
        return "rate_limit"
    if status == 429:
        return "rate_limit"
    if status in (401, 403):
        return "authentication_failed"
    if status is not None and status >= 408:
        return "server_error"
    return "unknown"


# ---------------------------------------------------------------------------
# get_assistant_message_from_error
# ---------------------------------------------------------------------------

def get_assistant_message_from_error(
    error: Any,
    model: str = "",
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Convert an exception into an AssistantMessage dict.
    Python equivalent of getAssistantMessageFromError().

    Handles the common cases; Anthropic SDK exceptions are matched by type
    when the SDK is available, otherwise by message string patterns.
    """
    # Try to import Anthropic SDK types lazily
    try:
        from anthropic import (
            APIConnectionError,
            APIConnectionTimeoutError,
            APIError,
        )
        _has_sdk = True
    except ImportError:
        APIConnectionError = APIConnectionTimeoutError = APIError = None  # type: ignore
        _has_sdk = False

    msg = str(error) if isinstance(error, Exception) else ""
    status = getattr(error, "status", None)

    # Timeout
    if _has_sdk and (
        isinstance(error, APIConnectionTimeoutError)
        or (isinstance(error, APIConnectionError) and "timeout" in msg.lower())
    ):
        return _create_assistant_api_error_message(
            API_TIMEOUT_ERROR_MESSAGE, error="unknown"
        )

    # Emergency capacity off switch
    if CUSTOM_OFF_SWITCH_MESSAGE in msg:
        return _create_assistant_api_error_message(
            CUSTOM_OFF_SWITCH_MESSAGE, error="rate_limit"
        )

    # Prompt too long
    if "prompt is too long" in msg.lower():
        return _create_assistant_api_error_message(
            PROMPT_TOO_LONG_ERROR_MESSAGE,
            error="invalid_request",
            error_details=msg,
        )

    # PDF page limit
    if re.search(r"maximum of \d+ PDF pages", msg):
        return _create_assistant_api_error_message(
            get_pdf_too_large_error_message(),
            error="invalid_request",
            error_details=msg,
        )

    # PDF password protected
    if "The PDF specified is password protected" in msg:
        return _create_assistant_api_error_message(
            get_pdf_password_protected_error_message(),
            error="invalid_request",
        )

    # Invalid PDF
    if "The PDF specified was not valid" in msg:
        return _create_assistant_api_error_message(
            get_pdf_invalid_error_message(),
            error="invalid_request",
        )

    # Image too large (API 400)
    if _has_sdk and isinstance(error, APIError) and status == 400:
        if "image exceeds" in msg and "maximum" in msg:
            return _create_assistant_api_error_message(
                get_image_too_large_error_message(),
                error_details=msg,
            )
        if "image dimensions exceed" in msg and "many-image" in msg:
            non_interactive = _is_non_interactive_session()
            content = (
                "An image in the conversation exceeds the dimension limit for "
                "many-image requests (2000px). Start a new session with fewer images."
                if non_interactive
                else "An image in the conversation exceeds the dimension limit for "
                "many-image requests (2000px). Run /compact to remove old images from "
                "context, or start a new session."
            )
            return _create_assistant_api_error_message(
                content, error="invalid_request", error_details=msg
            )

    # Request too large (413)
    if _has_sdk and isinstance(error, APIError) and status == 413:
        return _create_assistant_api_error_message(
            get_request_too_large_error_message(), error="invalid_request"
        )

    # Duplicate tool_use IDs
    if (
        _has_sdk
        and isinstance(error, APIError)
        and status == 400
        and "`tool_use` ids must be unique" in msg
    ):
        non_interactive = _is_non_interactive_session()
        rewind = "" if non_interactive else " Run /rewind to recover the conversation."
        return _create_assistant_api_error_message(
            f"API Error: 400 duplicate tool_use ID in conversation history.{rewind}",
            error="invalid_request",
            error_details=msg,
        )

    # Credit balance
    if "Your credit balance is too low" in msg:
        return _create_assistant_api_error_message(
            CREDIT_BALANCE_TOO_LOW_ERROR_MESSAGE, error="billing_error"
        )

    # x-api-key / invalid key
    if "x-api-key" in msg.lower():
        api_key_source = os.environ.get("_ANTHROPIC_API_KEY_SOURCE", "")
        is_external = api_key_source in ("ANTHROPIC_API_KEY", "apiKeyHelper")
        return _create_assistant_api_error_message(
            INVALID_API_KEY_ERROR_MESSAGE_EXTERNAL
            if is_external
            else INVALID_API_KEY_ERROR_MESSAGE,
            error="authentication_failed",
        )

    # OAuth token revoked
    if (
        _has_sdk
        and isinstance(error, APIError)
        and status == 403
        and "OAuth token has been revoked" in msg
    ):
        return _create_assistant_api_error_message(
            get_token_revoked_error_message(), error="authentication_failed"
        )

    # OAuth org not allowed
    if (
        _has_sdk
        and isinstance(error, APIError)
        and status in (401, 403)
        and "OAuth authentication is currently not allowed for this organization" in msg
    ):
        return _create_assistant_api_error_message(
            get_oauth_org_not_allowed_error_message(), error="authentication_failed"
        )

    # Generic 401/403
    if _has_sdk and isinstance(error, APIError) and status in (401, 403):
        non_interactive = _is_non_interactive_session()
        content = (
            f"Failed to authenticate. {API_ERROR_MESSAGE_PREFIX}: {msg}"
            if non_interactive
            else f"Please run /login · {API_ERROR_MESSAGE_PREFIX}: {msg}"
        )
        return _create_assistant_api_error_message(content, error="authentication_failed")

    # 404 Not Found
    if _has_sdk and isinstance(error, APIError) and status == 404:
        return _create_assistant_api_error_message(
            f"There's an issue with the selected model ({model}). It may not exist "
            "or you may not have access to it. Run /model to pick a different model.",
            error="invalid_request",
        )

    # Connection error (non-timeout)
    if _has_sdk and isinstance(error, APIConnectionError):
        return _create_assistant_api_error_message(
            f"{API_ERROR_MESSAGE_PREFIX}: {msg}", error="unknown"
        )

    # Generic Error
    if isinstance(error, Exception):
        return _create_assistant_api_error_message(
            f"{API_ERROR_MESSAGE_PREFIX}: {msg}", error="unknown"
        )

    return _create_assistant_api_error_message(
        API_ERROR_MESSAGE_PREFIX, error="unknown"
    )


# ---------------------------------------------------------------------------
# get_error_message_if_refusal
# ---------------------------------------------------------------------------

def get_error_message_if_refusal(
    stop_reason: Optional[str],
    model: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Returns an error AssistantMessage if stop_reason == 'refusal', else None.
    Mirrors getErrorMessageIfRefusal().
    """
    if stop_reason != "refusal":
        return None

    non_interactive = _is_non_interactive_session()
    base_message = (
        f"{API_ERROR_MESSAGE_PREFIX}: Claude Code is unable to respond to this request, "
        "which appears to violate our Usage Policy (https://www.anthropic.com/legal/aup). "
        "Try rephrasing the request or attempting a different approach."
        if non_interactive
        else f"{API_ERROR_MESSAGE_PREFIX}: Claude Code is unable to respond to this request, "
        "which appears to violate our Usage Policy (https://www.anthropic.com/legal/aup). "
        "Please double press esc to edit your last message or start a new session for "
        "Claude Code to assist with a different task."
    )

    model_suggestion = (
        " If you are seeing this refusal repeatedly, try running "
        "/model claude-sonnet-4-20250514 to switch models."
        if model != "claude-sonnet-4-20250514"
        else ""
    )

    return _create_assistant_api_error_message(
        base_message + model_suggestion, error="invalid_request"
    )


# ---------------------------------------------------------------------------
# Lazy sys import guard
# ---------------------------------------------------------------------------

import sys  # noqa: E402 (already imported at top but kept explicit for clarity)
