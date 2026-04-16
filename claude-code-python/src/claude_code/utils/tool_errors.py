"""
Tool error types and formatting utilities.

Provides:
- ToolError: base exception for tool failures
- ToolAbortError: tool was aborted / interrupted
- format_error(error) -> str: human-readable error string (mirrors TS formatError)
- format_validation_error(): schema-validation error formatter
"""

from __future__ import annotations

from typing import Any, Optional

# Message shown when a tool is interrupted
INTERRUPT_MESSAGE_FOR_TOOL_USE = "Tool execution interrupted by user"

# Max total length before truncation
_MAX_ERROR_LENGTH = 10_000
_HALF_LENGTH = _MAX_ERROR_LENGTH // 2


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ToolError(Exception):
    """
    Raised when a tool fails during execution.

    Attributes:
        message: Human-readable error description.
        code: Optional exit code (for shell-based tools).
        stdout: Captured stdout, if any.
        stderr: Captured stderr, if any.
    """

    def __init__(
        self,
        message: str,
        *,
        code: Optional[int] = None,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.stdout = stdout
        self.stderr = stderr

    def __repr__(self) -> str:
        return f"ToolError(message={self.args[0]!r}, code={self.code!r})"


class ToolAbortError(ToolError):
    """
    Raised when a tool execution is aborted / interrupted.

    Maps to the TypeScript AbortError path in formatError().
    """

    def __init__(self, message: str = INTERRUPT_MESSAGE_FOR_TOOL_USE) -> None:
        super().__init__(message)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _get_error_parts(error: Exception) -> list[str]:
    """Extract message parts from an exception, prioritising stderr/stdout."""
    if isinstance(error, ToolError):
        parts: list[str] = []
        if error.code is not None:
            parts.append(f"Exit code {error.code}")
        if isinstance(error, ToolAbortError):
            parts.append(INTERRUPT_MESSAGE_FOR_TOOL_USE)
        if error.stderr:
            parts.append(error.stderr)
        if error.stdout:
            parts.append(error.stdout)
        return parts

    parts = [str(error)]
    stderr = getattr(error, "stderr", None)
    if isinstance(stderr, str):
        parts.append(stderr)
    stdout = getattr(error, "stdout", None)
    if isinstance(stdout, str):
        parts.append(stdout)
    return parts


def format_error(error: Any) -> str:
    """
    Return a human-readable string for *error*.

    - ToolAbortError → interrupt message
    - Non-exception → str(error)
    - Long messages are centre-truncated at 10 000 chars

    Args:
        error: Any exception or value.

    Returns:
        Formatted error string.
    """
    if isinstance(error, ToolAbortError):
        return error.args[0] if error.args else INTERRUPT_MESSAGE_FOR_TOOL_USE

    if not isinstance(error, Exception):
        return str(error)

    parts = _get_error_parts(error)
    full = "\n".join(p for p in parts if p).strip() or "Command failed with no output"

    if len(full) <= _MAX_ERROR_LENGTH:
        return full

    start = full[:_HALF_LENGTH]
    end = full[-_HALF_LENGTH:]
    trimmed = len(full) - _MAX_ERROR_LENGTH
    return f"{start}\n\n... [{trimmed} characters truncated] ...\n\n{end}"


# ---------------------------------------------------------------------------
# Schema-validation error formatter (replaces formatZodValidationError)
# ---------------------------------------------------------------------------

class ValidationIssue:
    """Represents a single schema validation problem."""

    def __init__(
        self,
        code: str,
        path: list[Any],
        message: str,
        keys: Optional[list[str]] = None,
        expected: Optional[str] = None,
    ) -> None:
        self.code = code
        self.path = path
        self.message = message
        self.keys = keys or []
        self.expected = expected


def _format_path(path: list[Any]) -> str:
    if not path:
        return ""
    result = ""
    for i, segment in enumerate(path):
        if isinstance(segment, int):
            result += f"[{segment}]"
        elif i == 0:
            result = str(segment)
        else:
            result += f".{segment}"
    return result


def format_validation_error(tool_name: str, issues: list[ValidationIssue]) -> str:
    """
    Convert a list of ValidationIssue objects into a human-readable error string.

    Args:
        tool_name: Name of the tool that failed validation.
        issues: List of validation issues.

    Returns:
        Formatted error message.
    """
    import re

    missing: list[str] = []
    unexpected: list[str] = []
    type_mismatches: list[dict] = []

    for issue in issues:
        if issue.code == "invalid_type" and "received undefined" in issue.message:
            missing.append(_format_path(issue.path))
        elif issue.code == "unrecognized_keys":
            unexpected.extend(issue.keys)
        elif issue.code == "invalid_type":
            m = re.search(r"received (\w+)", issue.message)
            received = m.group(1) if m else "unknown"
            type_mismatches.append({
                "param": _format_path(issue.path),
                "expected": issue.expected or "unknown",
                "received": received,
            })

    error_parts: list[str] = []
    for param in missing:
        error_parts.append(f"The required parameter `{param}` is missing")
    for param in unexpected:
        error_parts.append(f"An unexpected parameter `{param}` was provided")
    for tm in type_mismatches:
        error_parts.append(
            f"The parameter `{tm['param']}` type is expected as "
            f"`{tm['expected']}` but provided as `{tm['received']}`"
        )

    if not error_parts:
        return f"{tool_name} validation failed"

    count = len(error_parts)
    noun = "issues" if count > 1 else "issue"
    return f"{tool_name} failed due to the following {noun}:\n" + "\n".join(error_parts)
