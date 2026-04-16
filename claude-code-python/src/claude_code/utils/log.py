"""
Logging utilities
原始 TS: src/utils/log.ts (partial)

rich → console logging with levels
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any, Optional

# Configure module logger
_logger = logging.getLogger("claude_code")
_logger.setLevel(logging.WARNING)

_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
_logger.addHandler(_handler)


def log_error(message: Any, *args: Any) -> None:
    """Log an error message."""
    _logger.error(str(message), *args)


def log_warning(message: Any, *args: Any) -> None:
    """Log a warning message."""
    _logger.warning(str(message), *args)


def log_info(message: Any, *args: Any) -> None:
    """Log an info message."""
    _logger.info(str(message), *args)


def log_debug(message: Any, *args: Any) -> None:
    """Log a debug message."""
    _logger.debug(str(message), *args)


def log_for_debugging(message: Any, *args: Any) -> None:
    """
    Debug log that only prints when CLAUDE_CODE_DEBUG is set.
    原始 TS: logForDebugging
    """
    if os.environ.get("CLAUDE_CODE_DEBUG"):
        _logger.debug(str(message), *args)


def set_debug_logging(enabled: bool = True) -> None:
    """Enable or disable debug logging."""
    _logger.setLevel(logging.DEBUG if enabled else logging.WARNING)
