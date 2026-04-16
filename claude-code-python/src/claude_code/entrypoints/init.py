"""
Init - Application initialization for Claude Code CLI.

Provides the main initialization function and telemetry setup.
This module mirrors init.ts — it stubs or approximates the TypeScript-side
initialization sequence so Python consumers can understand the startup flow.

Corresponds to init.ts.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Track if telemetry has been initialized to prevent double initialization
_telemetry_initialized: bool = False

# ============================================================================
# Init (memoized, async)
# ============================================================================

_init_called: bool = False
_init_done: bool = False


async def init() -> None:
    """
    Main application initialization.

    Mirrors the TypeScript `init` function (memoized via lodash):
    - Enables configs
    - Applies safe environment variables
    - Configures mTLS, proxy agents
    - Sets up graceful shutdown
    - Kicks off async background work (analytics, OAuth, JetBrains, etc.)
    - Initializes scratchpad directory if enabled

    In the Python port this is a lightweight stub; full initialization depends
    on internal services being ported. The function is idempotent — calling it
    multiple times has no additional effect after the first call.

    Raises:
        ConfigParseError: If a configuration file is malformed.
        Exception: Re-raises unexpected errors from initialization steps.
    """
    global _init_called, _init_done

    if _init_done:
        return

    if _init_called:
        # Already in progress - wait (naive spinwait for stub)
        while not _init_done:
            import asyncio
            await asyncio.sleep(0.01)
        return

    _init_called = True
    init_start_time = int(time.time() * 1000)
    logger.info("init_started")

    try:
        # Stub: In the real implementation these would call internal services.
        # In this Python port we log milestones and return.

        logger.info("init_configs_enabled", extra={"duration_ms": 0})
        logger.info("init_safe_env_vars_applied", extra={"duration_ms": 0})
        logger.info("init_mtls_configured", extra={"duration_ms": 0})
        logger.info("init_proxy_configured", extra={"duration_ms": 0})

        logger.info(
            "init_completed",
            extra={"duration_ms": int(time.time() * 1000) - init_start_time},
        )
        _init_done = True

    except ConfigParseError as error:
        # In a non-interactive session we just log and exit
        logger.error(f"Configuration error in {error.file_path}: {error.message}")
        raise

    except Exception:
        _init_called = False  # Allow retry
        raise


# ============================================================================
# Telemetry
# ============================================================================


def initialize_telemetry_after_trust() -> None:
    """
    Initialize telemetry after trust has been granted.

    For remote-settings-eligible users, waits for settings to load,
    then re-applies env vars before initializing telemetry.
    For non-eligible users, initializes telemetry immediately.

    This should only be called once, after the trust dialog has been accepted.
    """
    import asyncio

    # Schedule the async telemetry init
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(_do_initialize_telemetry())
    except RuntimeError:
        # No event loop; run synchronously (e.g., in tests)
        asyncio.run(_do_initialize_telemetry())


async def _do_initialize_telemetry() -> None:
    """
    Internal: perform the actual telemetry initialization.

    Stub — full implementation would load OpenTelemetry, configure meters,
    and increment the session counter.
    """
    global _telemetry_initialized

    if _telemetry_initialized:
        return

    _telemetry_initialized = True
    try:
        logger.debug("[telemetry] Telemetry initialization stub — no-op in Python port")
    except Exception as error:
        _telemetry_initialized = False
        raise


# ============================================================================
# ConfigParseError (mirrored from utils/errors.ts)
# ============================================================================


class ConfigParseError(Exception):
    """
    Raised when a Claude Code configuration file cannot be parsed.

    Mirrors ConfigParseError from utils/errors.ts.
    """

    def __init__(self, message: str, file_path: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.file_path = file_path

    def __repr__(self) -> str:
        return f"ConfigParseError(file_path={self.file_path!r}, message={self.message!r})"
