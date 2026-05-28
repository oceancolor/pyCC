"""
Command type definitions
原始 TS: src/types/command.ts

TypeScript interface/type → Python dataclass/TypedDict/Literal
React.ReactNode → Any (TODO: 替换为实际 UI 框架类型)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Literal,
    Optional,
    Union,
)

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# LocalCommandResult  (discriminated union → Union of dataclasses)
# ---------------------------------------------------------------------------

@dataclass
class LocalCommandResultText:
    """type: 'text'"""
    type: Literal["text"] = "text"
    value: str = ""


@dataclass
class LocalCommandResultCompact:
    """type: 'compact'"""
    type: Literal["compact"] = "compact"
    compaction_result: Any = None      # CompactionResult (forward ref)
    display_text: Optional[str] = None


@dataclass
class LocalCommandResultSkip:
    """type: 'skip'"""
    type: Literal["skip"] = "skip"


LocalCommandResult = Union[
    LocalCommandResultText,
    LocalCommandResultCompact,
    LocalCommandResultSkip,
]


# ---------------------------------------------------------------------------
# PromptCommand
# ---------------------------------------------------------------------------

@dataclass
class PluginInfo:
    plugin_manifest: Any          # PluginManifest (forward ref)
    repository: str


@dataclass
class PromptCommand:
    """
    原始 TS: PromptCommand
    type: 'prompt'
    """
    type: Literal["prompt"] = "prompt"
    progress_message: str = ""
    content_length: int = 0
    arg_names: Optional[list[str]] = None
    allowed_tools: Optional[list[str]] = None
    model: Optional[str] = None
    source: str = "builtin"         # SettingSource | 'builtin' | 'mcp' | 'plugin' | 'bundled'
    plugin_info: Optional[PluginInfo] = None
    disable_non_interactive: Optional[bool] = None
    hooks: Optional[Any] = None     # HooksSettings (forward ref)
    skill_root: Optional[str] = None
    context: Optional[Literal["inline", "fork"]] = None
    agent: Optional[str] = None
    effort: Optional[Any] = None    # EffortValue (forward ref)
    paths: Optional[list[str]] = None
    # async fn(args, context) → ContentBlockParam[]
    get_prompt_for_command: Optional[Callable[..., Awaitable[list[Any]]]] = None


# ---------------------------------------------------------------------------
# LocalCommand (lazy-loaded)
# ---------------------------------------------------------------------------

# TS: (args: string, context: LocalJSXCommandContext) => Promise<LocalCommandResult>
LocalCommandCall = Callable[..., Awaitable[LocalCommandResult]]

@dataclass
class LocalCommandModule:
    call: LocalCommandCall


@dataclass
class LocalCommand:
    """type: 'local'"""
    type: Literal["local"] = "local"
    supports_non_interactive: bool = False
    load: Optional[Callable[[], Awaitable[LocalCommandModule]]] = None


# ---------------------------------------------------------------------------
# LocalJSXCommand
# ---------------------------------------------------------------------------

@dataclass
class LocalJSXCommandContext:
    """
    原始 TS: LocalJSXCommandContext
    混合了 ToolUseContext + 额外字段
    TODO: 完善 ToolUseContext 后填入
    """
    can_use_tool: Optional[Any] = None          # CanUseToolFn
    set_messages: Optional[Callable[..., None]] = None
    options: Optional[dict[str, Any]] = None
    on_change_api_key: Optional[Callable[[], None]] = None
    on_change_dynamic_mcp_config: Optional[Callable[..., None]] = None
    on_install_ide_extension: Optional[Callable[..., None]] = None
    resume: Optional[Callable[..., Awaitable[None]]] = None


ResumeEntrypoint = Literal[
    "cli_flag",
    "slash_command_picker",
    "slash_command_session_id",
    "slash_command_title",
    "fork",
]

CommandResultDisplay = Literal["skip", "system", "user"]

# TS: LocalJSXCommandOnDone callback
LocalJSXCommandOnDone = Callable[..., None]

# TS: LocalJSXCommandCall → (onDone, context, args) → Promise<React.ReactNode>
LocalJSXCommandCall = Callable[..., Awaitable[Any]]  # ReactNode → Any


@dataclass
class LocalJSXCommandModule:
    call: LocalJSXCommandCall


@dataclass
class LocalJSXCommand:
    """type: 'local-jsx'"""
    type: Literal["local-jsx"] = "local-jsx"
    load: Optional[Callable[[], Awaitable[LocalJSXCommandModule]]] = None


# ---------------------------------------------------------------------------
# CommandAvailability & CommandBase & Command
# ---------------------------------------------------------------------------

CommandAvailability = Literal["claude-ai", "console"]


@dataclass
class CommandBase:
    """
    原始 TS: CommandBase
    所有命令的公共字段
    """
    name: str = ""
    description: str = ""
    has_user_specified_description: Optional[bool] = None
    is_enabled: Optional[Callable[[], bool]] = None
    is_hidden: Optional[bool] = None
    aliases: Optional[list[str]] = None
    is_mcp: Optional[bool] = None
    argument_hint: Optional[str] = None
    when_to_use: Optional[str] = None
    version: Optional[str] = None
    availability: Optional[list[CommandAvailability]] = None
    disable_model_invocation: Optional[bool] = None
    user_invocable: Optional[bool] = None
    loaded_from: Optional[str] = None   # 'commands_DEPRECATED' | 'skills' | 'plugin' | ...
    kind: Optional[Literal["workflow"]] = None
    immediate: Optional[bool] = None
    is_sensitive: Optional[bool] = None
    user_facing_name: Optional[Callable[[], str]] = None


# Command = CommandBase + one of (PromptCommand | LocalCommand | LocalJSXCommand)
# Python: represent as a union type alias
Command = Any   # TODO: 使用 typing.Union[...] 配合 TypedDict 或协议改进


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_command_name(cmd: Any) -> str:
    """Resolves the user-visible name, falling back to cmd.name.

    Uses getattr so that command objects that do not inherit from CommandBase
    are handled gracefully.
    """
    user_facing_name = getattr(cmd, "user_facing_name", None)
    if user_facing_name is not None:
        return user_facing_name()
    return getattr(cmd, "name", "")


def is_command_enabled(cmd: Any) -> bool:
    """Resolves whether the command is enabled, defaulting to True.

    Uses getattr with a default of None so that command objects that do not
    inherit from CommandBase (and therefore lack an is_enabled attribute) are
    treated as enabled, matching the original TypeScript behaviour.
    """
    is_enabled = getattr(cmd, "is_enabled", None)
    if is_enabled is not None:
        return is_enabled()
    return True
