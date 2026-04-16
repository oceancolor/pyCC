"""
Tool base classes and interfaces
原始 TS: src/Tool.ts (core types + buildTool)

React/Ink UI components → TODO stubs
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Coroutine,
    Generic,
    Optional,
    TypeVar,
    Union,
)

if TYPE_CHECKING:
    from claude_code.types.permissions import (
        PermissionMode,
        AdditionalWorkingDirectory,
        PermissionResult,
    )

# ---------------------------------------------------------------------------
# Type vars
# ---------------------------------------------------------------------------

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")

# ---------------------------------------------------------------------------
# Tool Input / JSON Schema
# ---------------------------------------------------------------------------

ToolInputJSONSchema = dict[str, Any]  # {type:'object', properties: {...}}


@dataclass
class ValidationResultOk:
    result: bool = True


@dataclass
class ValidationResultFail:
    result: bool = False
    message: str = ""
    error_code: int = 0


ValidationResult = Union[ValidationResultOk, ValidationResultFail]

# ---------------------------------------------------------------------------
# ToolUseContext  (partial — full version requires AppState etc.)
# ---------------------------------------------------------------------------

@dataclass
class ToolUseOptions:
    """Options passed down to tool execution context."""
    commands: list[Any] = field(default_factory=list)
    debug: bool = False
    main_loop_model: str = ""
    tools: list[Any] = field(default_factory=list)
    verbose: bool = False
    mcp_clients: list[Any] = field(default_factory=list)
    mcp_resources: dict[str, Any] = field(default_factory=dict)
    is_non_interactive_session: bool = False
    agent_definitions: Any = None
    max_budget_usd: Optional[float] = None
    custom_system_prompt: Optional[str] = None
    append_system_prompt: Optional[str] = None
    query_source: Optional[str] = None
    refresh_tools: Optional[Callable[[], list[Any]]] = None


@dataclass
class ToolUseContext:
    """Context passed to tool calls."""
    options: ToolUseOptions = field(default_factory=ToolUseOptions)
    abort_controller: Optional[Any] = None   # asyncio.Event equivalent
    read_file_state: Optional[Any] = None
    get_app_state: Optional[Callable[[], Any]] = None
    set_app_state: Optional[Callable[[Callable], None]] = None
    set_tool_jsx: Optional[Any] = None       # TODO: UI callback
    add_notification: Optional[Callable[[Any], None]] = None
    append_system_message: Optional[Callable[[Any], None]] = None
    send_os_notification: Optional[Callable[[dict], None]] = None


def get_empty_tool_use_context() -> ToolUseContext:
    return ToolUseContext()


# ---------------------------------------------------------------------------
# ToolCallProgress
# ---------------------------------------------------------------------------

@dataclass
class ToolCallProgress:
    type: str = ""
    message: str = ""
    data: Optional[Any] = None


# ---------------------------------------------------------------------------
# Tool base class
# ---------------------------------------------------------------------------

class Tool(abc.ABC):
    """
    Abstract base class for all tools.
    原始 TS: ToolDef + buildTool pattern
    """

    #: Tool name (must be unique, used in API calls)
    name: str = ""

    #: Human-readable search hint
    search_hint: str = ""

    #: Max result size in characters
    max_result_size_chars: int = 10_000_000

    @abc.abstractmethod
    async def description(self) -> str:
        """Return the tool description for the system prompt."""
        ...

    @abc.abstractmethod
    async def prompt(self) -> str:
        """Return the detailed prompt / instructions for the tool."""
        ...

    @abc.abstractmethod
    def input_schema(self) -> ToolInputJSONSchema:
        """Return the JSON schema for the tool's input parameters."""
        ...

    @abc.abstractmethod
    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> Any:
        """Execute the tool with the given input."""
        ...

    async def validate_input(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> ValidationResult:
        """Validate tool input. Default: always valid."""
        return ValidationResultOk()

    async def check_permission(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> "PermissionResult":
        """Check if the tool call is permitted. Default: allow."""
        from claude_code.types.permissions import PermissionAllowDecision
        return PermissionAllowDecision()

    def user_facing_name(self, input_data: Optional[dict[str, Any]] = None) -> str:
        """Return the user-facing name for the tool call."""
        return self.name

    def get_tool_use_summary(self, input_data: dict[str, Any]) -> Optional[str]:
        """Return a one-line summary of the tool call."""
        return None


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

_TOOL_REGISTRY: dict[str, type[Tool]] = {}


def register_tool(tool_cls: type[Tool]) -> type[Tool]:
    """Decorator: register a tool class."""
    _TOOL_REGISTRY[tool_cls.name] = tool_cls
    return tool_cls


def get_registered_tools() -> dict[str, type[Tool]]:
    return dict(_TOOL_REGISTRY)
