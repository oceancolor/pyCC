"""
Types for swarm backends.

Port of utils/swarm/backends/types.ts
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal, Optional, Protocol

# ---------------------------------------------------------------------------
# Primitive type aliases
# ---------------------------------------------------------------------------

BackendType = Literal["tmux", "iterm2", "in-process"]
"""Types of backends available for teammate execution."""

PaneBackendType = Literal["tmux", "iterm2"]
"""Subset of BackendType for pane-based backends only."""

PaneId = str
"""Opaque identifier for a pane managed by a backend."""

# ---------------------------------------------------------------------------
# Color names (mirrors AgentColorName from agentColorManager.ts)
# ---------------------------------------------------------------------------

AgentColorName = Literal[
    "red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"
]

# ---------------------------------------------------------------------------
# Pane creation result
# ---------------------------------------------------------------------------


@dataclass
class CreatePaneResult:
    """Result of creating a new teammate pane."""

    pane_id: PaneId
    """The pane ID for the newly created pane."""

    is_first_teammate: bool
    """Whether this is the first teammate pane (affects layout strategy)."""


# ---------------------------------------------------------------------------
# PaneBackend interface (abstract base class)
# ---------------------------------------------------------------------------


class PaneBackend(ABC):
    """
    Interface for pane management backends.
    Abstracts operations for creating and managing terminal panes
    for teammate visualization in swarm mode.
    """

    @property
    @abstractmethod
    def type(self) -> BackendType:
        """The type identifier for this backend."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable display name for this backend."""
        ...

    @property
    @abstractmethod
    def supports_hide_show(self) -> bool:
        """Whether this backend supports hiding and showing panes."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Checks if this backend is available on the system."""
        ...

    @abstractmethod
    async def is_running_inside(self) -> bool:
        """Checks if we're currently running inside this backend's environment."""
        ...

    @abstractmethod
    async def create_teammate_pane_in_swarm_view(
        self,
        name: str,
        color: AgentColorName,
    ) -> CreatePaneResult:
        """Creates a new pane for a teammate in the swarm view."""
        ...

    @abstractmethod
    async def send_command_to_pane(
        self,
        pane_id: PaneId,
        command: str,
        use_external_session: bool = False,
    ) -> None:
        """Sends a command to execute in a specific pane."""
        ...

    @abstractmethod
    async def set_pane_border_color(
        self,
        pane_id: PaneId,
        color: AgentColorName,
        use_external_session: bool = False,
    ) -> None:
        """Sets the border color for a pane."""
        ...

    @abstractmethod
    async def set_pane_title(
        self,
        pane_id: PaneId,
        name: str,
        color: AgentColorName,
        use_external_session: bool = False,
    ) -> None:
        """Sets the title for a pane."""
        ...

    @abstractmethod
    async def enable_pane_border_status(
        self,
        window_target: Optional[str] = None,
        use_external_session: bool = False,
    ) -> None:
        """Enables pane border status display (shows titles in borders)."""
        ...

    @abstractmethod
    async def rebalance_panes(
        self,
        window_target: str,
        has_leader: bool,
    ) -> None:
        """Rebalances panes to achieve the desired layout."""
        ...

    @abstractmethod
    async def kill_pane(
        self,
        pane_id: PaneId,
        use_external_session: bool = False,
    ) -> bool:
        """Kills/closes a specific pane."""
        ...

    @abstractmethod
    async def hide_pane(
        self,
        pane_id: PaneId,
        use_external_session: bool = False,
    ) -> bool:
        """Hides a pane by breaking it out into a hidden window."""
        ...

    @abstractmethod
    async def show_pane(
        self,
        pane_id: PaneId,
        target_window_or_pane: str,
        use_external_session: bool = False,
    ) -> bool:
        """Shows a previously hidden pane by joining it back into the main window."""
        ...


# ---------------------------------------------------------------------------
# BackendDetectionResult
# ---------------------------------------------------------------------------


@dataclass
class BackendDetectionResult:
    """Result from backend detection."""

    backend: PaneBackend
    """The backend that should be used."""

    is_native: bool
    """Whether we're running inside the backend's native environment."""

    needs_it2_setup: Optional[bool] = None
    """If iTerm2 is detected but it2 not installed, this will be true."""


# ---------------------------------------------------------------------------
# In-Process Teammate Types
# ---------------------------------------------------------------------------


@dataclass
class TeammateIdentity:
    """
    Identity fields for a teammate.
    Subset shared with TeammateContext to avoid circular deps.
    """

    name: str
    """Agent name (e.g., 'researcher', 'tester')."""

    team_name: str
    """Team name this teammate belongs to."""

    color: Optional[AgentColorName] = None
    """Assigned color for UI differentiation."""

    plan_mode_required: Optional[bool] = None
    """Whether plan mode approval is required before implementation."""


@dataclass
class TeammateSpawnConfig(TeammateIdentity):
    """Configuration for spawning a teammate (any execution mode)."""

    prompt: str = ""
    """Initial prompt to send to the teammate."""

    cwd: str = ""
    """Working directory for the teammate."""

    parent_session_id: str = ""
    """Parent session ID (for context linking)."""

    model: Optional[str] = None
    """Model to use for this teammate."""

    system_prompt: Optional[str] = None
    """System prompt for this teammate."""

    system_prompt_mode: Optional[Literal["default", "replace", "append"]] = None
    """How to apply the system prompt."""

    worktree_path: Optional[str] = None
    """Optional git worktree path."""

    permissions: Optional[list[str]] = None
    """Tool permissions to grant this teammate."""

    allow_permission_prompts: Optional[bool] = None
    """Whether this teammate can show permission prompts for unlisted tools."""


@dataclass
class TeammateSpawnResult:
    """Result from spawning a teammate."""

    success: bool
    """Whether spawn was successful."""

    agent_id: str
    """Unique agent ID (format: agentName@teamName)."""

    error: Optional[str] = None
    """Error message if spawn failed."""

    abort_controller: Optional[object] = None
    """Abort controller for lifecycle management (in-process only)."""

    task_id: Optional[str] = None
    """Task ID in AppState.tasks (in-process only)."""

    pane_id: Optional[PaneId] = None
    """Pane ID (pane-based only)."""


@dataclass
class TeammateMessage:
    """Message to send to a teammate."""

    text: str
    """Message content."""

    from_agent: str
    """Sender agent ID."""

    color: Optional[str] = None
    """Sender display color."""

    timestamp: Optional[str] = None
    """Message timestamp (ISO string)."""

    summary: Optional[str] = None
    """5-10 word summary shown as preview in the UI."""


# ---------------------------------------------------------------------------
# TeammateExecutor interface
# ---------------------------------------------------------------------------


class TeammateExecutor(ABC):
    """
    Common interface for teammate execution backends.
    Abstracts differences between pane-based and in-process execution.
    """

    @property
    @abstractmethod
    def type(self) -> BackendType:
        """Backend type identifier."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this executor is available on the system."""
        ...

    @abstractmethod
    async def spawn(self, config: TeammateSpawnConfig) -> TeammateSpawnResult:
        """Spawn a new teammate with the given configuration."""
        ...

    @abstractmethod
    async def send_message(
        self, agent_id: str, message: TeammateMessage
    ) -> None:
        """Send a message to a teammate."""
        ...

    @abstractmethod
    async def terminate(
        self, agent_id: str, reason: Optional[str] = None
    ) -> bool:
        """Terminate a teammate (graceful shutdown request)."""
        ...

    @abstractmethod
    async def kill(self, agent_id: str) -> bool:
        """Force kill a teammate (immediate termination)."""
        ...

    @abstractmethod
    async def is_active(self, agent_id: str) -> bool:
        """Check if a teammate is still active."""
        ...


# ---------------------------------------------------------------------------
# Type Guards
# ---------------------------------------------------------------------------


def is_pane_backend(backend_type: BackendType) -> bool:
    """Type guard to check if a backend type uses terminal panes."""
    return backend_type in ("tmux", "iterm2")
