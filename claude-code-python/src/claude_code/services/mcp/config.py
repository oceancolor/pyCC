"""
MCP config management. Ported from services/mcp/config.ts

Manages reading, writing, and validating MCP server configurations
across multiple scopes: project (.mcp.json), user (~/.claude/claude.json),
local (project-local claude.json), and enterprise (managed-mcp.json).
"""
from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from typing import TypedDict, Literal
except ImportError:
    from typing_extensions import TypedDict, Literal  # type: ignore


# ---------------------------------------------------------------------------
# Type Definitions (Python equivalents of TS types from types.ts)
# ---------------------------------------------------------------------------

ConfigScope = Literal[
    "local", "user", "project", "dynamic", "enterprise", "claudeai", "managed"
]

# MCP server config dicts — typed as plain dicts for flexibility
McpServerConfig = Dict[str, Any]
ScopedMcpServerConfig = Dict[str, Any]  # McpServerConfig + {"scope": ConfigScope}
McpJsonConfig = Dict[str, Any]          # {"mcpServers": Dict[str, McpServerConfig]}


class ValidationError(TypedDict, total=False):
    file: str
    path: str
    message: str
    suggestion: str
    mcpErrorMetadata: Dict[str, Any]


# ---------------------------------------------------------------------------
# Schema validation helpers (replaces Zod schemas)
# ---------------------------------------------------------------------------

def _validate_mcp_server_config(config: Any) -> Tuple[bool, str]:
    """
    Validate a single MCP server config dict.
    Returns (is_valid, error_message).
    """
    if not isinstance(config, dict):
        return False, "Server config must be an object"

    server_type = config.get("type")

    if server_type is None or server_type == "stdio":
        # StdioServerConfig
        command = config.get("command")
        if not command or not isinstance(command, str) or not command.strip():
            return False, "command: Command cannot be empty"
        args = config.get("args", [])
        if not isinstance(args, list):
            return False, "args: Must be an array"
        for arg in args:
            if not isinstance(arg, str):
                return False, "args: All arguments must be strings"
        env = config.get("env")
        if env is not None and not isinstance(env, dict):
            return False, "env: Must be an object"
        return True, ""

    elif server_type in ("sse", "http", "ws"):
        # Remote server configs
        url = config.get("url")
        if not isinstance(url, str):
            return False, "url: URL is required"
        headers = config.get("headers")
        if headers is not None and not isinstance(headers, dict):
            return False, "headers: Must be an object"
        return True, ""

    elif server_type in ("sse-ide", "ws-ide"):
        url = config.get("url")
        if not isinstance(url, str):
            return False, "url: URL is required"
        return True, ""

    elif server_type == "sdk":
        name = config.get("name")
        if not isinstance(name, str):
            return False, "name: Name is required for sdk type"
        return True, ""

    elif server_type == "claudeai-proxy":
        url = config.get("url")
        if not isinstance(url, str):
            return False, "url: URL is required"
        server_id = config.get("id")
        if not isinstance(server_id, str):
            return False, "id: ID is required"
        return True, ""

    else:
        return False, f"type: Unknown server type '{server_type}'"


def _validate_mcp_json_config(obj: Any) -> Tuple[bool, List[str]]:
    """
    Validate a McpJsonConfig object.
    Returns (is_valid, list_of_error_messages).
    """
    if not isinstance(obj, dict):
        return False, ["Config must be an object"]

    mcp_servers = obj.get("mcpServers")
    if mcp_servers is None:
        # Allow missing mcpServers (treated as empty)
        return True, []

    if not isinstance(mcp_servers, dict):
        return False, ["mcpServers: Must be an object"]

    errors = []
    for name, server_config in mcp_servers.items():
        valid, err = _validate_mcp_server_config(server_config)
        if not valid:
            errors.append(f"mcpServers.{name}.{err}")

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Lazy imports — break circular dependencies
# ---------------------------------------------------------------------------

def _get_cwd() -> str:
    try:
        from claude_code.utils.cwd import get_cwd
        return get_cwd()
    except ImportError:
        return os.getcwd()


def _get_global_config() -> Dict[str, Any]:
    try:
        from claude_code.utils.config import get_global_config
        result = get_global_config()
        return dict(result) if result else {}
    except ImportError:
        return {}


def _save_global_config(updater: Any) -> None:
    try:
        from claude_code.utils.config import save_global_config
        save_global_config(updater)
    except ImportError:
        pass


def _get_current_project_config() -> Dict[str, Any]:
    try:
        from claude_code.utils.config import get_current_project_config
        result = get_current_project_config()
        return dict(result) if result else {}
    except ImportError:
        return {}


def _save_current_project_config(updater: Any) -> None:
    try:
        from claude_code.utils.config import save_current_project_config
        save_current_project_config(updater)
    except ImportError:
        pass


def _get_platform() -> str:
    try:
        from claude_code.utils.platform import get_platform
        return get_platform()
    except ImportError:
        import sys
        if sys.platform == "win32":
            return "windows"
        elif sys.platform == "darwin":
            return "mac"
        return "linux"


def _is_setting_source_enabled(source: str) -> bool:
    try:
        from claude_code.utils.settings.constants import is_setting_source_enabled
        return is_setting_source_enabled(source)
    except (ImportError, Exception):
        return True  # Default to enabled


def _get_settings_for_source(source: str) -> Optional[Dict[str, Any]]:
    try:
        from claude_code.utils.settings.settings import get_settings_for_source
        return get_settings_for_source(source)
    except (ImportError, Exception):
        return None


def _get_initial_settings() -> Dict[str, Any]:
    try:
        from claude_code.utils.settings.settings import get_initial_settings
        result = get_initial_settings()
        return dict(result) if result else {}
    except (ImportError, Exception):
        return {}


def _get_managed_file_path() -> str:
    try:
        from claude_code.utils.settings.managed_path import get_managed_file_path
        return get_managed_file_path()
    except (ImportError, Exception):
        return str(Path.home() / ".claude" / "managed")


def _is_restricted_to_plugin_only(surface: str) -> bool:
    try:
        from claude_code.utils.settings.plugin_only_policy import is_restricted_to_plugin_only
        return is_restricted_to_plugin_only(surface)
    except (ImportError, Exception):
        return False


def _is_mcp_server_name_entry(entry: Dict[str, Any]) -> bool:
    try:
        from claude_code.utils.settings.types import is_mcp_server_name_entry
        return is_mcp_server_name_entry(entry)
    except (ImportError, Exception):
        return "serverName" in entry


def _is_mcp_server_command_entry(entry: Dict[str, Any]) -> bool:
    try:
        from claude_code.utils.settings.types import is_mcp_server_command_entry
        return is_mcp_server_command_entry(entry)
    except (ImportError, Exception):
        return "serverCommand" in entry


def _is_mcp_server_url_entry(entry: Dict[str, Any]) -> bool:
    try:
        from claude_code.utils.settings.types import is_mcp_server_url_entry
        return is_mcp_server_url_entry(entry)
    except (ImportError, Exception):
        return "serverUrl" in entry


def _is_claude_in_chrome_mcp_server(name: str) -> bool:
    try:
        from claude_code.utils.claude_in_chrome.common import is_claude_in_chrome_mcp_server
        return is_claude_in_chrome_mcp_server(name)
    except (ImportError, Exception):
        return name == "claude-in-chrome"


def _get_project_mcp_server_status(name: str) -> str:
    try:
        from claude_code.services.mcp.utils import get_project_mcp_server_status
        return get_project_mcp_server_status(name)
    except (ImportError, Exception):
        return "pending"


def _expand_env_vars_in_string(value: str) -> Dict[str, Any]:
    """Expand ${VAR} and ${VAR:-default} syntax. Returns {expanded, missing_vars}."""
    try:
        from claude_code.services.mcp.env_expansion import expand_env_vars_in_string
        return expand_env_vars_in_string(value)
    except (ImportError, Exception):
        # Fallback implementation
        missing_vars: List[str] = []

        def replacer(match: re.Match) -> str:
            var_content = match.group(1)
            parts = var_content.split(":-", 1)
            var_name = parts[0]
            default_val = parts[1] if len(parts) > 1 else None
            env_val = os.environ.get(var_name)
            if env_val is not None:
                return env_val
            if default_val is not None:
                return default_val
            missing_vars.append(var_name)
            return match.group(0)

        expanded = re.sub(r"\$\{([^}]+)\}", replacer, value)
        return {"expanded": expanded, "missingVars": list(set(missing_vars))}


def _log_for_debugging(msg: str, level: str = "debug") -> None:
    try:
        from claude_code.utils.debug import log_for_debugging
        log_for_debugging(msg, level=level)
    except (ImportError, Exception):
        pass  # Silently ignore debug logging failures


# ---------------------------------------------------------------------------
# Enterprise MCP file path
# ---------------------------------------------------------------------------

def get_enterprise_mcp_file_path() -> str:
    """Get the path to the managed MCP configuration file."""
    return str(Path(_get_managed_file_path()) / "managed-mcp.json")


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------

def _add_scope_to_servers(
    servers: Optional[Dict[str, McpServerConfig]],
    scope: ConfigScope,
) -> Dict[str, ScopedMcpServerConfig]:
    """Add scope field to server configs."""
    if not servers:
        return {}
    result: Dict[str, ScopedMcpServerConfig] = {}
    for name, config in servers.items():
        result[name] = {**config, "scope": scope}
    return result


def _write_mcp_json_file(config: McpJsonConfig) -> None:
    """
    Write MCP config to .mcp.json file.
    Preserves file permissions and uses atomic rename.
    """
    cwd = _get_cwd()
    mcp_json_path = str(Path(cwd) / ".mcp.json")

    # Read existing file permissions to preserve them
    existing_mode: Optional[int] = None
    try:
        file_stat = os.stat(mcp_json_path)
        existing_mode = stat.S_IMODE(file_stat.st_mode)
    except OSError as e:
        if e.errno != 2:  # ENOENT
            raise

    content = json.dumps(config, indent=2, ensure_ascii=False)

    # Write to temp file then atomic rename
    temp_fd, temp_path = tempfile.mkstemp(
        dir=str(Path(cwd)),
        prefix=f".mcp.json.tmp.{os.getpid()}.",
    )
    try:
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            os.close(temp_fd)
            raise

        # Restore permissions
        if existing_mode is not None:
            os.chmod(temp_path, existing_mode)

        # Atomic rename
        os.rename(temp_path, mcp_json_path)
        temp_path = None  # Successfully renamed, don't clean up
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def _get_server_command_array(config: McpServerConfig) -> Optional[List[str]]:
    """Extract command array from server config. Returns None for non-stdio servers."""
    server_type = config.get("type")
    if server_type is not None and server_type != "stdio":
        return None
    command = config.get("command")
    if not command:
        return None
    args = config.get("args") or []
    return [command] + list(args)


def _command_arrays_match(a: List[str], b: List[str]) -> bool:
    """Check if two command arrays match exactly."""
    return a == b


def _get_server_url(config: McpServerConfig) -> Optional[str]:
    """Extract URL from server config. Returns None for stdio servers."""
    return config.get("url")


# ---------------------------------------------------------------------------
# CCR proxy URL handling
# ---------------------------------------------------------------------------

_CCR_PROXY_PATH_MARKERS = [
    "/v2/session_ingress/shttp/mcp/",
    "/v2/ccr-sessions/",
]


def unwrap_ccr_proxy_url(url: str) -> str:
    """
    If the URL is a CCR proxy URL, extract the original vendor URL from the
    mcp_url query parameter. Otherwise return the URL unchanged.
    """
    if not any(m in url for m in _CCR_PROXY_PATH_MARKERS):
        return url
    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        mcp_url_list = params.get("mcp_url")
        if mcp_url_list:
            return mcp_url_list[0]
        return url
    except Exception:
        return url


def get_mcp_server_signature(config: McpServerConfig) -> Optional[str]:
    """
    Compute a dedup signature for an MCP server config.
    Returns None only for configs with neither command nor url (sdk type).
    """
    cmd = _get_server_command_array(config)
    if cmd is not None:
        return f"stdio:{json.dumps(cmd, separators=(',', ':'))}"
    url = _get_server_url(config)
    if url:
        return f"url:{unwrap_ccr_proxy_url(url)}"
    return None


# ---------------------------------------------------------------------------
# Dedup helpers
# ---------------------------------------------------------------------------

def dedup_plugin_mcp_servers(
    plugin_servers: Dict[str, ScopedMcpServerConfig],
    manual_servers: Dict[str, ScopedMcpServerConfig],
) -> Dict[str, Any]:
    """
    Filter plugin MCP servers, dropping any whose signature matches a
    manually-configured server or an earlier-loaded plugin server.
    Returns {"servers": ..., "suppressed": [{"name": ..., "duplicateOf": ...}]}
    """
    # Build manual sigs map
    manual_sigs: Dict[str, str] = {}
    for name, config in manual_servers.items():
        sig = get_mcp_server_signature(config)
        if sig and sig not in manual_sigs:
            manual_sigs[sig] = name

    servers: Dict[str, ScopedMcpServerConfig] = {}
    suppressed: List[Dict[str, str]] = []
    seen_plugin_sigs: Dict[str, str] = {}

    for name, config in plugin_servers.items():
        sig = get_mcp_server_signature(config)
        if sig is None:
            servers[name] = config
            continue

        manual_dup = manual_sigs.get(sig)
        if manual_dup is not None:
            _log_for_debugging(
                f'Suppressing plugin MCP server "{name}": duplicates manually-configured "{manual_dup}"'
            )
            suppressed.append({"name": name, "duplicateOf": manual_dup})
            continue

        plugin_dup = seen_plugin_sigs.get(sig)
        if plugin_dup is not None:
            _log_for_debugging(
                f'Suppressing plugin MCP server "{name}": duplicates earlier plugin server "{plugin_dup}"'
            )
            suppressed.append({"name": name, "duplicateOf": plugin_dup})
            continue

        seen_plugin_sigs[sig] = name
        servers[name] = config

    return {"servers": servers, "suppressed": suppressed}


def dedup_claude_ai_mcp_servers(
    claude_ai_servers: Dict[str, ScopedMcpServerConfig],
    manual_servers: Dict[str, ScopedMcpServerConfig],
) -> Dict[str, Any]:
    """
    Filter claude.ai connectors, dropping any whose signature matches an enabled
    manually-configured server.
    Returns {"servers": ..., "suppressed": [{"name": ..., "duplicateOf": ...}]}
    """
    manual_sigs: Dict[str, str] = {}
    for name, config in manual_servers.items():
        if is_mcp_server_disabled(name):
            continue
        sig = get_mcp_server_signature(config)
        if sig and sig not in manual_sigs:
            manual_sigs[sig] = name

    servers: Dict[str, ScopedMcpServerConfig] = {}
    suppressed: List[Dict[str, str]] = []

    for name, config in claude_ai_servers.items():
        sig = get_mcp_server_signature(config)
        manual_dup = manual_sigs.get(sig) if sig is not None else None
        if manual_dup is not None:
            _log_for_debugging(
                f'Suppressing claude.ai connector "{name}": duplicates manually-configured "{manual_dup}"'
            )
            suppressed.append({"name": name, "duplicateOf": manual_dup})
            continue
        servers[name] = config

    return {"servers": servers, "suppressed": suppressed}


# ---------------------------------------------------------------------------
# URL pattern matching
# ---------------------------------------------------------------------------

def _url_pattern_to_regex(pattern: str) -> re.Pattern:
    """Convert a URL pattern with wildcards to a RegExp. * matches any characters."""
    # Escape regex special chars except *
    escaped = re.sub(r"[.+?^${}()|[\]\\]", lambda m: "\\" + m.group(0), pattern)
    regex_str = escaped.replace("*", ".*")
    return re.compile(f"^{regex_str}$")


def _url_matches_pattern(url: str, pattern: str) -> bool:
    """Check if a URL matches a pattern with wildcard support."""
    return bool(_url_pattern_to_regex(pattern).match(url))


# ---------------------------------------------------------------------------
# MCP allowlist/denylist policy
# ---------------------------------------------------------------------------

def _should_allow_managed_mcp_servers_only() -> bool:
    """
    Check if MCP allowlist policy should only come from managed settings.
    """
    settings = _get_settings_for_source("policySettings")
    if settings and settings.get("allowManagedMcpServersOnly") is True:
        return True
    return False


def should_allow_managed_mcp_servers_only() -> bool:
    """Public: Check if allowManagedMcpServersOnly is set in policy settings."""
    return _should_allow_managed_mcp_servers_only()


def _get_mcp_allowlist_settings() -> Dict[str, Any]:
    if _should_allow_managed_mcp_servers_only():
        return _get_settings_for_source("policySettings") or {}
    return _get_initial_settings()


def _get_mcp_denylist_settings() -> Dict[str, Any]:
    return _get_initial_settings()


def _is_mcp_server_denied(
    server_name: str,
    config: Optional[McpServerConfig] = None,
) -> bool:
    """Check if an MCP server is denied by enterprise policy."""
    settings = _get_mcp_denylist_settings()
    denied_servers = settings.get("deniedMcpServers")
    if not denied_servers:
        return False

    # Name-based denial
    for entry in denied_servers:
        if _is_mcp_server_name_entry(entry) and entry.get("serverName") == server_name:
            return True

    if config:
        server_command = _get_server_command_array(config)
        if server_command:
            for entry in denied_servers:
                if (
                    _is_mcp_server_command_entry(entry)
                    and _command_arrays_match(
                        entry.get("serverCommand", []), server_command
                    )
                ):
                    return True

        server_url = _get_server_url(config)
        if server_url:
            for entry in denied_servers:
                if (
                    _is_mcp_server_url_entry(entry)
                    and _url_matches_pattern(server_url, entry.get("serverUrl", ""))
                ):
                    return True

    return False


def _is_mcp_server_allowed_by_policy(
    server_name: str,
    config: Optional[McpServerConfig] = None,
) -> bool:
    """Check if an MCP server is allowed by enterprise policy."""
    # Denylist takes absolute precedence
    if _is_mcp_server_denied(server_name, config):
        return False

    settings = _get_mcp_allowlist_settings()
    allowed_servers = settings.get("allowedMcpServers")

    if allowed_servers is None:
        return True  # No allowlist restrictions

    if len(allowed_servers) == 0:
        return False  # Empty allowlist = block all

    has_command_entries = any(_is_mcp_server_command_entry(e) for e in allowed_servers)
    has_url_entries = any(_is_mcp_server_url_entry(e) for e in allowed_servers)

    if config:
        server_command = _get_server_command_array(config)
        server_url = _get_server_url(config)

        if server_command:
            # stdio server
            if has_command_entries:
                for entry in allowed_servers:
                    if (
                        _is_mcp_server_command_entry(entry)
                        and _command_arrays_match(
                            entry.get("serverCommand", []), server_command
                        )
                    ):
                        return True
                return False
            else:
                for entry in allowed_servers:
                    if (
                        _is_mcp_server_name_entry(entry)
                        and entry.get("serverName") == server_name
                    ):
                        return True
                return False

        elif server_url:
            # remote server
            if has_url_entries:
                for entry in allowed_servers:
                    if (
                        _is_mcp_server_url_entry(entry)
                        and _url_matches_pattern(
                            server_url, entry.get("serverUrl", "")
                        )
                    ):
                        return True
                return False
            else:
                for entry in allowed_servers:
                    if (
                        _is_mcp_server_name_entry(entry)
                        and entry.get("serverName") == server_name
                    ):
                        return True
                return False

        else:
            # Unknown type — name-only check
            for entry in allowed_servers:
                if (
                    _is_mcp_server_name_entry(entry)
                    and entry.get("serverName") == server_name
                ):
                    return True
            return False

    # No config — name-only check
    for entry in allowed_servers:
        if (
            _is_mcp_server_name_entry(entry)
            and entry.get("serverName") == server_name
        ):
            return True
    return False


def filter_mcp_servers_by_policy(configs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Filter a record of MCP server configs by managed policy.
    SDK-type servers are always allowed.
    Returns {"allowed": ..., "blocked": [...]}
    """
    allowed: Dict[str, Any] = {}
    blocked: List[str] = []
    for name, config in configs.items():
        c = config if isinstance(config, dict) else {}
        if c.get("type") == "sdk" or _is_mcp_server_allowed_by_policy(name, c):
            allowed[name] = config
        else:
            blocked.append(name)
    return {"allowed": allowed, "blocked": blocked}


# ---------------------------------------------------------------------------
# Environment variable expansion for MCP configs
# ---------------------------------------------------------------------------

def _expand_env_vars_in_config(config: McpServerConfig) -> Dict[str, Any]:
    """
    Expand environment variables in an MCP server config.
    Returns {"expanded": config, "missingVars": [...]}
    """
    missing_vars: List[str] = []

    def expand_str(s: str) -> str:
        result = _expand_env_vars_in_string(s)
        missing_vars.extend(result.get("missingVars", []))
        return result.get("expanded", s)

    server_type = config.get("type")

    if server_type is None or server_type == "stdio":
        command = config.get("command", "")
        args = config.get("args", [])
        env = config.get("env")
        expanded: McpServerConfig = {
            **config,
            "command": expand_str(command),
            "args": [expand_str(a) for a in args],
        }
        if env is not None:
            expanded["env"] = {k: expand_str(v) for k, v in env.items()}

    elif server_type in ("sse", "http", "ws"):
        url = config.get("url", "")
        headers = config.get("headers")
        expanded = {
            **config,
            "url": expand_str(url),
        }
        if headers is not None:
            expanded["headers"] = {k: expand_str(v) for k, v in headers.items()}

    elif server_type in ("sse-ide", "ws-ide", "sdk", "claudeai-proxy"):
        expanded = dict(config)

    else:
        expanded = dict(config)

    # Deduplicate missing vars
    unique_missing = list(dict.fromkeys(missing_vars))
    return {"expanded": expanded, "missingVars": unique_missing}


# ---------------------------------------------------------------------------
# MCP config parsing
# ---------------------------------------------------------------------------

def parse_mcp_config(
    *,
    config_object: Any,
    expand_vars: bool,
    scope: ConfigScope,
    file_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Parse and validate an MCP configuration object.
    Returns {"config": McpJsonConfig | None, "errors": [ValidationError]}
    """
    valid, errs = _validate_mcp_json_config(config_object)
    if not valid:
        errors: List[ValidationError] = []
        for err_msg in errs:
            ve: ValidationError = {
                "path": "",
                "message": "Does not adhere to MCP server configuration schema",
                "mcpErrorMetadata": {
                    "scope": scope,
                    "severity": "fatal",
                },
            }
            if file_path:
                ve["file"] = file_path
            errors.append(ve)
        return {"config": None, "errors": errors}

    # config_object is valid; extract mcpServers
    raw_servers: Dict[str, Any] = {}
    if isinstance(config_object, dict) and "mcpServers" in config_object:
        mcs = config_object["mcpServers"]
        if isinstance(mcs, dict):
            raw_servers = mcs

    errors_out: List[ValidationError] = []
    validated_servers: Dict[str, McpServerConfig] = {}

    for name, config in raw_servers.items():
        config_to_check = config

        if expand_vars:
            expansion = _expand_env_vars_in_config(config)
            missing = expansion.get("missingVars", [])
            if missing:
                ve_warn: ValidationError = {
                    "path": f"mcpServers.{name}",
                    "message": f"Missing environment variables: {', '.join(missing)}",
                    "suggestion": f"Set the following environment variables: {', '.join(missing)}",
                    "mcpErrorMetadata": {
                        "scope": scope,
                        "serverName": name,
                        "severity": "warning",
                    },
                }
                if file_path:
                    ve_warn["file"] = file_path
                errors_out.append(ve_warn)
            config_to_check = expansion.get("expanded", config)

        # Check Windows npx usage
        if (
            _get_platform() == "windows"
            and (config_to_check.get("type") is None or config_to_check.get("type") == "stdio")
        ):
            cmd = config_to_check.get("command", "")
            if cmd == "npx" or cmd.endswith("\\npx") or cmd.endswith("/npx"):
                ve_win: ValidationError = {
                    "path": f"mcpServers.{name}",
                    "message": "Windows requires 'cmd /c' wrapper to execute npx",
                    "suggestion": (
                        'Change command to "cmd" with args ["/c", "npx", ...]. '
                        "See: https://code.claude.com/docs/en/mcp#configure-mcp-servers"
                    ),
                    "mcpErrorMetadata": {
                        "scope": scope,
                        "serverName": name,
                        "severity": "warning",
                    },
                }
                if file_path:
                    ve_win["file"] = file_path
                errors_out.append(ve_win)

        validated_servers[name] = config_to_check

    return {"config": {"mcpServers": validated_servers}, "errors": errors_out}


def parse_mcp_config_from_file_path(
    *,
    file_path: str,
    expand_vars: bool,
    scope: ConfigScope,
) -> Dict[str, Any]:
    """
    Parse and validate an MCP configuration from a file path.
    Returns {"config": McpJsonConfig | None, "errors": [ValidationError]}
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        if e.errno == 2:  # ENOENT
            return {
                "config": None,
                "errors": [
                    {
                        "file": file_path,
                        "path": "",
                        "message": f"MCP config file not found: {file_path}",
                        "suggestion": "Check that the file path is correct",
                        "mcpErrorMetadata": {
                            "scope": scope,
                            "severity": "fatal",
                        },
                    }
                ],
            }
        _log_for_debugging(
            f"MCP config read error for {file_path} (scope={scope}): {e}",
            level="error",
        )
        return {
            "config": None,
            "errors": [
                {
                    "file": file_path,
                    "path": "",
                    "message": f"Failed to read file: {e}",
                    "suggestion": "Check file permissions and ensure the file exists",
                    "mcpErrorMetadata": {
                        "scope": scope,
                        "severity": "fatal",
                    },
                }
            ],
        }

    # Parse JSON
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        _log_for_debugging(
            f"MCP config is not valid JSON: {file_path} (scope={scope}, "
            f"length={len(content)}, first100={json.dumps(content[:100])})",
            level="error",
        )
        return {
            "config": None,
            "errors": [
                {
                    "file": file_path,
                    "path": "",
                    "message": "MCP config is not a valid JSON",
                    "suggestion": "Fix the JSON syntax errors in the file",
                    "mcpErrorMetadata": {
                        "scope": scope,
                        "severity": "fatal",
                    },
                }
            ],
        }

    return parse_mcp_config(
        config_object=parsed,
        expand_vars=expand_vars,
        scope=scope,
        file_path=file_path,
    )


# ---------------------------------------------------------------------------
# Enterprise config existence check (memoized)
# ---------------------------------------------------------------------------

_enterprise_exists_cache: Optional[bool] = None


def does_enterprise_mcp_config_exist() -> bool:
    """
    Check if the enterprise MCP config file exists and is valid.
    Memoized (result cached after first call).
    """
    global _enterprise_exists_cache
    if _enterprise_exists_cache is not None:
        return _enterprise_exists_cache
    result = parse_mcp_config_from_file_path(
        file_path=get_enterprise_mcp_file_path(),
        expand_vars=True,
        scope="enterprise",
    )
    _enterprise_exists_cache = result.get("config") is not None
    return _enterprise_exists_cache


def _reset_enterprise_cache() -> None:
    """Reset the enterprise config cache (for testing)."""
    global _enterprise_exists_cache
    _enterprise_exists_cache = None


# ---------------------------------------------------------------------------
# Scope-based config retrieval
# ---------------------------------------------------------------------------

def get_project_mcp_configs_from_cwd() -> Dict[str, Any]:
    """
    Get MCP configs from current directory only (no parent traversal).
    Used by add_mcp_config and remove_mcp_config to modify the local .mcp.json.
    Returns {"servers": ..., "errors": [...]}
    """
    if not _is_setting_source_enabled("projectSettings"):
        return {"servers": {}, "errors": []}

    cwd = _get_cwd()
    mcp_json_path = str(Path(cwd) / ".mcp.json")

    result = parse_mcp_config_from_file_path(
        file_path=mcp_json_path,
        expand_vars=True,
        scope="project",
    )
    config = result.get("config")
    errors = result.get("errors", [])

    if config is None:
        non_missing = [
            e for e in errors
            if not e.get("message", "").startswith("MCP config file not found")
        ]
        if non_missing:
            _log_for_debugging(
                f"MCP config errors for {mcp_json_path}: {json.dumps([e.get('message') for e in non_missing])}",
                level="error",
            )
            return {"servers": {}, "errors": non_missing}
        return {"servers": {}, "errors": []}

    servers = config.get("mcpServers") or {}
    return {
        "servers": _add_scope_to_servers(servers, "project"),
        "errors": errors,
    }


def get_mcp_configs_by_scope(
    scope: Literal["project", "user", "local", "enterprise"],
) -> Dict[str, Any]:
    """
    Get all MCP configurations from a specific scope.
    Returns {"servers": ..., "errors": [...]}
    """
    source_map = {
        "project": "projectSettings",
        "user": "userSettings",
        "local": "localSettings",
    }

    if scope in source_map and not _is_setting_source_enabled(source_map[scope]):
        return {"servers": {}, "errors": []}

    if scope == "project":
        all_servers: Dict[str, ScopedMcpServerConfig] = {}
        all_errors: List[ValidationError] = []

        cwd = _get_cwd()
        current_dir = Path(cwd).resolve()

        # Collect directories from cwd up to root
        dirs: List[Path] = []
        d = current_dir
        while True:
            dirs.append(d)
            parent = d.parent
            if parent == d:
                break
            d = parent

        # Process from root down to cwd (closer = higher priority)
        for directory in reversed(dirs):
            mcp_json_path = str(directory / ".mcp.json")
            res = parse_mcp_config_from_file_path(
                file_path=mcp_json_path,
                expand_vars=True,
                scope="project",
            )
            cfg = res.get("config")
            errs = res.get("errors", [])

            if cfg is None:
                non_missing = [
                    e for e in errs
                    if not e.get("message", "").startswith("MCP config file not found")
                ]
                if non_missing:
                    _log_for_debugging(
                        f"MCP config errors for {mcp_json_path}: {json.dumps([e.get('message') for e in non_missing])}",
                        level="error",
                    )
                    all_errors.extend(non_missing)
                continue

            if cfg.get("mcpServers"):
                all_servers.update(_add_scope_to_servers(cfg["mcpServers"], scope))

            if errs:
                all_errors.extend(errs)

        return {"servers": all_servers, "errors": all_errors}

    elif scope == "user":
        global_config = _get_global_config()
        mcp_servers = global_config.get("mcpServers")
        if not mcp_servers:
            return {"servers": {}, "errors": []}

        res = parse_mcp_config(
            config_object={"mcpServers": mcp_servers},
            expand_vars=True,
            scope="user",
        )
        cfg = res.get("config")
        errs = res.get("errors", [])
        return {
            "servers": _add_scope_to_servers(cfg.get("mcpServers") if cfg else None, scope),
            "errors": errs,
        }

    elif scope == "local":
        project_config = _get_current_project_config()
        mcp_servers = project_config.get("mcpServers")
        if not mcp_servers:
            return {"servers": {}, "errors": []}

        res = parse_mcp_config(
            config_object={"mcpServers": mcp_servers},
            expand_vars=True,
            scope="local",
        )
        cfg = res.get("config")
        errs = res.get("errors", [])
        return {
            "servers": _add_scope_to_servers(cfg.get("mcpServers") if cfg else None, scope),
            "errors": errs,
        }

    elif scope == "enterprise":
        enterprise_path = get_enterprise_mcp_file_path()
        res = parse_mcp_config_from_file_path(
            file_path=enterprise_path,
            expand_vars=True,
            scope="enterprise",
        )
        cfg = res.get("config")
        errs = res.get("errors", [])

        if cfg is None:
            non_missing = [
                e for e in errs
                if not e.get("message", "").startswith("MCP config file not found")
            ]
            if non_missing:
                _log_for_debugging(
                    f"Enterprise MCP config errors for {enterprise_path}: {json.dumps([e.get('message') for e in non_missing])}",
                    level="error",
                )
                return {"servers": {}, "errors": non_missing}
            return {"servers": {}, "errors": []}

        return {
            "servers": _add_scope_to_servers(cfg.get("mcpServers"), scope),
            "errors": errs,
        }

    return {"servers": {}, "errors": []}


def get_mcp_config_by_name(name: str) -> Optional[ScopedMcpServerConfig]:
    """
    Get an MCP server configuration by name.
    Returns the server configuration with scope, or None if not found.
    """
    enterprise = get_mcp_configs_by_scope("enterprise")["servers"]

    if _is_restricted_to_plugin_only("mcp"):
        return enterprise.get(name)

    user = get_mcp_configs_by_scope("user")["servers"]
    project = get_mcp_configs_by_scope("project")["servers"]
    local = get_mcp_configs_by_scope("local")["servers"]

    # Priority: enterprise > local > project > user
    for store in (enterprise, local, project, user):
        if name in store:
            return store[name]

    return None


# ---------------------------------------------------------------------------
# Main config aggregators
# ---------------------------------------------------------------------------

async def get_claude_code_mcp_configs(
    dynamic_servers: Optional[Dict[str, ScopedMcpServerConfig]] = None,
    extra_dedup_targets=None,  # Optional[Awaitable[Dict]]
) -> Dict[str, Any]:
    """
    Get Claude Code MCP configurations (excludes claude.ai servers).
    Returns {"servers": ..., "errors": [...]}
    """
    import asyncio

    if dynamic_servers is None:
        dynamic_servers = {}

    enterprise_servers = get_mcp_configs_by_scope("enterprise")["servers"]

    if does_enterprise_mcp_config_exist():
        filtered: Dict[str, ScopedMcpServerConfig] = {}
        for name, server_config in enterprise_servers.items():
            if not _is_mcp_server_allowed_by_policy(name, server_config):
                continue
            filtered[name] = server_config
        return {"servers": filtered, "errors": []}

    mcp_locked = _is_restricted_to_plugin_only("mcp")
    empty: Dict[str, ScopedMcpServerConfig] = {}

    user_servers = empty if mcp_locked else get_mcp_configs_by_scope("user")["servers"]
    project_servers = empty if mcp_locked else get_mcp_configs_by_scope("project")["servers"]
    local_servers = empty if mcp_locked else get_mcp_configs_by_scope("local")["servers"]

    # Load plugin MCP servers (async)
    plugin_mcp_servers: Dict[str, ScopedMcpServerConfig] = {}
    mcp_errors: List[Any] = []

    try:
        from claude_code.utils.plugins.plugin_loader import load_all_plugins_cache_only
        plugin_result = await load_all_plugins_cache_only()

        if hasattr(plugin_result, "errors"):
            for error in plugin_result.errors:
                error_type = getattr(error, "type", "unknown")
                if error_type in (
                    "mcp-config-invalid",
                    "mcpb-download-failed",
                    "mcpb-extract-failed",
                    "mcpb-invalid-manifest",
                ):
                    pass  # log error (skipped for brevity)

        if hasattr(plugin_result, "enabled"):
            from claude_code.utils.plugins.mcp_plugin_integration import get_plugin_mcp_servers
            results = await asyncio.gather(
                *[get_plugin_mcp_servers(plugin, mcp_errors) for plugin in plugin_result.enabled],
                return_exceptions=True,
            )
            for servers in results:
                if servers and isinstance(servers, dict):
                    plugin_mcp_servers.update(servers)
    except (ImportError, Exception):
        pass  # Plugin loading is optional

    # Filter approved project servers
    approved_project_servers: Dict[str, ScopedMcpServerConfig] = {}
    for pname, pconfig in project_servers.items():
        if _get_project_mcp_server_status(pname) == "approved":
            approved_project_servers[pname] = pconfig

    # Await extra dedup targets
    extra_targets: Dict[str, ScopedMcpServerConfig] = {}
    if extra_dedup_targets is not None:
        try:
            if asyncio.isfuture(extra_dedup_targets) or asyncio.iscoroutine(extra_dedup_targets):
                extra_targets = await extra_dedup_targets
            else:
                extra_targets = extra_dedup_targets
        except Exception:
            pass

    # Build enabled manual servers
    enabled_manual: Dict[str, ScopedMcpServerConfig] = {}
    merged_manual = {
        **user_servers,
        **approved_project_servers,
        **local_servers,
        **dynamic_servers,
        **extra_targets,
    }
    for mname, mconfig in merged_manual.items():
        if not is_mcp_server_disabled(mname) and _is_mcp_server_allowed_by_policy(mname, mconfig):
            enabled_manual[mname] = mconfig

    # Split plugin servers into enabled/disabled
    enabled_plugin: Dict[str, ScopedMcpServerConfig] = {}
    disabled_plugin: Dict[str, ScopedMcpServerConfig] = {}
    for pname, pconfig in plugin_mcp_servers.items():
        if is_mcp_server_disabled(pname) or not _is_mcp_server_allowed_by_policy(pname, pconfig):
            disabled_plugin[pname] = pconfig
        else:
            enabled_plugin[pname] = pconfig

    dedup_result = dedup_plugin_mcp_servers(enabled_plugin, enabled_manual)
    deduped_plugin_servers: Dict[str, ScopedMcpServerConfig] = dedup_result["servers"]
    suppressed = dedup_result["suppressed"]
    deduped_plugin_servers.update(disabled_plugin)

    # Surface suppressions as mcp errors
    for item in suppressed:
        name = item["name"]
        duplicate_of = item["duplicateOf"]
        parts = name.split(":")
        if len(parts) >= 3 and parts[0] == "plugin":
            mcp_errors.append({
                "type": "mcp-server-suppressed-duplicate",
                "source": name,
                "plugin": parts[1],
                "serverName": ":".join(parts[2:]),
                "duplicateOf": duplicate_of,
            })

    # Merge: plugin < user < project < local
    configs: Dict[str, ScopedMcpServerConfig] = {
        **deduped_plugin_servers,
        **user_servers,
        **approved_project_servers,
        **local_servers,
    }

    # Apply policy filter
    filtered_configs: Dict[str, ScopedMcpServerConfig] = {}
    for fname, fconfig in configs.items():
        if not _is_mcp_server_allowed_by_policy(fname, fconfig):
            continue
        filtered_configs[fname] = fconfig

    return {"servers": filtered_configs, "errors": mcp_errors}


async def get_all_mcp_configs() -> Dict[str, Any]:
    """
    Get all MCP configurations across all scopes, including claude.ai servers.
    This may be slow due to network calls.
    Returns {"servers": ..., "errors": [...]}
    """
    import asyncio

    if does_enterprise_mcp_config_exist():
        return await get_claude_code_mcp_configs()

    # Kick off claude.ai fetch
    claudeai_promise = None
    try:
        from claude_code.services.mcp.claudeai import fetch_claude_ai_mcp_configs_if_eligible
        claudeai_promise = asyncio.ensure_future(fetch_claude_ai_mcp_configs_if_eligible())
    except (ImportError, Exception):
        pass

    result = await get_claude_code_mcp_configs(
        {}, claudeai_promise
    )
    claude_code_servers = result["servers"]
    errors = result["errors"]

    # Get claude.ai servers
    claudeai_raw: Dict[str, ScopedMcpServerConfig] = {}
    if claudeai_promise is not None:
        try:
            claudeai_raw = await claudeai_promise
        except Exception:
            pass

    policy_result = filter_mcp_servers_by_policy(claudeai_raw)
    claudeai_servers = policy_result["allowed"]

    dedup_result = dedup_claude_ai_mcp_servers(claudeai_servers, claude_code_servers)
    deduped_claudeai = dedup_result["servers"]

    # Merge: claudeai lowest precedence
    servers = {**deduped_claudeai, **claude_code_servers}
    return {"servers": servers, "errors": errors}


# ---------------------------------------------------------------------------
# Add / Remove MCP config
# ---------------------------------------------------------------------------

def add_mcp_config(name: str, config: Any, scope: ConfigScope) -> None:
    """
    Add a new MCP server configuration (synchronous version).
    Raises ValueError for invalid name or existing server.
    """
    if re.search(r"[^a-zA-Z0-9_-]", name):
        raise ValueError(
            f"Invalid name {name}. Names can only contain letters, numbers, hyphens, and underscores."
        )

    if _is_claude_in_chrome_mcp_server(name):
        raise ValueError(f'Cannot add MCP server "{name}": this name is reserved.')

    if does_enterprise_mcp_config_exist():
        raise ValueError(
            "Cannot add MCP server: enterprise MCP configuration is active and has exclusive control over MCP servers"
        )

    # Validate config
    valid, err = _validate_mcp_server_config(config)
    if not valid:
        raise ValueError(f"Invalid configuration: {err}")
    validated_config = dict(config)

    # Policy checks
    if _is_mcp_server_denied(name, validated_config):
        raise ValueError(
            f'Cannot add MCP server "{name}": server is explicitly blocked by enterprise policy'
        )
    if not _is_mcp_server_allowed_by_policy(name, validated_config):
        raise ValueError(
            f'Cannot add MCP server "{name}": not allowed by enterprise policy'
        )

    if scope == "project":
        existing = get_project_mcp_configs_from_cwd()["servers"]
        if name in existing:
            raise ValueError(f"MCP server {name} already exists in .mcp.json")

        # Build new mcpServers dict without scope fields
        mcp_servers: Dict[str, McpServerConfig] = {}
        for sname, sconfig in existing.items():
            c = {k: v for k, v in sconfig.items() if k != "scope"}
            mcp_servers[sname] = c
        mcp_servers[name] = validated_config

        try:
            _write_mcp_json_file({"mcpServers": mcp_servers})
        except Exception as e:
            raise ValueError(f"Failed to write to .mcp.json: {e}") from e

    elif scope == "user":
        global_cfg = _get_global_config()
        if (global_cfg.get("mcpServers") or {}).get(name):
            raise ValueError(f"MCP server {name} already exists in user config")

        def updater(current: Dict[str, Any]) -> Dict[str, Any]:
            mcp = dict(current.get("mcpServers") or {})
            mcp[name] = validated_config
            return {**current, "mcpServers": mcp}

        _save_global_config(updater)

    elif scope == "local":
        project_cfg = _get_current_project_config()
        if (project_cfg.get("mcpServers") or {}).get(name):
            raise ValueError(f"MCP server {name} already exists in local config")

        def updater(current: Dict[str, Any]) -> Dict[str, Any]:  # type: ignore[misc]
            mcp = dict(current.get("mcpServers") or {})
            mcp[name] = validated_config
            return {**current, "mcpServers": mcp}

        _save_current_project_config(updater)

    elif scope == "dynamic":
        raise ValueError("Cannot add MCP server to scope: dynamic")
    elif scope == "enterprise":
        raise ValueError("Cannot add MCP server to scope: enterprise")
    elif scope == "claudeai":
        raise ValueError("Cannot add MCP server to scope: claudeai")
    else:
        raise ValueError(f"Cannot add MCP server to scope: {scope}")


def remove_mcp_config(name: str, scope: ConfigScope) -> None:
    """
    Remove an MCP server configuration.
    Raises ValueError if server not found in specified scope.
    """
    if scope == "project":
        existing = get_project_mcp_configs_from_cwd()["servers"]
        if name not in existing:
            raise ValueError(f"No MCP server found with name: {name} in .mcp.json")

        mcp_servers: Dict[str, McpServerConfig] = {}
        for sname, sconfig in existing.items():
            if sname != name:
                c = {k: v for k, v in sconfig.items() if k != "scope"}
                mcp_servers[sname] = c

        try:
            _write_mcp_json_file({"mcpServers": mcp_servers})
        except Exception as e:
            raise ValueError(f"Failed to remove from .mcp.json: {e}") from e

    elif scope == "user":
        cfg = _get_global_config()
        if name not in (cfg.get("mcpServers") or {}):
            raise ValueError(f"No user-scoped MCP server found with name: {name}")

        def updater(current: Dict[str, Any]) -> Dict[str, Any]:
            mcp = dict(current.get("mcpServers") or {})
            mcp.pop(name, None)
            return {**current, "mcpServers": mcp}

        _save_global_config(updater)

    elif scope == "local":
        cfg = _get_current_project_config()
        if name not in (cfg.get("mcpServers") or {}):
            raise ValueError(f"No project-local MCP server found with name: {name}")

        def updater(current: Dict[str, Any]) -> Dict[str, Any]:  # type: ignore[misc]
            mcp = dict(current.get("mcpServers") or {})
            mcp.pop(name, None)
            return {**current, "mcpServers": mcp}

        _save_current_project_config(updater)

    else:
        raise ValueError(f"Cannot remove MCP server from scope: {scope}")


# ---------------------------------------------------------------------------
# Enable / Disable MCP servers
# ---------------------------------------------------------------------------

# Default disabled built-in (corresponds to COMPUTER_USE_MCP_SERVER_NAME when feature is on)
_DEFAULT_DISABLED_BUILTIN: Optional[str] = None
try:
    from claude_code.utils.computer_use.common import COMPUTER_USE_MCP_SERVER_NAME
    _DEFAULT_DISABLED_BUILTIN = COMPUTER_USE_MCP_SERVER_NAME
except (ImportError, Exception):
    pass


def _is_default_disabled_builtin(name: str) -> bool:
    return _DEFAULT_DISABLED_BUILTIN is not None and name == _DEFAULT_DISABLED_BUILTIN


def is_mcp_server_disabled(name: str) -> bool:
    """Check if an MCP server is disabled."""
    project_config = _get_current_project_config()
    if _is_default_disabled_builtin(name):
        enabled_servers = project_config.get("enabledMcpServers") or []
        return name not in enabled_servers
    disabled_servers = project_config.get("disabledMcpServers") or []
    return name in disabled_servers


def _toggle_membership(lst: List[str], name: str, should_contain: bool) -> List[str]:
    """Toggle membership of name in list."""
    contains = name in lst
    if contains == should_contain:
        return lst
    if should_contain:
        return lst + [name]
    return [s for s in lst if s != name]


def set_mcp_server_enabled(name: str, enabled: bool) -> None:
    """Enable or disable an MCP server."""
    is_builtin_state_change = (
        _is_default_disabled_builtin(name) and is_mcp_server_disabled(name) == enabled
    )

    def updater(current: Dict[str, Any]) -> Dict[str, Any]:
        if _is_default_disabled_builtin(name):
            prev = list(current.get("enabledMcpServers") or [])
            nxt = _toggle_membership(prev, name, enabled)
            if nxt is prev:
                return current
            return {**current, "enabledMcpServers": nxt}

        prev = list(current.get("disabledMcpServers") or [])
        nxt = _toggle_membership(prev, name, not enabled)
        if nxt is prev:
            return current
        return {**current, "disabledMcpServers": nxt}

    _save_current_project_config(updater)

    if is_builtin_state_change:
        try:
            from claude_code.services.analytics import log_event
            log_event("tengu_builtin_mcp_toggle", {"serverName": name, "enabled": enabled})
        except (ImportError, Exception):
            pass


# ---------------------------------------------------------------------------
# Misc exports
# ---------------------------------------------------------------------------

def are_mcp_configs_allowed_with_enterprise_mcp_config(
    configs: Dict[str, ScopedMcpServerConfig],
) -> bool:
    """
    Check if all MCP server configs are allowed with enterprise MCP config.
    Currently limited to sdk type with name 'claude-vscode'.
    """
    return all(
        c.get("type") == "sdk" and c.get("name") == "claude-vscode"
        for c in configs.values()
    )
