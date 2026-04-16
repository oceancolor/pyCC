"""
Error classes
原始 TS: src/utils/errors.ts
"""
from __future__ import annotations

import errno
import os
from typing import Optional


class ClaudeError(Exception):
    """Base Claude error."""
    pass


class MalformedCommandError(Exception):
    pass


class AbortError(Exception):
    def __init__(self, message: str = ""):
        super().__init__(message)
        self.name = "AbortError"


def is_abort_error(e: BaseException) -> bool:
    """
    True iff `e` is an abort-shaped error.
    原始 TS: isAbortError
    """
    return isinstance(e, AbortError)


class ConfigParseError(Exception):
    """Config file parsing error."""
    def __init__(self, message: str, file_path: str, default_config: object):
        super().__init__(message)
        self.name = "ConfigParseError"
        self.file_path = file_path
        self.default_config = default_config


class ShellError(Exception):
    """Shell command failed."""
    def __init__(
        self,
        stdout: str,
        stderr: str,
        code: int,
        interrupted: bool,
    ):
        super().__init__("Shell command failed")
        self.name = "ShellError"
        self.stdout = stdout
        self.stderr = stderr
        self.code = code
        self.interrupted = interrupted


class TeleportOperationError(Exception):
    def __init__(self, message: str, formatted_message: str):
        super().__init__(message)
        self.name = "TeleportOperationError"
        self.formatted_message = formatted_message


class TelemetrySafeError(Exception):
    """
    Error with a message safe to log to telemetry.
    原始 TS: TelemetrySafeError
    """
    def __init__(self, message: str, telemetry_message: Optional[str] = None):
        super().__init__(message)
        self.telemetry_message = telemetry_message or message


def is_enoent(e: BaseException) -> bool:
    """Check if error is a file-not-found (ENOENT) error."""
    if isinstance(e, FileNotFoundError):
        return True
    if isinstance(e, OSError):
        return e.errno == errno.ENOENT
    return False


def get_errno_code(e: BaseException) -> Optional[int]:
    """Get the errno code from an OSError."""
    if isinstance(e, OSError):
        return e.errno
    return None


def error_message(e: BaseException) -> str:
    """Extract a safe error message string."""
    return str(e)
