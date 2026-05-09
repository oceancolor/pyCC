"""Shared event metadata enrichment for analytics systems.

Ported from services/analytics/metadata.ts

This module provides a single source of truth for collecting and formatting
event metadata across all analytics systems.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import platform
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from functools import lru_cache
from os.path import splitext
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# ---------------------------------------------------------------------------
# Optional internal-dep shims
# ---------------------------------------------------------------------------

def _get_session_id() -> str:
    try:
        from claude_code.bootstrap.state import get_session_id  # type: ignore
        return get_session_id()
    except (ImportError, Exception):
        return os.environ.get("SESSION_ID", "")


def _get_is_interactive() -> bool:
    try:
        from claude_code.bootstrap.state import get_is_interactive  # type: ignore
        return get_is_interactive()
    except (ImportError, Exception):
        return True


def _get_kairos_active() -> bool:
    try:
        from claude_code.bootstrap.state import get_kairos_active  # type: ignore
        return get_kairos_active()
    except (ImportError, Exception):
        return False


def _get_client_type() -> str:
    try:
        from claude_code.bootstrap.state import get_client_type  # type: ignore
        return get_client_type()
    except (ImportError, Exception):
        return ""


def _get_parent_session_id_from_state() -> Optional[str]:
    try:
        from claude_code.bootstrap.state import get_parent_session_id  # type: ignore
        return get_parent_session_id()
    except (ImportError, Exception):
        return None


def _get_main_loop_model() -> str:
    try:
        from claude_code.utils.model.model import get_main_loop_model  # type: ignore
        return get_main_loop_model()
    except (ImportError, Exception):
        return os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-5")


def _get_model_betas(model: str) -> List[str]:
    try:
        from claude_code.utils.betas import get_model_betas  # type: ignore
        return get_model_betas(model)
    except (ImportError, Exception):
        return []


def _get_host_platform_for_analytics() -> str:
    try:
        from claude_code.utils.env import get_host_platform_for_analytics  # type: ignore
        return get_host_platform_for_analytics()
    except (ImportError, Exception):
        p = sys.platform
        if p == "win32":
            return "windows"
        if p == "darwin":
            return "mac"
        return "linux"


def _is_env_truthy(val: Optional[str]) -> bool:
    if not val:
        return False
    return val.strip().lower() not in ("0", "false", "no", "")


def _get_package_managers() -> List[str]:
    try:
        from claude_code.utils.env import env  # type: ignore
        return env.get_package_managers()
    except (ImportError, Exception):
        import shutil
        managers = []
        for pm in ("npm", "yarn", "pnpm", "pip", "pip3", "poetry", "uv"):
            if shutil.which(pm):
                managers.append(pm)
        return managers


def _get_runtimes() -> List[str]:
    try:
        from claude_code.utils.env import env  # type: ignore
        return env.get_runtimes()
    except (ImportError, Exception):
        import shutil
        runtimes = []
        for rt in ("node", "bun", "deno", "python", "python3"):
            if shutil.which(rt):
                runtimes.append(rt)
        return runtimes


def _get_linux_distro_info() -> Optional[Dict[str, str]]:
    try:
        from claude_code.utils.platform import get_linux_distro_info  # type: ignore
        return get_linux_distro_info()
    except (ImportError, Exception):
        if sys.platform != "linux":
            return None
        info: Dict[str, str] = {}
        try:
            import distro  # type: ignore
            info["linuxDistroId"] = distro.id()
            info["linuxDistroVersion"] = distro.version()
        except ImportError:
            pass
        try:
            info["linuxKernel"] = os.uname().release
        except Exception:
            pass
        return info or None


def _detect_vcs() -> List[str]:
    try:
        from claude_code.utils.platform import detect_vcs  # type: ignore
        return detect_vcs()
    except (ImportError, Exception):
        import shutil
        result = []
        for vcs in ("git", "hg", "svn"):
            if shutil.which(vcs):
                result.append(vcs)
        return result


def _get_wsl_version() -> Optional[str]:
    try:
        from claude_code.utils.platform import get_wsl_version  # type: ignore
        return get_wsl_version()
    except (ImportError, Exception):
        return os.environ.get("WSL_DISTRO_NAME")


def _get_repo_remote_hash() -> Optional[str]:
    try:
        from claude_code.utils.git import get_repo_remote_hash  # type: ignore
        return asyncio.get_event_loop().run_until_complete(get_repo_remote_hash())
    except (ImportError, Exception):
        return None


def _is_official_mcp_url(url: str) -> bool:
    try:
        from claude_code.services.mcp.official_registry import is_official_mcp_url  # type: ignore
        return is_official_mcp_url(url)
    except (ImportError, Exception):
        return False


def _is_claude_ai_subscriber() -> bool:
    try:
        from claude_code.utils.auth import is_claude_ai_subscriber  # type: ignore
        return is_claude_ai_subscriber()
    except (ImportError, Exception):
        return False


def _get_subscription_type() -> Optional[str]:
    try:
        from claude_code.utils.auth import get_subscription_type  # type: ignore
        return get_subscription_type()
    except (ImportError, Exception):
        return None


def _get_agent_context():
    try:
        from claude_code.utils.agent_context import get_agent_context  # type: ignore
        return get_agent_context()
    except (ImportError, Exception):
        return None


def _get_teammate_agent_id() -> Optional[str]:
    try:
        from claude_code.utils.teammate import get_agent_id  # type: ignore
        return get_agent_id()
    except (ImportError, Exception):
        return None


def _get_teammate_parent_session_id() -> Optional[str]:
    try:
        from claude_code.utils.teammate import get_parent_session_id  # type: ignore
        return get_parent_session_id()
    except (ImportError, Exception):
        return None


def _get_team_name() -> Optional[str]:
    try:
        from claude_code.utils.teammate import get_team_name  # type: ignore
        return get_team_name()
    except (ImportError, Exception):
        return None


def _is_teammate() -> bool:
    try:
        from claude_code.utils.teammate import is_teammate  # type: ignore
        return is_teammate()
    except (ImportError, Exception):
        return False


def _detect_deployment_environment() -> str:
    try:
        from claude_code.utils.env import env  # type: ignore
        return env.detect_deployment_environment()
    except (ImportError, Exception):
        if _is_env_truthy(os.environ.get("CI")):
            return "ci"
        return "local"


def _is_conductor() -> bool:
    try:
        from claude_code.utils.env import env  # type: ignore
        return env.is_conductor()
    except (ImportError, Exception):
        return False


def _is_running_with_bun() -> bool:
    try:
        from claude_code.utils.env import env  # type: ignore
        return env.is_running_with_bun()
    except (ImportError, Exception):
        return False


def _json_stringify(obj: Any) -> str:
    try:
        from claude_code.utils.slow_operations import json_stringify  # type: ignore
        return json_stringify(obj)
    except (ImportError, Exception):
        return json.dumps(obj, default=str)


# ---------------------------------------------------------------------------
# Marker type (Python equivalent — just an alias)
# ---------------------------------------------------------------------------

# In Python there's no `never` type trick, so we use a plain str alias.
AnalyticsMetadataVerified = str


# ---------------------------------------------------------------------------
# Tool name sanitization
# ---------------------------------------------------------------------------

def sanitize_tool_name_for_analytics(tool_name: str) -> AnalyticsMetadataVerified:
    """Return 'mcp_tool' for MCP tools, original name otherwise."""
    if tool_name.startswith("mcp__"):
        return "mcp_tool"
    return tool_name


def is_tool_details_logging_enabled() -> bool:
    """True when OTEL_LOG_TOOL_DETAILS=1."""
    return _is_env_truthy(os.environ.get("OTEL_LOG_TOOL_DETAILS"))


def is_analytics_tool_details_logging_enabled(
    mcp_server_type: Optional[str],
    mcp_server_base_url: Optional[str],
) -> bool:
    """Check whether detailed MCP tool names may be logged for analytics."""
    if os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "local-agent":
        return True
    if mcp_server_type == "claudeai-proxy":
        return True
    if mcp_server_base_url and _is_official_mcp_url(mcp_server_base_url):
        return True
    return False


# Builtin MCP server names that are safe to log (not user-configured)
BUILTIN_MCP_SERVER_NAMES: Set[str] = set()
try:
    from claude_code.utils.computer_use.common import COMPUTER_USE_MCP_SERVER_NAME  # type: ignore
    BUILTIN_MCP_SERVER_NAMES.add(COMPUTER_USE_MCP_SERVER_NAME)
except (ImportError, Exception):
    pass


def mcp_tool_details_for_analytics(
    tool_name: str,
    mcp_server_type: Optional[str],
    mcp_server_base_url: Optional[str],
) -> Dict[str, AnalyticsMetadataVerified]:
    """Return {mcpServerName, mcpToolName} if logging is permitted, else {}."""
    details = extract_mcp_tool_details(tool_name)
    if not details:
        return {}
    server_name, mcp_tool_name = details
    if (
        server_name not in BUILTIN_MCP_SERVER_NAMES
        and not is_analytics_tool_details_logging_enabled(mcp_server_type, mcp_server_base_url)
    ):
        return {}
    return {"mcpServerName": server_name, "mcpToolName": mcp_tool_name}


def extract_mcp_tool_details(
    tool_name: str,
) -> Optional[Tuple[AnalyticsMetadataVerified, AnalyticsMetadataVerified]]:
    """Parse ``mcp__<server>__<tool>`` → (server_name, tool_name) or None."""
    if not tool_name.startswith("mcp__"):
        return None
    parts = tool_name.split("__")
    if len(parts) < 3:
        return None
    server_name = parts[1]
    mcp_tool_name = "__".join(parts[2:])
    if not server_name or not mcp_tool_name:
        return None
    return server_name, mcp_tool_name


def extract_skill_name(
    tool_name: str,
    input_data: Any,
) -> Optional[AnalyticsMetadataVerified]:
    """Return skill name if this is a Skill tool call, else None."""
    if tool_name != "Skill":
        return None
    if isinstance(input_data, dict) and isinstance(input_data.get("skill"), str):
        return input_data["skill"]
    return None


# ---------------------------------------------------------------------------
# Tool input truncation / telemetry
# ---------------------------------------------------------------------------

TOOL_INPUT_STRING_TRUNCATE_AT = 512
TOOL_INPUT_STRING_TRUNCATE_TO = 128
TOOL_INPUT_MAX_JSON_CHARS = 4 * 1024
TOOL_INPUT_MAX_COLLECTION_ITEMS = 20
TOOL_INPUT_MAX_DEPTH = 2


def _truncate_tool_input_value(value: Any, depth: int = 0) -> Any:
    if isinstance(value, str):
        if len(value) > TOOL_INPUT_STRING_TRUNCATE_AT:
            return f"{value[:TOOL_INPUT_STRING_TRUNCATE_TO]}…[{len(value)} chars]"
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if depth >= TOOL_INPUT_MAX_DEPTH:
        return "<nested>"
    if isinstance(value, list):
        mapped = [_truncate_tool_input_value(v, depth + 1) for v in value[:TOOL_INPUT_MAX_COLLECTION_ITEMS]]
        if len(value) > TOOL_INPUT_MAX_COLLECTION_ITEMS:
            mapped.append(f"…[{len(value)} items]")
        return mapped
    if isinstance(value, dict):
        entries = [(k, v) for k, v in value.items() if not k.startswith("_")]
        mapped = {k: _truncate_tool_input_value(v, depth + 1) for k, v in entries[:TOOL_INPUT_MAX_COLLECTION_ITEMS]}
        if len(entries) > TOOL_INPUT_MAX_COLLECTION_ITEMS:
            mapped["…"] = f"{len(entries)} keys"
        return mapped
    return str(value)


def extract_tool_input_for_telemetry(input_data: Any) -> Optional[str]:
    """Serialize tool input for OTel; returns None when not enabled."""
    if not is_tool_details_logging_enabled():
        return None
    truncated = _truncate_tool_input_value(input_data)
    json_str = _json_stringify(truncated)
    if len(json_str) > TOOL_INPUT_MAX_JSON_CHARS:
        json_str = json_str[:TOOL_INPUT_MAX_JSON_CHARS] + "…[truncated]"
    return json_str


# ---------------------------------------------------------------------------
# File-extension extraction
# ---------------------------------------------------------------------------

MAX_FILE_EXTENSION_LENGTH = 10

FILE_COMMANDS: Set[str] = {
    "rm", "mv", "cp", "touch", "mkdir", "chmod", "chown",
    "cat", "head", "tail", "sort", "stat", "diff", "wc",
    "grep", "rg", "sed",
}

_COMPOUND_OPERATOR_RE = re.compile(r"\s*(?:&&|\|\||[;|])\s*")
_WHITESPACE_RE = re.compile(r"\s+")


def get_file_extension_for_analytics(file_path: str) -> Optional[AnalyticsMetadataVerified]:
    """Extract and sanitize a file extension for analytics.

    Returns None for no extension, 'other' for suspiciously long ones.
    """
    _, ext = splitext(file_path)
    ext = ext.lower()
    if not ext or ext == ".":
        return None
    extension = ext[1:]  # strip leading dot
    if len(extension) > MAX_FILE_EXTENSION_LENGTH:
        return "other"
    return extension


def get_file_extensions_from_bash_command(
    command: str,
    simulated_sed_edit_file_path: Optional[str] = None,
) -> Optional[AnalyticsMetadataVerified]:
    """Best-effort extraction of file extensions mentioned in a bash command."""
    if "." not in command and not simulated_sed_edit_file_path:
        return None

    result: Optional[str] = None
    seen: Set[str] = set()

    if simulated_sed_edit_file_path:
        ext = get_file_extension_for_analytics(simulated_sed_edit_file_path)
        if ext:
            seen.add(ext)
            result = ext

    for subcmd in _COMPOUND_OPERATOR_RE.split(command):
        if not subcmd:
            continue
        tokens = _WHITESPACE_RE.split(subcmd.strip())
        if len(tokens) < 2:
            continue
        first_token = tokens[0]
        slash_idx = first_token.rfind("/")
        base_cmd = first_token[slash_idx + 1:] if slash_idx >= 0 else first_token
        if base_cmd not in FILE_COMMANDS:
            continue
        for arg in tokens[1:]:
            if arg.startswith("-"):
                continue
            ext = get_file_extension_for_analytics(arg)
            if ext and ext not in seen:
                seen.add(ext)
                result = (result + "," + ext) if result else ext

    return result


# ---------------------------------------------------------------------------
# EnvContext dataclass
# ---------------------------------------------------------------------------

@dataclass
class EnvContext:
    platform: str
    platform_raw: str
    arch: str
    node_version: str
    terminal: Optional[str]
    package_managers: str
    runtimes: str
    is_running_with_bun: bool
    is_ci: bool
    is_claubbit: bool
    is_claude_code_remote: bool
    is_local_agent_mode: bool
    is_conductor: bool
    is_github_action: bool
    is_claude_code_action: bool
    is_claude_ai_auth: bool
    version: str
    build_time: str
    deployment_environment: str
    # Optional fields
    remote_environment_type: Optional[str] = None
    coworker_type: Optional[str] = None
    claude_code_container_id: Optional[str] = None
    claude_code_remote_session_id: Optional[str] = None
    tags: Optional[str] = None
    github_event_name: Optional[str] = None
    github_actions_runner_environment: Optional[str] = None
    github_actions_runner_os: Optional[str] = None
    github_action_ref: Optional[str] = None
    wsl_version: Optional[str] = None
    linux_distro_id: Optional[str] = None
    linux_distro_version: Optional[str] = None
    linux_kernel: Optional[str] = None
    vcs: Optional[str] = None
    version_base: Optional[str] = None


# ---------------------------------------------------------------------------
# ProcessMetrics dataclass
# ---------------------------------------------------------------------------

@dataclass
class ProcessMetrics:
    uptime: float
    rss: int
    heap_total: int
    heap_used: int
    external: int
    array_buffers: int
    constrained_memory: Optional[int]
    cpu_user: float
    cpu_system: float
    cpu_percent: Optional[float]


# ---------------------------------------------------------------------------
# EventMetadata dataclass
# ---------------------------------------------------------------------------

@dataclass
class EventMetadata:
    model: str
    session_id: str
    user_type: str
    env_context: EnvContext
    is_interactive: str
    client_type: str
    swe_bench_run_id: str
    swe_bench_instance_id: str
    swe_bench_task_id: str
    betas: Optional[str] = None
    entrypoint: Optional[str] = None
    agent_sdk_version: Optional[str] = None
    process_metrics: Optional[ProcessMetrics] = None
    agent_id: Optional[str] = None
    parent_session_id: Optional[str] = None
    agent_type: Optional[str] = None  # 'teammate' | 'subagent' | 'standalone'
    team_name: Optional[str] = None
    subscription_type: Optional[str] = None
    rh: Optional[str] = None
    kairos_active: Optional[bool] = None
    skill_mode: Optional[str] = None
    observer_mode: Optional[str] = None


# ---------------------------------------------------------------------------
# EnrichMetadataOptions
# ---------------------------------------------------------------------------

@dataclass
class EnrichMetadataOptions:
    model: Optional[Any] = None
    betas: Optional[Any] = None
    additional_metadata: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# First-party event logging types
# ---------------------------------------------------------------------------

@dataclass
class FirstPartyEventLoggingCoreMetadata:
    session_id: str
    model: str
    user_type: str
    is_interactive: bool
    client_type: str
    betas: Optional[str] = None
    entrypoint: Optional[str] = None
    agent_sdk_version: Optional[str] = None
    swe_bench_run_id: Optional[str] = None
    swe_bench_instance_id: Optional[str] = None
    swe_bench_task_id: Optional[str] = None
    agent_id: Optional[str] = None
    parent_session_id: Optional[str] = None
    agent_type: Optional[str] = None
    team_name: Optional[str] = None


@dataclass
class FirstPartyEventLoggingMetadata:
    env: Dict[str, Any]
    core: FirstPartyEventLoggingCoreMetadata
    process: Optional[str] = None  # base64-encoded JSON
    auth: Optional[Dict[str, Any]] = None
    additional: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Agent identification
# ---------------------------------------------------------------------------

def _get_agent_identification() -> Dict[str, Any]:
    """Return agent identification fields, checking AsyncLocalStorage first."""
    agent_context = _get_agent_context()
    if agent_context:
        result: Dict[str, Any] = {}
        if hasattr(agent_context, "agent_id") and agent_context.agent_id:
            result["agent_id"] = agent_context.agent_id
        if hasattr(agent_context, "parent_session_id") and agent_context.parent_session_id:
            result["parent_session_id"] = agent_context.parent_session_id
        if hasattr(agent_context, "agent_type") and agent_context.agent_type:
            result["agent_type"] = agent_context.agent_type
            if agent_context.agent_type == "teammate" and hasattr(agent_context, "team_name"):
                result["team_name"] = agent_context.team_name
        return result

    # Fall back to swarm helpers
    agent_id = _get_teammate_agent_id()
    parent_session_id = _get_teammate_parent_session_id()
    team_name = _get_team_name()
    is_swarm = _is_teammate()
    agent_type: Optional[str] = (
        "teammate" if is_swarm else ("standalone" if agent_id else None)
    )

    if agent_id or agent_type or parent_session_id or team_name:
        result = {}
        if agent_id:
            result["agent_id"] = agent_id
        if agent_type:
            result["agent_type"] = agent_type
        if parent_session_id:
            result["parent_session_id"] = parent_session_id
        if team_name:
            result["team_name"] = team_name
        return result

    # Bootstrap state fallback
    state_parent = _get_parent_session_id_from_state()
    if state_parent:
        return {"parent_session_id": state_parent}

    return {}


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

_VERSION = os.environ.get("CLAUDE_VERSION", "0.0.0")
_BUILD_TIME = os.environ.get("CLAUDE_BUILD_TIME", "unknown")


@lru_cache(maxsize=1)
def _get_version_base() -> Optional[str]:
    match = re.match(r"^\d+\.\d+\.\d+(?:-[a-z]+)?", _VERSION)
    return match.group(0) if match else None


# ---------------------------------------------------------------------------
# EnvContext builder (cached)
# ---------------------------------------------------------------------------

_env_context_cache: Optional[EnvContext] = None


async def _build_env_context() -> EnvContext:
    global _env_context_cache
    if _env_context_cache is not None:
        return _env_context_cache

    package_managers = _get_package_managers()
    runtimes = _get_runtimes()
    linux_distro_info = _get_linux_distro_info()
    vcs_list = _detect_vcs()

    node_version = f"python/{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    terminal = os.environ.get("TERM_PROGRAM") or os.environ.get("TERM")

    ctx = EnvContext(
        platform=_get_host_platform_for_analytics(),
        platform_raw=os.environ.get("CLAUDE_CODE_HOST_PLATFORM") or sys.platform,
        arch=platform.machine(),
        node_version=node_version,
        terminal=terminal,
        package_managers=",".join(package_managers),
        runtimes=",".join(runtimes),
        is_running_with_bun=_is_running_with_bun(),
        is_ci=_is_env_truthy(os.environ.get("CI")),
        is_claubbit=_is_env_truthy(os.environ.get("CLAUBBIT")),
        is_claude_code_remote=_is_env_truthy(os.environ.get("CLAUDE_CODE_REMOTE")),
        is_local_agent_mode=os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "local-agent",
        is_conductor=_is_conductor(),
        is_github_action=_is_env_truthy(os.environ.get("GITHUB_ACTIONS")),
        is_claude_code_action=_is_env_truthy(os.environ.get("CLAUDE_CODE_ACTION")),
        is_claude_ai_auth=_is_claude_ai_subscriber(),
        version=_VERSION,
        build_time=_BUILD_TIME,
        deployment_environment=_detect_deployment_environment(),
        version_base=_get_version_base(),
        remote_environment_type=os.environ.get("CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE"),
        coworker_type=os.environ.get("CLAUDE_CODE_COWORKER_TYPE"),
        claude_code_container_id=os.environ.get("CLAUDE_CODE_CONTAINER_ID"),
        claude_code_remote_session_id=os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID"),
        tags=os.environ.get("CLAUDE_CODE_TAGS"),
        wsl_version=_get_wsl_version(),
        vcs=",".join(vcs_list) if vcs_list else None,
    )

    if _is_env_truthy(os.environ.get("GITHUB_ACTIONS")):
        ctx.github_event_name = os.environ.get("GITHUB_EVENT_NAME")
        ctx.github_actions_runner_environment = os.environ.get("RUNNER_ENVIRONMENT")
        ctx.github_actions_runner_os = os.environ.get("RUNNER_OS")
        action_path = os.environ.get("GITHUB_ACTION_PATH", "")
        if "claude-code-action/" in action_path:
            ctx.github_action_ref = action_path.split("claude-code-action/", 1)[1]

    if linux_distro_info:
        ctx.linux_distro_id = linux_distro_info.get("linuxDistroId")
        ctx.linux_distro_version = linux_distro_info.get("linuxDistroVersion")
        ctx.linux_kernel = linux_distro_info.get("linuxKernel")

    _env_context_cache = ctx
    return ctx


# ---------------------------------------------------------------------------
# ProcessMetrics builder
# ---------------------------------------------------------------------------

_prev_cpu_times: Optional[Any] = None
_prev_wall_time_ms: Optional[float] = None


def _build_process_metrics() -> Optional[ProcessMetrics]:
    global _prev_cpu_times, _prev_wall_time_ms
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss = usage.ru_maxrss
        # macOS reports KB, Linux reports bytes
        if sys.platform == "darwin":
            rss *= 1024

        now_ms = time.time() * 1000
        cpu_user = usage.ru_utime
        cpu_system = usage.ru_stime
        cpu_percent: Optional[float] = None

        if _prev_cpu_times is not None and _prev_wall_time_ms is not None:
            wall_delta_ms = now_ms - _prev_wall_time_ms
            if wall_delta_ms > 0:
                user_delta = cpu_user - _prev_cpu_times[0]
                sys_delta = cpu_system - _prev_cpu_times[1]
                cpu_percent = ((user_delta + sys_delta) / (wall_delta_ms / 1000)) * 100

        _prev_cpu_times = (cpu_user, cpu_system)
        _prev_wall_time_ms = now_ms

        import psutil  # type: ignore
        mem = psutil.Process().memory_info()
        uptime_val = time.time() - psutil.Process().create_time()

        return ProcessMetrics(
            uptime=uptime_val,
            rss=mem.rss,
            heap_total=0,
            heap_used=0,
            external=0,
            array_buffers=0,
            constrained_memory=None,
            cpu_user=cpu_user,
            cpu_system=cpu_system,
            cpu_percent=cpu_percent,
        )
    except Exception:
        try:
            # Minimal fallback without psutil
            return ProcessMetrics(
                uptime=time.process_time(),
                rss=0,
                heap_total=0,
                heap_used=0,
                external=0,
                array_buffers=0,
                constrained_memory=None,
                cpu_user=0.0,
                cpu_system=0.0,
                cpu_percent=None,
            )
        except Exception:
            return None


# ---------------------------------------------------------------------------
# get_event_metadata — main public API
# ---------------------------------------------------------------------------

async def get_event_metadata(
    options: Optional[EnrichMetadataOptions] = None,
) -> EventMetadata:
    """Collect and return enriched event metadata."""
    if options is None:
        options = EnrichMetadataOptions()

    model = str(options.model) if options.model is not None else _get_main_loop_model()
    if isinstance(options.betas, str):
        betas = options.betas
    else:
        betas = ",".join(_get_model_betas(model))

    env_context = await _build_env_context()

    # repo remote hash — best-effort
    repo_remote_hash: Optional[str] = None
    try:
        from claude_code.utils.git import get_repo_remote_hash  # type: ignore
        repo_remote_hash = await get_repo_remote_hash()
    except (ImportError, Exception):
        pass

    process_metrics = _build_process_metrics()
    agent_info = _get_agent_identification()
    subscription_type = _get_subscription_type()

    metadata = EventMetadata(
        model=model,
        session_id=_get_session_id(),
        user_type=os.environ.get("USER_TYPE", ""),
        betas=betas if betas else None,
        env_context=env_context,
        entrypoint=os.environ.get("CLAUDE_CODE_ENTRYPOINT"),
        agent_sdk_version=os.environ.get("CLAUDE_AGENT_SDK_VERSION"),
        is_interactive=str(_get_is_interactive()),
        client_type=_get_client_type(),
        process_metrics=process_metrics,
        swe_bench_run_id=os.environ.get("SWE_BENCH_RUN_ID", ""),
        swe_bench_instance_id=os.environ.get("SWE_BENCH_INSTANCE_ID", ""),
        swe_bench_task_id=os.environ.get("SWE_BENCH_TASK_ID", ""),
        agent_id=agent_info.get("agent_id"),
        parent_session_id=agent_info.get("parent_session_id"),
        agent_type=agent_info.get("agent_type"),
        team_name=agent_info.get("team_name"),
        subscription_type=subscription_type,
        rh=repo_remote_hash,
        kairos_active=True if _get_kairos_active() else None,
    )

    return metadata


# ---------------------------------------------------------------------------
# to_1p_event_format
# ---------------------------------------------------------------------------

def to_1p_event_format(
    metadata: EventMetadata,
    user_metadata: Any,
    additional_metadata: Optional[Dict[str, Any]] = None,
) -> FirstPartyEventLoggingMetadata:
    """Convert EventMetadata to the 1P event logging wire format (snake_case)."""
    if additional_metadata is None:
        additional_metadata = {}

    ctx = metadata.env_context

    env: Dict[str, Any] = {
        "platform": ctx.platform,
        "platform_raw": ctx.platform_raw,
        "arch": ctx.arch,
        "node_version": ctx.node_version,
        "terminal": ctx.terminal or "unknown",
        "package_managers": ctx.package_managers,
        "runtimes": ctx.runtimes,
        "is_running_with_bun": ctx.is_running_with_bun,
        "is_ci": ctx.is_ci,
        "is_claubbit": ctx.is_claubbit,
        "is_claude_code_remote": ctx.is_claude_code_remote,
        "is_local_agent_mode": ctx.is_local_agent_mode,
        "is_conductor": ctx.is_conductor,
        "is_github_action": ctx.is_github_action,
        "is_claude_code_action": ctx.is_claude_code_action,
        "is_claude_ai_auth": ctx.is_claude_ai_auth,
        "version": ctx.version,
        "build_time": ctx.build_time,
        "deployment_environment": ctx.deployment_environment,
    }

    # Optional env fields
    if ctx.remote_environment_type:
        env["remote_environment_type"] = ctx.remote_environment_type
    if ctx.coworker_type:
        env["coworker_type"] = ctx.coworker_type
    if ctx.claude_code_container_id:
        env["claude_code_container_id"] = ctx.claude_code_container_id
    if ctx.claude_code_remote_session_id:
        env["claude_code_remote_session_id"] = ctx.claude_code_remote_session_id
    if ctx.tags:
        env["tags"] = [t.strip() for t in ctx.tags.split(",") if t.strip()]
    if ctx.github_event_name:
        env["github_event_name"] = ctx.github_event_name
    if ctx.github_actions_runner_environment:
        env["github_actions_runner_environment"] = ctx.github_actions_runner_environment
    if ctx.github_actions_runner_os:
        env["github_actions_runner_os"] = ctx.github_actions_runner_os
    if ctx.github_action_ref:
        env["github_action_ref"] = ctx.github_action_ref
    if ctx.wsl_version:
        env["wsl_version"] = ctx.wsl_version
    if ctx.linux_distro_id:
        env["linux_distro_id"] = ctx.linux_distro_id
    if ctx.linux_distro_version:
        env["linux_distro_version"] = ctx.linux_distro_version
    if ctx.linux_kernel:
        env["linux_kernel"] = ctx.linux_kernel
    if ctx.vcs:
        env["vcs"] = ctx.vcs
    if ctx.version_base:
        env["version_base"] = ctx.version_base

    # GitHub Actions metadata from user_metadata
    if user_metadata is not None and hasattr(user_metadata, "github_actions_metadata"):
        gh_meta = user_metadata.github_actions_metadata
        if gh_meta:
            env["github_actions_metadata"] = {
                "actor_id": getattr(gh_meta, "actor_id", None),
                "repository_id": getattr(gh_meta, "repository_id", None),
                "repository_owner_id": getattr(gh_meta, "repository_owner_id", None),
            }

    # Core fields
    core = FirstPartyEventLoggingCoreMetadata(
        session_id=metadata.session_id,
        model=metadata.model,
        user_type=metadata.user_type,
        is_interactive=metadata.is_interactive.lower() == "true",
        client_type=metadata.client_type,
    )
    if metadata.betas:
        core.betas = metadata.betas
    if metadata.entrypoint:
        core.entrypoint = metadata.entrypoint
    if metadata.agent_sdk_version:
        core.agent_sdk_version = metadata.agent_sdk_version
    if metadata.swe_bench_run_id:
        core.swe_bench_run_id = metadata.swe_bench_run_id
    if metadata.swe_bench_instance_id:
        core.swe_bench_instance_id = metadata.swe_bench_instance_id
    if metadata.swe_bench_task_id:
        core.swe_bench_task_id = metadata.swe_bench_task_id
    if metadata.agent_id:
        core.agent_id = metadata.agent_id
    if metadata.parent_session_id:
        core.parent_session_id = metadata.parent_session_id
    if metadata.agent_type:
        core.agent_type = metadata.agent_type
    if metadata.team_name:
        core.team_name = metadata.team_name

    # Auth
    auth: Optional[Dict[str, Any]] = None
    if user_metadata is not None:
        account_uuid = getattr(user_metadata, "account_uuid", None)
        org_uuid = getattr(user_metadata, "organization_uuid", None)
        if account_uuid or org_uuid:
            auth = {"account_uuid": account_uuid, "organization_uuid": org_uuid}

    # Process metrics as base64-encoded JSON
    process_b64: Optional[str] = None
    if metadata.process_metrics is not None:
        pm = metadata.process_metrics
        pm_dict = {
            "uptime": pm.uptime,
            "rss": pm.rss,
            "heapTotal": pm.heap_total,
            "heapUsed": pm.heap_used,
            "external": pm.external,
            "arrayBuffers": pm.array_buffers,
            "constrainedMemory": pm.constrained_memory,
            "cpuUser": pm.cpu_user,
            "cpuSystem": pm.cpu_system,
            "cpuPercent": pm.cpu_percent,
        }
        process_b64 = base64.b64encode(_json_stringify(pm_dict).encode()).decode()

    # Additional fields
    additional: Dict[str, Any] = {}
    if metadata.rh:
        additional["rh"] = metadata.rh
    if metadata.kairos_active:
        additional["is_assistant_mode"] = True
    if metadata.skill_mode:
        additional["skill_mode"] = metadata.skill_mode
    if metadata.observer_mode:
        additional["observer_mode"] = metadata.observer_mode
    additional.update(additional_metadata)

    return FirstPartyEventLoggingMetadata(
        env=env,
        process=process_b64,
        auth=auth,
        core=core,
        additional=additional,
    )


# ---------------------------------------------------------------------------
# Backward-compat stub used by other modules
# ---------------------------------------------------------------------------

def build_event_metadata(event: str, context: Any = None) -> Dict[str, Any]:
    """Legacy stub — returns a minimal metadata dict synchronously."""
    return {
        "event": event,
        "session_id": _get_session_id(),
        "model": _get_main_loop_model(),
        "user_type": os.environ.get("USER_TYPE", ""),
        "is_interactive": str(_get_is_interactive()),
        "client_type": _get_client_type(),
    }
