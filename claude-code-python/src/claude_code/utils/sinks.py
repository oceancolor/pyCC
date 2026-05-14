"""Analytics and error-log sinks initialisation. Ported from utils/sinks.ts"""

from __future__ import annotations

import logging
import os
from typing import Callable, List, Optional

_LOG = logging.getLogger(__name__)

# Registry of sink initialisation functions so callers can hook in without
# importing private modules.
_SINK_INITS: List[Callable[[], None]] = []
_initialised = False


def register_sink_init(fn: Callable[[], None]) -> None:
    """Register *fn* to be called during :func:`init_sinks`."""
    _SINK_INITS.append(fn)


def init_sinks() -> None:
    """Attach error-log and analytics sinks.

    Both inits are idempotent. Called from setup() for the default command;
    other entry-points (subcommands, daemon, bridge) call this directly since
    they bypass setup().

    Leaf module — kept out of setup.ts to avoid the setup → commands → bridge
    → setup import cycle.
    """
    global _initialised
    _initialised = True

    # Run any registered sink inits first
    for fn in _SINK_INITS:
        try:
            fn()
        except Exception as exc:
            _LOG.debug("Sink init %s raised: %s", fn, exc)

    _init_error_log_sink()
    _init_analytics_sink()


def _init_error_log_sink() -> None:
    """Initialise the error-log sink.

    In the Python port this configures the root logger to write errors to
    the log file path specified by ``CLAUDE_CODE_ERROR_LOG`` (if set).
    """
    log_path = os.environ.get("CLAUDE_CODE_ERROR_LOG")
    if not log_path:
        return

    try:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setLevel(logging.ERROR)
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        handler.setFormatter(formatter)
        root = logging.getLogger()
        # Avoid duplicate handlers if called multiple times
        if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == handler.baseFilename for h in root.handlers):
            root.addHandler(handler)
    except Exception as exc:
        _LOG.debug("Failed to initialise error log sink: %s", exc)


def _init_analytics_sink() -> None:
    """Initialise the analytics sink (no-op stub).

    A full implementation would attach the GrowthBook / Amplitude sink here.
    """


def is_initialised() -> bool:
    """Return True if :func:`init_sinks` has been called."""
    return _initialised
