"""
Backend registry for swarm teammate execution.

Port of utils/swarm/backends/registry.ts
"""

from __future__ import annotations

import logging
import platform
from typing import Callable, Optional, Type

from .types import (
    BackendDetectionResult,
    BackendType,
    PaneBackend,
    PaneBackendType,
    TeammateExecutor,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state (mirrors TS module-level variables)
# ---------------------------------------------------------------------------

_cached_backend: Optional[PaneBackend] = None
_cached_detection_result: Optional[BackendDetectionResult] = None
_backends_registered: bool = False
_cached_in_process_backend: Optional[TeammateExecutor] = None
_cached_pane_backend_executor: Optional[TeammateExecutor] = None
_in_process_fallback_active: bool = False

# Registered backend classes
_TmuxBackendClass: Optional[Callable[[], PaneBackend]] = None
_ITermBackendClass: Optional[Callable[[], PaneBackend]] = None


# ---------------------------------------------------------------------------
# Backend registration
# ---------------------------------------------------------------------------


async def ensure_backends_registered() -> None:
    """
    Ensures backend classes are registered. Does not spawn subprocesses.
    Lightweight option when you only need class registration.
    """
    global _backends_registered
    if _backends_registered:
        return
    # Dynamic imports to avoid circular dependencies
    import importlib
    importlib.import_module(".tmux_backend", package=__package__)
    importlib.import_module(".i_term_backend", package=__package__)
    _backends_registered = True


def register_tmux_backend(backend_class: Callable[[], PaneBackend]) -> None:
    """
    Registers the TmuxBackend class with the registry.
    Called by tmux_backend.py to avoid circular dependencies.
    """
    global _TmuxBackendClass
    _TmuxBackendClass = backend_class


def register_i_term_backend(backend_class: Callable[[], PaneBackend]) -> None:
    """
    Registers the ITermBackend class with the registry.
    Called by i_term_backend.py to avoid circular dependencies.
    """
    global _ITermBackendClass
    logger.debug(
        "[registry] register_i_term_backend called, class=%s",
        getattr(backend_class, "__name__", "undefined"),
    )
    _ITermBackendClass = backend_class


def _create_tmux_backend() -> PaneBackend:
    """Creates a TmuxBackend instance. Raises if not registered."""
    if _TmuxBackendClass is None:
        raise RuntimeError(
            "TmuxBackend not registered. Import tmux_backend before using the registry."
        )
    return _TmuxBackendClass()


def _create_i_term_backend() -> PaneBackend:
    """Creates an ITermBackend instance. Raises if not registered."""
    if _ITermBackendClass is None:
        raise RuntimeError(
            "ITermBackend not registered. Import i_term_backend before using the registry."
        )
    return _ITermBackendClass()


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


async def detect_and_get_backend() -> BackendDetectionResult:
    """
    Detect and return the appropriate pane backend.

    Detection priority flow:
    1. If inside tmux, always use tmux (even in iTerm2)
    2. If in iTerm2 with it2 available, use iTerm2 backend
    3. If in iTerm2 without it2, check tmux as fallback
    4. Fall back to tmux external session
    5. Otherwise raise error with instructions
    """
    global _cached_backend, _cached_detection_result

    await ensure_backends_registered()

    if _cached_detection_result is not None:
        logger.debug(
            "[BackendRegistry] Using cached backend: %s",
            _cached_detection_result.backend.type,
        )
        return _cached_detection_result

    from .detection import (
        is_in_i_term2,
        is_inside_tmux,
        is_it2_cli_available,
        is_tmux_available,
    )
    from .it2_setup import get_prefer_tmux_over_iterm2

    logger.debug("[BackendRegistry] Starting backend detection...")

    inside_tmux = await is_inside_tmux()
    in_i_term2 = is_in_i_term2()

    logger.debug(
        "[BackendRegistry] Environment: insideTmux=%s, inITerm2=%s",
        inside_tmux,
        in_i_term2,
    )

    # Priority 1: inside tmux → always use tmux
    if inside_tmux:
        logger.debug("[BackendRegistry] Selected: tmux (running inside tmux session)")
        backend = _create_tmux_backend()
        _cached_backend = backend
        _cached_detection_result = BackendDetectionResult(
            backend=backend, is_native=True, needs_it2_setup=False
        )
        return _cached_detection_result

    # Priority 2: in iTerm2
    if in_i_term2:
        prefer_tmux = get_prefer_tmux_over_iterm2()
        if prefer_tmux:
            logger.debug(
                "[BackendRegistry] User prefers tmux over iTerm2, skipping iTerm2 detection"
            )
        else:
            it2_available = await is_it2_cli_available()
            logger.debug(
                "[BackendRegistry] iTerm2 detected, it2 CLI available: %s", it2_available
            )

            if it2_available:
                logger.debug(
                    "[BackendRegistry] Selected: iterm2 (native iTerm2 with it2 CLI)"
                )
                backend = _create_i_term_backend()
                _cached_backend = backend
                _cached_detection_result = BackendDetectionResult(
                    backend=backend, is_native=True, needs_it2_setup=False
                )
                return _cached_detection_result

        # In iTerm2 but it2 not available — try tmux as fallback
        tmux_available = await is_tmux_available()
        logger.debug(
            "[BackendRegistry] it2 not available, tmux available: %s", tmux_available
        )

        if tmux_available:
            logger.debug(
                "[BackendRegistry] Selected: tmux (fallback in iTerm2, it2 setup recommended)"
            )
            backend = _create_tmux_backend()
            _cached_backend = backend
            _cached_detection_result = BackendDetectionResult(
                backend=backend,
                is_native=False,
                needs_it2_setup=not prefer_tmux,
            )
            return _cached_detection_result

        # In iTerm2 with no it2 and no tmux
        logger.debug(
            "[BackendRegistry] ERROR: iTerm2 detected but no it2 CLI and no tmux"
        )
        raise RuntimeError(
            "iTerm2 detected but it2 CLI not installed. Install it2 with: pip install it2"
        )

    # Priority 3: fall back to tmux external session
    tmux_available = await is_tmux_available()
    logger.debug(
        "[BackendRegistry] Not in tmux or iTerm2, tmux available: %s", tmux_available
    )

    if tmux_available:
        logger.debug("[BackendRegistry] Selected: tmux (external session mode)")
        backend = _create_tmux_backend()
        _cached_backend = backend
        _cached_detection_result = BackendDetectionResult(
            backend=backend, is_native=False, needs_it2_setup=False
        )
        return _cached_detection_result

    logger.debug("[BackendRegistry] ERROR: No pane backend available")
    raise RuntimeError(_get_tmux_install_instructions())


def _get_tmux_install_instructions() -> str:
    """Returns platform-specific tmux installation instructions."""
    system = platform.system().lower()

    if system == "darwin":
        return (
            "To use agent swarms, install tmux:\n"
            "  brew install tmux\n"
            "Then start a tmux session with: tmux new-session -s claude"
        )
    elif system in ("linux",):
        return (
            "To use agent swarms, install tmux:\n"
            "  sudo apt install tmux    # Ubuntu/Debian\n"
            "  sudo dnf install tmux    # Fedora/RHEL\n"
            "Then start a tmux session with: tmux new-session -s claude"
        )
    elif system == "windows":
        return (
            "To use agent swarms, you need tmux which requires WSL (Windows Subsystem for Linux).\n"
            "Install WSL first, then inside WSL run:\n"
            "  sudo apt install tmux\n"
            "Then start a tmux session with: tmux new-session -s claude"
        )
    else:
        return (
            "To use agent swarms, install tmux using your system's package manager.\n"
            "Then start a tmux session with: tmux new-session -s claude"
        )


def get_backend_by_type(backend_type: PaneBackendType) -> PaneBackend:
    """
    Gets a backend by explicit type selection.
    Useful for testing or when the user has a preference.
    """
    if backend_type == "tmux":
        return _create_tmux_backend()
    elif backend_type == "iterm2":
        return _create_i_term_backend()
    else:
        raise ValueError(f"Unknown backend type: {backend_type}")


def get_cached_backend() -> Optional[PaneBackend]:
    """Gets the currently cached backend, if any."""
    return _cached_backend


def get_cached_detection_result() -> Optional[BackendDetectionResult]:
    """Gets the cached backend detection result, if any."""
    return _cached_detection_result


def mark_in_process_fallback() -> None:
    """
    Records that spawn fell back to in-process mode because no pane backend
    was available.
    """
    global _in_process_fallback_active
    logger.debug("[BackendRegistry] Marking in-process fallback as active")
    _in_process_fallback_active = True


def _get_teammate_mode() -> str:
    """Gets the teammate mode for this session from the snapshot."""
    from .teammate_mode_snapshot import get_teammate_mode_from_snapshot

    return get_teammate_mode_from_snapshot()


def is_in_process_enabled() -> bool:
    """
    Checks if in-process teammate execution is enabled.

    Logic:
    - If teammateMode is 'in-process', always enabled
    - If teammateMode is 'tmux', always disabled
    - If teammateMode is 'auto', check environment
    """
    from .detection import is_in_i_term2, is_inside_tmux_sync

    # Force in-process for non-interactive sessions
    try:
        from ...bootstrap.state import get_is_non_interactive_session  # type: ignore[import]

        if get_is_non_interactive_session():
            logger.debug(
                "[BackendRegistry] isInProcessEnabled: True (non-interactive session)"
            )
            return True
    except Exception:
        pass

    mode = _get_teammate_mode()

    if mode == "in-process":
        enabled = True
    elif mode == "tmux":
        enabled = False
    else:
        # 'auto' mode
        if _in_process_fallback_active:
            logger.debug(
                "[BackendRegistry] isInProcessEnabled: True (fallback after pane backend unavailable)"
            )
            return True
        inside_tmux = is_inside_tmux_sync()
        in_i_term2 = is_in_i_term2()
        enabled = not inside_tmux and not in_i_term2

    logger.debug(
        "[BackendRegistry] isInProcessEnabled: %s (mode=%s)", enabled, mode
    )
    return enabled


def get_resolved_teammate_mode() -> str:
    """
    Returns the resolved teammate executor mode for this session.
    Unlike get_teammate_mode_from_snapshot which may return 'auto', this returns
    what 'auto' actually resolves to given the current environment.
    """
    return "in-process" if is_in_process_enabled() else "tmux"


def get_in_process_backend() -> TeammateExecutor:
    """
    Gets the InProcessBackend instance.
    Creates and caches the instance on first call.
    """
    global _cached_in_process_backend
    if _cached_in_process_backend is None:
        from .in_process_backend import create_in_process_backend

        _cached_in_process_backend = create_in_process_backend()
    return _cached_in_process_backend


async def get_teammate_executor(prefer_in_process: bool = False) -> TeammateExecutor:
    """
    Gets a TeammateExecutor for spawning teammates.

    Returns either:
    - InProcessBackend when prefer_in_process is True and in-process mode is enabled
    - PaneBackendExecutor wrapping the detected pane backend otherwise

    :param prefer_in_process: If True and in-process is enabled, returns InProcessBackend.
    """
    if prefer_in_process and is_in_process_enabled():
        logger.debug("[BackendRegistry] Using in-process executor")
        return get_in_process_backend()

    logger.debug("[BackendRegistry] Using pane backend executor")
    return await _get_pane_backend_executor()


async def _get_pane_backend_executor() -> TeammateExecutor:
    """
    Gets the PaneBackendExecutor instance.
    Creates and caches the instance on first call.
    """
    global _cached_pane_backend_executor
    if _cached_pane_backend_executor is None:
        from .pane_backend_executor import create_pane_backend_executor

        detection = await detect_and_get_backend()
        _cached_pane_backend_executor = create_pane_backend_executor(detection.backend)
        logger.debug(
            "[BackendRegistry] Created PaneBackendExecutor wrapping %s",
            detection.backend.type,
        )
    return _cached_pane_backend_executor


def reset_backend_detection() -> None:
    """Resets the backend detection cache. Used for testing."""
    global (
        _cached_backend,
        _cached_detection_result,
        _cached_in_process_backend,
        _cached_pane_backend_executor,
        _backends_registered,
        _in_process_fallback_active,
    )
    _cached_backend = None
    _cached_detection_result = None
    _cached_in_process_backend = None
    _cached_pane_backend_executor = None
    _backends_registered = False
    _in_process_fallback_active = False
