"""
Swarm backends package.
Provides pane-based and in-process backends for teammate execution.
"""

from .types import (
    BackendType,
    PaneBackendType,
    PaneId,
    CreatePaneResult,
    PaneBackend,
    BackendDetectionResult,
    TeammateIdentity,
    TeammateSpawnConfig,
    TeammateSpawnResult,
    TeammateMessage,
    TeammateExecutor,
    is_pane_backend,
)
from .detection import (
    is_inside_tmux_sync,
    is_inside_tmux,
    get_leader_pane_id,
    is_tmux_available,
    is_in_i_term2,
    is_it2_cli_available,
    reset_detection_cache,
    IT2_COMMAND,
)
from .registry import (
    ensure_backends_registered,
    register_tmux_backend,
    register_i_term_backend,
    detect_and_get_backend,
    get_backend_by_type,
    get_cached_backend,
    get_cached_detection_result,
    mark_in_process_fallback,
    is_in_process_enabled,
    get_resolved_teammate_mode,
    get_in_process_backend,
    get_teammate_executor,
    reset_backend_detection,
)
from .teammate_mode_snapshot import (
    TeammateMode,
    set_cli_teammate_mode_override,
    get_cli_teammate_mode_override,
    clear_cli_teammate_mode_override,
    capture_teammate_mode_snapshot,
    get_teammate_mode_from_snapshot,
)

__all__ = [
    # types
    "BackendType",
    "PaneBackendType",
    "PaneId",
    "CreatePaneResult",
    "PaneBackend",
    "BackendDetectionResult",
    "TeammateIdentity",
    "TeammateSpawnConfig",
    "TeammateSpawnResult",
    "TeammateMessage",
    "TeammateExecutor",
    "is_pane_backend",
    # detection
    "is_inside_tmux_sync",
    "is_inside_tmux",
    "get_leader_pane_id",
    "is_tmux_available",
    "is_in_i_term2",
    "is_it2_cli_available",
    "reset_detection_cache",
    "IT2_COMMAND",
    # registry
    "ensure_backends_registered",
    "register_tmux_backend",
    "register_i_term_backend",
    "detect_and_get_backend",
    "get_backend_by_type",
    "get_cached_backend",
    "get_cached_detection_result",
    "mark_in_process_fallback",
    "is_in_process_enabled",
    "get_resolved_teammate_mode",
    "get_in_process_backend",
    "get_teammate_executor",
    "reset_backend_detection",
    # teammate_mode_snapshot
    "TeammateMode",
    "set_cli_teammate_mode_override",
    "get_cli_teammate_mode_override",
    "clear_cli_teammate_mode_override",
    "capture_teammate_mode_snapshot",
    "get_teammate_mode_from_snapshot",
]
