"""
Python port of utils/slowOperations.ts
Source: claude-code-source/utils/slowOperations.ts (286 lines)

Wrappers around expensive operations (JSON parse/stringify, deep clone)
with optional slow-operation logging for performance monitoring.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import time
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Slow-operation threshold (mirrors the TS SLOW_OPERATION_THRESHOLD_MS)
# ---------------------------------------------------------------------------

def _compute_threshold() -> float:
    """Compute the slow-operation logging threshold in seconds."""
    env_val = os.environ.get("CLAUDE_CODE_SLOW_OPERATION_THRESHOLD_MS")
    if env_val is not None:
        try:
            parsed = float(env_val)
            if parsed >= 0:
                return parsed / 1000.0
        except ValueError:
            pass
    if os.environ.get("NODE_ENV") == "development":
        return 0.020  # 20 ms
    if os.environ.get("USER_TYPE") == "ant":
        return 0.300  # 300 ms
    return float("inf")


SLOW_OPERATION_THRESHOLD_S: float = _compute_threshold()

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Slow-operation context manager
# ---------------------------------------------------------------------------

class _SlowOperationLogger:
    """Context manager that logs when the enclosed block exceeds the threshold."""

    def __init__(self, description: str) -> None:
        self._description = description
        self._start: float = 0.0

    def __enter__(self) -> "_SlowOperationLogger":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_: Any) -> None:
        duration = time.perf_counter() - self._start
        if duration > SLOW_OPERATION_THRESHOLD_S:
            logger.debug(
                "[SLOW OPERATION DETECTED] %s (%.1f ms)",
                self._description,
                duration * 1000,
            )


class _NoopLogger:
    """No-op context manager for external builds."""

    def __enter__(self) -> "_NoopLogger":
        return self

    def __exit__(self, *_: Any) -> None:
        pass


_NOOP = _NoopLogger()


def slow_logging(description: str) -> "_SlowOperationLogger | _NoopLogger":
    """
    Return a context manager that times the operation and logs if slow.

    Usage::

        with slow_logging("JSON.parse"):
            result = json_parse(text)
    """
    if SLOW_OPERATION_THRESHOLD_S < float("inf"):
        return _SlowOperationLogger(description)
    return _NOOP


# ---------------------------------------------------------------------------
# Wrapped JSON operations
# ---------------------------------------------------------------------------

def json_stringify(
    value: Any,
    indent: Optional[int | str] = None,
    sort_keys: bool = False,
    default: Optional[Callable[[Any], Any]] = None,
) -> str:
    """
    Wrapped json.dumps with optional slow-operation logging.

    Mirrors TS ``jsonStringify(value, replacer?, space?)``.
    ``indent`` maps to the JSON ``space`` parameter.
    """
    desc = f"JSON.stringify({type(value).__name__})"
    with slow_logging(desc):
        return json.dumps(value, indent=indent, sort_keys=sort_keys, default=default)


def json_parse(text: str, object_hook: Optional[Callable] = None) -> Any:
    """
    Wrapped json.loads with optional slow-operation logging.

    Mirrors TS ``jsonParse(text, reviver?)``.
    """
    desc = f"JSON.parse(len={len(text)})"
    with slow_logging(desc):
        if object_hook is not None:
            return json.loads(text, object_hook=object_hook)
        return json.loads(text)


def clone(value: T) -> T:
    """
    Shallow-clone an object using copy.copy().

    Mirrors TS ``structuredClone(value)`` for simple cases.
    For deep cloning use ``clone_deep``.
    """
    with slow_logging(f"structuredClone({type(value).__name__})"):
        return copy.copy(value)


def clone_deep(value: T) -> T:
    """
    Deep-clone an object using copy.deepcopy().

    Mirrors TS ``cloneDeep(value)`` (lodash).
    """
    with slow_logging(f"cloneDeep({type(value).__name__})"):
        return copy.deepcopy(value)


# ---------------------------------------------------------------------------
# writeFileSync equivalent (sync write with optional flush)
# ---------------------------------------------------------------------------

def write_file_sync(
    file_path: str,
    data: str | bytes,
    encoding: str = "utf-8",
    flush: bool = False,
) -> None:
    """
    Synchronous file write with optional fsync.

    Mirrors TS ``writeFileSync_DEPRECATED(filePath, data, options?)``.

    .. deprecated::
        Prefer async I/O (``aiofiles`` or ``asyncio``).
        Sync writes block the event loop.
    """
    with slow_logging(f"fs.writeFileSync({file_path})"):
        mode = "wb" if isinstance(data, bytes) else "w"
        kwargs: dict[str, Any] = {} if isinstance(data, bytes) else {"encoding": encoding}
        with open(file_path, mode, **kwargs) as fh:
            fh.write(data)
            if flush:
                fh.flush()
                os.fsync(fh.fileno())
