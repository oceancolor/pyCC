"""
Message constants.
Ported from: src/constants/messages.ts
"""
from __future__ import annotations

# Displayed when the model returns an empty / whitespace-only response.
NO_CONTENT_MESSAGE: str = "(no content)"

# Displayed when a tool call produces no output.
NO_TOOL_OUTPUT_MESSAGE: str = "(no tool output)"

# Placeholder for redacted content (e.g. long base64 blobs in logs).
REDACTED_PLACEHOLDER: str = "[redacted]"

# Generic error prefix used in user-facing error messages.
ERROR_PREFIX: str = "Error:"

__all__ = [
    "NO_CONTENT_MESSAGE",
    "NO_TOOL_OUTPUT_MESSAGE",
    "REDACTED_PLACEHOLDER",
    "ERROR_PREFIX",
]
