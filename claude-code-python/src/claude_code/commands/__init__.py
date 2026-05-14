"""Command registry and helpers.
Ported from commands.ts (754 lines) — full implementation.

This module serves as both the commands package init AND the top-level
command registry (mirroring the structure of the TS commands.ts file).
"""
from __future__ import annotations

import importlib
import logging
import os
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Re-export type stubs (mirror TS re-exports)
# ---------------------------------------------------------------------------
try:
    from claude_code.types.command import (  # type: ignore
        Command,
        CommandBase,
        CommandResultDisplay,
        LocalCommandResult,
        PromptCommand,
        get_command_name,
        is_command_enabled,
    )
    _HAS_COMMAND_TYPES = True
except ImportError:
    _HAS_COMMAND_TYPES = False
    Command = Any  # type: ignore
    CommandBase = Any  # type: ignore
    CommandResultDisplay = Any  # type: ignore
    LocalCommandResult = Any  # type: ignore
    PromptCommand = Any  # type: ignore

    def get_command_name(cmd: Any) -> str:  # type: ignore
        return getattr(cmd, "name", "")

    def is_command_enabled(cmd: Any) -> bool:  # type: ignore
        return getattr(cmd, "enabled", True)


# ---------------------------------------------------------------------------
# Auth / provider guards
# ---------------------------------------------------------------------------

def _is_using_3p_services() -> bool:
    try:
        from claude_code.utils.auth import is_using_3p_services  # type: ignore
        return is_using_3p_services()
    except ImportError:
        provider = os.environ.get("CLAUDE_CODE_USE_BEDROCK", "") or os.environ.get("CLAUDE_CODE_USE_VERTEX", "")
        return bool(provider)


def _is_claude_ai_subscriber() -> bool:
    try:
        from claude_code.utils.auth import is_claude_ai_subscriber  # type: ignore
        return is_claude_ai_subscriber()
    except ImportError:
        return False


def _is_first_party_anthropic_base_url() -> bool:
    try:
        from claude_code.utils.model.providers import is_first_party_anthropic_base_url  # type: ignore
        return is_first_party_anthropic_base_url()
    except ImportError:
        return True


def _is_feature_enabled(flag: str) -> bool:
    """Check a feature flag (env-var based fallback)."""
    return os.environ.get(f"FEATURE_{flag}", "").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Lazy command loader — mirrors TS _try_import pattern
# ---------------------------------------------------------------------------

def _try_import(module_path: str, attr: str = "default") -> Optional[Any]:
    """Attempt to import *attr* from *module_path*, returning None on failure."""
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, attr, None)
    except ImportError:
        return None
    except Exception as exc:
        logger.debug("Failed to import %s.%s: %s", module_path, attr, exc)
        return None


# ---------------------------------------------------------------------------
# Static command instances loaded at first call
# ---------------------------------------------------------------------------

def _load_builtin_commands() -> List[Any]:
    """Load all builtin (non-skill) command objects.

    Mirrors the COMMANDS() array in the TS source.  Each entry is imported
    lazily so import errors are isolated and don't break the whole registry.
    """
    base = "claude_code.commands"
    cmds: List[Any] = []

    def add(path: str, attr: str = "default") -> None:
        cmd = _try_import(f"{base}.{path}", attr)
        if cmd is not None:
            cmds.append(cmd)

    # --- Alphabetical, mirroring the TS COMMANDS() array ---
    add("add_dir.index")
    add("advisor")
    add("agents.index")
    add("branch.index")
    add("btw.index")
    add("chrome.index")
    add("clear.index")
    add("color.index")
    add("compact.index")
    add("config.index")
    add("copy.index")
    add("desktop.index")
    add("context.index", "context")
    add("context.index", "context_non_interactive")
    add("cost.index")
    add("diff.index")
    add("doctor.index")
    add("effort.index")
    add("exit.index")
    add("fast.index")
    add("files.index")
    add("heapdump.index")
    add("help.index")
    add("ide.index")
    add("init")
    add("keybindings.index")
    add("install_github_app.index")
    add("install_slack_app.index")
    add("mcp.index")
    add("memory.index")
    add("mobile.index")
    add("model.index")
    add("output_style.index")
    add("remote_env.index")
    add("plugin.index")
    add("pr_comments.index")
    add("release_notes.index")
    add("reload_plugins.index")
    add("rename.index")
    add("resume.index")
    add("session.index")
    add("skills.index")
    add("stats.index")
    add("status.index")
    add("statusline")
    add("stickers.index")
    add("tag.index")
    add("theme.index")
    add("feedback.index")
    add("review", "review")
    add("review", "ultrareview")
    add("rewind.index")
    add("security_review")
    add("terminal_setup.index")
    add("upgrade.index")
    add("extra_usage.index", "extra_usage")
    add("extra_usage.index", "extra_usage_non_interactive")
    add("rate_limit_options.index")
    add("usage.index")
    # Lazy "insights" command (heavy module)
    _insights = _make_insights_command()
    if _insights is not None:
        cmds.append(_insights)
    add("vim.index")
    add("thinkback.index")
    add("thinkback_play.index")
    add("permissions.index")
    add("plan.index")
    add("privacy_settings.index")
    add("hooks.index")
    add("export.index")
    add("sandbox_toggle.index")
    add("passes.index")
    add("tasks.index")

    # Feature-gated commands
    if not _is_using_3p_services():
        add("logout.index")
        add("login.index")

    if _is_feature_enabled("PROACTIVE") or _is_feature_enabled("KAIROS"):
        add("proactive")
    if _is_feature_enabled("KAIROS") or _is_feature_enabled("KAIROS_BRIEF"):
        add("brief")
    if _is_feature_enabled("KAIROS"):
        add("assistant.index")
    if _is_feature_enabled("BRIDGE_MODE"):
        add("bridge.index")
    if _is_feature_enabled("DAEMON") and _is_feature_enabled("BRIDGE_MODE"):
        add("remote_control_server.index")
    if _is_feature_enabled("VOICE_MODE"):
        add("voice.index")
    if _is_feature_enabled("HISTORY_SNIP"):
        add("force_snip")
    if _is_feature_enabled("WORKFLOW_SCRIPTS"):
        add("workflows.index")
    if _is_feature_enabled("CCR_REMOTE_SETUP"):
        add("remote_setup.index")
    if _is_feature_enabled("KAIROS_GITHUB_WEBHOOKS"):
        add("subscribe_pr")
    if _is_feature_enabled("ULTRAPLAN"):
        add("ultraplan")
    if _is_feature_enabled("TORCH"):
        add("torch")
    if _is_feature_enabled("UDS_INBOX"):
        add("peers.index")
    if _is_feature_enabled("FORK_SUBAGENT"):
        add("fork.index")
    if _is_feature_enabled("BUDDY"):
        add("buddy.index")

    # Ant-only internal commands
    if os.environ.get("USER_TYPE") == "ant" and not os.environ.get("IS_DEMO"):
        cmds.extend(_get_internal_only_commands())

    return [c for c in cmds if c is not None]


def _make_insights_command() -> Optional[Any]:
    """Create the lazy 'insights' command shim (avoids loading heavy module at startup)."""
    try:
        class _InsightsCommand:
            type = "prompt"
            name = "insights"
            description = "Generate a report analyzing your Claude Code sessions"
            content_length = 0
            progress_message = "analyzing your sessions"
            source = "builtin"
            is_enabled = None  # use default (enabled)

            async def get_prompt_for_command(self, args: Any, context: Any) -> Any:
                real = _try_import("claude_code.commands.insights", "default")
                if real is None:
                    raise RuntimeError("insights command unavailable")
                if getattr(real, "type", None) != "prompt":
                    raise RuntimeError("unreachable")
                return await real.get_prompt_for_command(args, context)

        return _InsightsCommand()
    except Exception:
        return None


def _get_internal_only_commands() -> List[Any]:
    """Commands that are only available for Anthropic-internal (ant) users."""
    base = "claude_code.commands"

    def imp(path: str, attr: str = "default") -> Optional[Any]:
        return _try_import(f"{base}.{path}", attr)

    return [c for c in [
        imp("backfill_sessions.index"),
        imp("break_cache.index"),
        imp("bughunter.index"),
        imp("commit"),
        imp("commit_push_pr"),
        imp("ctx_viz.index"),
        imp("good_claude.index"),
        imp("issue.index"),
        imp("init_verifiers"),
        imp("mock_limits.index"),
        imp("bridge_kick"),
        imp("version"),
        imp("reset_limits.index", "reset_limits"),
        imp("reset_limits.index", "reset_limits_non_interactive"),
        imp("onboarding.index"),
        imp("share.index"),
        imp("summary.index"),
        imp("teleport.index"),
        imp("ant_trace.index"),
        imp("perf_issue.index"),
        imp("env.index"),
        imp("oauth_refresh.index"),
        imp("debug_tool_call.index"),
        imp("agents_platform.index"),
        imp("autofix_pr.index"),
    ] if c is not None]


# ---------------------------------------------------------------------------
# Skill loaders
# ---------------------------------------------------------------------------

async def _get_skills(cwd: str) -> Dict[str, List[Any]]:
    """Load skill commands from all sources."""
    skill_dir_commands: List[Any] = []
    plugin_skills: List[Any] = []
    bundled_skills: List[Any] = []
    builtin_plugin_skills: List[Any] = []

    try:
        from claude_code.skills.load_skills_dir import get_skill_dir_commands  # type: ignore
        try:
            skill_dir_commands = await get_skill_dir_commands(cwd)
        except Exception as err:
            logger.error("Skill directory commands failed to load: %s", err)
    except ImportError:
        pass

    try:
        from claude_code.utils.plugins.load_plugin_commands import get_plugin_skills  # type: ignore
        try:
            plugin_skills = await get_plugin_skills()
        except Exception as err:
            logger.error("Plugin skills failed to load: %s", err)
    except ImportError:
        pass

    try:
        from claude_code.skills.bundled_skills import get_bundled_skills  # type: ignore
        bundled_skills = get_bundled_skills()
    except ImportError:
        pass

    try:
        from claude_code.plugins.builtin_plugins import get_builtin_plugin_skill_commands  # type: ignore
        builtin_plugin_skills = get_builtin_plugin_skill_commands()
    except ImportError:
        pass

    logger.debug(
        "getSkills returning: %d skill dir, %d plugin, %d bundled, %d builtin",
        len(skill_dir_commands), len(plugin_skills), len(bundled_skills), len(builtin_plugin_skills),
    )
    return {
        "skill_dir_commands": skill_dir_commands,
        "plugin_skills": plugin_skills,
        "bundled_skills": bundled_skills,
        "builtin_plugin_skills": builtin_plugin_skills,
    }


# ---------------------------------------------------------------------------
# Availability filter
# ---------------------------------------------------------------------------

def meets_availability_requirement(cmd: Any) -> bool:
    """Return True if *cmd* is available for the current user/provider.

    Commands without an ``availability`` attribute are treated as universal.
    """
    availability = getattr(cmd, "availability", None)
    if not availability:
        return True
    for a in availability:
        if a == "claude-ai":
            if _is_claude_ai_subscriber():
                return True
        elif a == "console":
            if (
                not _is_claude_ai_subscriber()
                and not _is_using_3p_services()
                and _is_first_party_anthropic_base_url()
            ):
                return True
    return False


# ---------------------------------------------------------------------------
# Memoized command loader
# ---------------------------------------------------------------------------

_loaded_commands_cache: Dict[str, List[Any]] = {}
_builtin_commands_cache: Optional[List[Any]] = None


def _get_builtin_commands() -> List[Any]:
    global _builtin_commands_cache
    if _builtin_commands_cache is None:
        _builtin_commands_cache = _load_builtin_commands()
    return _builtin_commands_cache


async def _load_all_commands(cwd: str) -> List[Any]:
    """Load all commands (skills + plugins + builtins). Memoized by cwd."""
    if cwd in _loaded_commands_cache:
        return _loaded_commands_cache[cwd]

    skills_data = await _get_skills(cwd)

    plugin_commands: List[Any] = []
    try:
        from claude_code.utils.plugins.load_plugin_commands import get_plugin_commands  # type: ignore
        plugin_commands = await get_plugin_commands()
    except ImportError:
        pass

    workflow_commands: List[Any] = []
    if _is_feature_enabled("WORKFLOW_SCRIPTS"):
        try:
            from claude_code.tools.workflow_tool.create_workflow_command import get_workflow_commands  # type: ignore
            workflow_commands = await get_workflow_commands(cwd)
        except ImportError:
            pass

    all_cmds = [
        *skills_data["bundled_skills"],
        *skills_data["builtin_plugin_skills"],
        *skills_data["skill_dir_commands"],
        *workflow_commands,
        *plugin_commands,
        *skills_data["plugin_skills"],
        *_get_builtin_commands(),
    ]

    _loaded_commands_cache[cwd] = all_cmds
    return all_cmds


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_commands(cwd: str) -> List[Any]:
    """Return commands available to the current user.

    The expensive loading is memoized, but availability and isEnabled checks
    run fresh every call so auth changes (e.g. /login) take effect immediately.
    """
    all_commands = await _load_all_commands(cwd)

    # Dynamic skills discovered during file operations
    dynamic_skills: List[Any] = []
    try:
        from claude_code.skills.load_skills_dir import get_dynamic_skills  # type: ignore
        dynamic_skills = get_dynamic_skills()
    except ImportError:
        pass

    base_commands = [
        c for c in all_commands
        if meets_availability_requirement(c) and is_command_enabled(c)
    ]

    if not dynamic_skills:
        return base_commands

    base_names: Set[str] = {getattr(c, "name", "") for c in base_commands}
    unique_dynamic = [
        s for s in dynamic_skills
        if (
            getattr(s, "name", None) not in base_names
            and meets_availability_requirement(s)
            and is_command_enabled(s)
        )
    ]

    if not unique_dynamic:
        return base_commands

    # Insert dynamic skills before the first builtin command
    builtin_names: Set[str] = {getattr(c, "name", "") for c in _get_builtin_commands()}
    insert_index = next(
        (i for i, c in enumerate(base_commands) if getattr(c, "name", None) in builtin_names),
        -1,
    )

    if insert_index == -1:
        return [*base_commands, *unique_dynamic]

    return [
        *base_commands[:insert_index],
        *unique_dynamic,
        *base_commands[insert_index:],
    ]


def builtin_command_names() -> Set[str]:
    """Return the set of all builtin command names (including aliases)."""
    names: Set[str] = set()
    for cmd in _get_builtin_commands():
        name = getattr(cmd, "name", None)
        if name:
            names.add(name)
        aliases = getattr(cmd, "aliases", None) or []
        names.update(aliases)
    return names


def clear_command_memoization_caches() -> None:
    """Clear only the memoization caches for commands (not skill caches)."""
    global _loaded_commands_cache
    _loaded_commands_cache.clear()

    # Clear skill index if available
    try:
        from claude_code.services.skill_search.local_search import clear_skill_index_cache  # type: ignore
        clear_skill_index_cache()
    except ImportError:
        pass


def clear_commands_cache() -> None:
    """Clear all command and skill caches."""
    clear_command_memoization_caches()

    try:
        from claude_code.utils.plugins.load_plugin_commands import (  # type: ignore
            clear_plugin_command_cache,
            clear_plugin_skills_cache,
        )
        clear_plugin_command_cache()
        clear_plugin_skills_cache()
    except ImportError:
        pass

    try:
        from claude_code.skills.load_skills_dir import clear_skill_caches  # type: ignore
        clear_skill_caches()
    except ImportError:
        pass


def get_mcp_skill_commands(mcp_commands: List[Any]) -> List[Any]:
    """Filter MCP commands to only include model-invocable skills."""
    if not _is_feature_enabled("MCP_SKILLS"):
        return []
    return [
        cmd for cmd in mcp_commands
        if (
            getattr(cmd, "type", None) == "prompt"
            and getattr(cmd, "loaded_from", None) == "mcp"
            and not getattr(cmd, "disable_model_invocation", False)
        )
    ]


async def get_skill_tool_commands(cwd: str) -> List[Any]:
    """Return all prompt-based commands the model can invoke as skills."""
    all_commands = await get_commands(cwd)
    return [
        cmd for cmd in all_commands
        if (
            getattr(cmd, "type", None) == "prompt"
            and not getattr(cmd, "disable_model_invocation", False)
            and getattr(cmd, "source", None) != "builtin"
            and (
                getattr(cmd, "loaded_from", None) in ("bundled", "skills", "commands_DEPRECATED")
                or getattr(cmd, "has_user_specified_description", False)
                or getattr(cmd, "when_to_use", None)
            )
        )
    ]


async def get_slash_command_tool_skills(cwd: str) -> List[Any]:
    """Return commands that are skills (not generic prompt commands)."""
    try:
        all_commands = await get_commands(cwd)
        return [
            cmd for cmd in all_commands
            if (
                getattr(cmd, "type", None) == "prompt"
                and getattr(cmd, "source", None) != "builtin"
                and (
                    getattr(cmd, "has_user_specified_description", False)
                    or getattr(cmd, "when_to_use", None)
                )
                and (
                    getattr(cmd, "loaded_from", None) in ("skills", "plugin", "bundled")
                    or getattr(cmd, "disable_model_invocation", False)
                )
            )
        ]
    except Exception as err:
        logger.error("Returning empty skills array due to load failure: %s", err)
        return []


# ---------------------------------------------------------------------------
# Remote / bridge helpers
# ---------------------------------------------------------------------------

def _get_remote_safe_command_names() -> Set[str]:
    """Names of commands that are safe in remote (--remote) mode."""
    return {
        "session", "exit", "clear", "help", "theme", "color", "vim",
        "cost", "usage", "copy", "btw", "feedback", "plan", "keybindings",
        "statusline", "stickers", "mobile",
    }


def _get_bridge_safe_command_names() -> Set[str]:
    """Names of 'local'-type commands safe to execute from the bridge."""
    return {"compact", "clear", "cost", "summary", "release-notes", "files"}


def is_bridge_safe_command(cmd: Any) -> bool:
    """Return True if *cmd* can be executed when received over the Remote Control bridge."""
    cmd_type = getattr(cmd, "type", None)
    if cmd_type == "local-jsx":
        return False
    if cmd_type == "prompt":
        return True
    cmd_name = getattr(cmd, "name", "")
    return cmd_name in _get_bridge_safe_command_names()


def filter_commands_for_remote_mode(commands: List[Any]) -> List[Any]:
    """Filter commands to only those safe for remote mode."""
    safe = _get_remote_safe_command_names()
    return [c for c in commands if getattr(c, "name", "") in safe]


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def find_command(command_name: str, commands: List[Any]) -> Optional[Any]:
    """Find a command by name or alias."""
    for cmd in commands:
        name = getattr(cmd, "name", None)
        try:
            computed_name = get_command_name(cmd)
        except (AttributeError, TypeError):
            computed_name = name
        aliases = getattr(cmd, "aliases", None) or []
        if name == command_name or computed_name == command_name or command_name in aliases:
            return cmd
    return None


def has_command(command_name: str, commands: List[Any]) -> bool:
    """Return True if *command_name* exists in *commands*."""
    return find_command(command_name, commands) is not None


def get_command(command_name: str, commands: List[Any]) -> Any:
    """Return the command with *command_name* or raise ReferenceError."""
    cmd = find_command(command_name, commands)
    if cmd is None:
        def _fmt(c: Any) -> str:
            try:
                n = get_command_name(c)
            except (AttributeError, TypeError):
                n = getattr(c, "name", "?")
            aliases = getattr(c, "aliases", None)
            return f"{n} (aliases: {', '.join(aliases)})" if aliases else n

        available = sorted(_fmt(c) for c in commands)
        raise ReferenceError(
            f"Command {command_name} not found. Available commands: {', '.join(available)}"
        )
    return cmd


# ---------------------------------------------------------------------------
# Description formatting
# ---------------------------------------------------------------------------

def format_description_with_source(cmd: Any) -> str:
    """Format a command's description with its source annotation for user-facing UI."""
    description = getattr(cmd, "description", "")
    cmd_type = getattr(cmd, "type", None)

    if cmd_type != "prompt":
        return description

    kind = getattr(cmd, "kind", None)
    if kind == "workflow":
        return f"{description} (workflow)"

    source = getattr(cmd, "source", None)
    if source == "plugin":
        plugin_info = getattr(cmd, "plugin_info", None)
        plugin_name: Optional[str] = None
        if plugin_info:
            manifest = getattr(plugin_info, "plugin_manifest", None)
            if manifest is None and isinstance(plugin_info, dict):
                manifest = plugin_info.get("plugin_manifest", {})
            plugin_name = (
                getattr(manifest, "name", None)
                if not isinstance(manifest, dict)
                else manifest.get("name")
            )
        if plugin_name:
            return f"({plugin_name}) {description}"
        return f"{description} (plugin)"

    if source in ("builtin", "mcp"):
        return description

    if source == "bundled":
        return f"{description} (bundled)"

    # User-configured skill — show setting source name
    try:
        from claude_code.utils.settings.constants import get_setting_source_name  # type: ignore
        return f"{description} ({get_setting_source_name(source)})"
    except ImportError:
        return f"{description} ({source})" if source else description
