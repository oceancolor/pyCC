"""
MCP client module. Ported from services/mcp/client.ts

Manages connections to MCP (Model Context Protocol) servers:
- connectToServer: establish & cache connections to all transport types
- fetchToolsForClient / fetchResourcesForClient / fetchCommandsForClient
- callMCPTool / callMCPToolWithUrlElicitationRetry / processMCPResult
- getMcpToolsCommandsAndResources: batch-fetch from all servers
- Auth cache helpers (isMcpAuthCached, setMcpAuthCacheEntry, clearMcpAuthCache)
- setupSdkMcpClients: wire in-process SDK servers
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)

# ---------------------------------------------------------------------------
# Conditional / optional imports
# ---------------------------------------------------------------------------
if TYPE_CHECKING:
    pass

try:
    from claude_code.utils.log import log_mcp_debug, log_mcp_error  # type: ignore
except ImportError:
    def log_mcp_debug(server_name: str, msg: str) -> None:  # type: ignore
        logging.debug("[MCP:%s] %s", server_name, msg)

    def log_mcp_error(server_name: str, msg: Any) -> None:  # type: ignore
        logging.error("[MCP:%s] %s", server_name, msg)

try:
    from claude_code.utils.errors import (  # type: ignore
        error_message,
        TelemetrySafeError,
    )
except ImportError:
    def error_message(e: BaseException) -> str:  # type: ignore
        return str(e)

    class TelemetrySafeError(Exception):  # type: ignore
        def __init__(self, message: str, telemetry_message: str = "") -> None:
            super().__init__(message)
            self.telemetry_message = telemetry_message

try:
    from claude_code.utils.json_utils import json_parse, json_stringify  # type: ignore
except ImportError:
    def json_parse(s: str) -> Any:  # type: ignore
        return json.loads(s)
    def json_stringify(v: Any) -> str:  # type: ignore
        return json.dumps(v)

try:
    from claude_code.utils.env_utils import (  # type: ignore
        is_env_truthy,
        is_env_defined_falsy,
        get_claude_config_home_dir,
    )
except ImportError:
    def is_env_truthy(v: Optional[str]) -> bool:  # type: ignore
        return str(v).lower() in ("1", "true", "yes") if v else False
    def is_env_defined_falsy(v: Optional[str]) -> bool:  # type: ignore
        return v is not None and str(v).lower() in ("0", "false", "no")
    def get_claude_config_home_dir() -> str:  # type: ignore
        return os.path.expanduser("~/.config/claude")

try:
    from claude_code.utils.memoize import memoize_with_lru  # type: ignore
except ImportError:
    def memoize_with_lru(size: int = 20) -> Callable:  # type: ignore
        def decorator(fn: Callable) -> Callable:
            return lru_cache(maxsize=size)(fn)
        return decorator

try:
    from claude_code.utils.abort import create_abort_controller  # type: ignore
except ImportError:
    class _AbortController:  # type: ignore
        def __init__(self) -> None:
            self._event = asyncio.Event()
        def abort(self) -> None:
            self._event.set()
        @property
        def signal(self) -> asyncio.Event:
            return self._event

    def create_abort_controller() -> _AbortController:  # type: ignore
        return _AbortController()

try:
    from claude_code.utils.http import get_mcp_user_agent  # type: ignore
except ImportError:
    def get_mcp_user_agent() -> str:  # type: ignore
        return "claude-code/0.0.0 (Python port)"

try:
    from claude_code.utils.sleep import sleep  # type: ignore
except ImportError:
    async def sleep(ms: int) -> None:  # type: ignore
        await asyncio.sleep(ms / 1000.0)

try:
    from claude_code.services.analytics import log_event  # type: ignore
except ImportError:
    def log_event(name: str, meta: Optional[Dict[str, Any]] = None) -> None:  # type: ignore
        pass

try:
    from claude_code.services.mcp.auth import (  # type: ignore
        ClaudeAuthProvider,
        has_mcp_discovery_but_no_token,
        wrap_fetch_with_step_up_detection,
    )
except ImportError:
    ClaudeAuthProvider = None  # type: ignore
    def has_mcp_discovery_but_no_token(*a: Any) -> bool:  # type: ignore
        return False
    def wrap_fetch_with_step_up_detection(*a: Any) -> Any:  # type: ignore
        return a[0] if a else None

try:
    from claude_code.services.mcp.types import (  # type: ignore
        ConnectedMCPServer,
        MCPServerConnection,
        McpSdkServerConfig,
        ScopedMcpServerConfig,
        ServerResource,
    )
except ImportError:
    ConnectedMCPServer = dict  # type: ignore
    MCPServerConnection = dict  # type: ignore
    McpSdkServerConfig = dict  # type: ignore
    ScopedMcpServerConfig = dict  # type: ignore
    ServerResource = dict  # type: ignore

try:
    from claude_code.services.mcp.config import get_all_mcp_configs, is_mcp_server_disabled  # type: ignore
except ImportError:
    def get_all_mcp_configs(*a: Any) -> List[Any]:  # type: ignore
        return []
    def is_mcp_server_disabled(*a: Any) -> bool:  # type: ignore
        return False

try:
    from claude_code.services.mcp.normalization import normalize_name_for_mcp  # type: ignore
except ImportError:
    def normalize_name_for_mcp(name: str) -> str:  # type: ignore
        return name.replace(" ", "_")

try:
    from claude_code.services.mcp.mcp_string_utils import build_mcp_tool_name  # type: ignore
except ImportError:
    def build_mcp_tool_name(server_name: str, tool_name: str) -> str:  # type: ignore
        return f"mcp__{server_name}__{tool_name}"

try:
    from claude_code.utils.mcp_validation import (  # type: ignore
        get_content_size_estimate,
        mcp_content_needs_truncation,
        truncate_mcp_content_if_needed,
        MCPToolResult,
    )
except ImportError:
    MCPToolResult = list  # type: ignore
    def get_content_size_estimate(content: Any) -> int:  # type: ignore
        return len(json_stringify(content))
    def mcp_content_needs_truncation(content: Any, max_bytes: int = 5_000_000) -> bool:  # type: ignore
        return get_content_size_estimate(content) > max_bytes
    def truncate_mcp_content_if_needed(content: Any, max_bytes: int = 5_000_000) -> Any:  # type: ignore
        return content

try:
    from claude_code.utils.mcp_output_storage import (  # type: ignore
        get_binary_blob_saved_message,
        get_format_description,
        get_large_output_instructions,
        persist_binary_content,
    )
except ImportError:
    def get_binary_blob_saved_message(path: str, format_desc: str) -> str:  # type: ignore
        return f"Binary content saved to {path}"
    def get_format_description(mime_type: str) -> str:  # type: ignore
        return mime_type.split("/")[-1].upper()
    def get_large_output_instructions(path: str) -> str:  # type: ignore
        return f"Output too large, saved to {path}"
    async def persist_binary_content(data: bytes, mime_type: str) -> str:  # type: ignore
        return "/tmp/mcp_blob"

try:
    from claude_code.utils.tool_result_storage import persist_tool_result, is_persist_error  # type: ignore
except ImportError:
    async def persist_tool_result(content: Any) -> Any:  # type: ignore
        return content
    def is_persist_error(e: Any) -> bool:  # type: ignore
        return False

try:
    from claude_code.utils.image_resizer import maybe_resize_and_downsample_image_buffer  # type: ignore
except ImportError:
    async def maybe_resize_and_downsample_image_buffer(data: bytes, mime_type: str) -> bytes:  # type: ignore
        return data

try:
    from claude_code.utils.sanitization import recursively_sanitize_unicode  # type: ignore
except ImportError:
    def recursively_sanitize_unicode(v: Any) -> Any:  # type: ignore
        return v

try:
    from claude_code.utils.cleanup_registry import register_cleanup  # type: ignore
except ImportError:
    def register_cleanup(fn: Callable) -> None:  # type: ignore
        pass

try:
    from claude_code.utils.subprocess_env import subprocess_env  # type: ignore
except ImportError:
    def subprocess_env() -> Dict[str, str]:  # type: ignore
        return dict(os.environ)

try:
    from claude_code.utils.session_ingress_auth import get_session_ingress_auth_token  # type: ignore
except ImportError:
    def get_session_ingress_auth_token() -> Optional[str]:  # type: ignore
        return None

try:
    from claude_code.utils.code_indexing import detect_code_indexing_from_mcp_server_name  # type: ignore
except ImportError:
    def detect_code_indexing_from_mcp_server_name(name: str) -> bool:  # type: ignore
        return False

try:
    from claude_code.utils.ide import maybe_notify_ide_connected  # type: ignore
except ImportError:
    def maybe_notify_ide_connected(name: str, server_type: str) -> None:  # type: ignore
        pass

try:
    from claude_code.utils.auth import check_and_refresh_oauth_token_if_needed, get_claude_ai_oauth_tokens, handle_oauth_401_error  # type: ignore
except ImportError:
    async def check_and_refresh_oauth_token_if_needed() -> None:  # type: ignore
        pass
    def get_claude_ai_oauth_tokens() -> Optional[Any]:  # type: ignore
        return None
    async def handle_oauth_401_error(token: str) -> bool:  # type: ignore
        return False

try:
    from claude_code.utils.debug import log_for_debugging  # type: ignore
except ImportError:
    def log_for_debugging(msg: str) -> None:  # type: ignore
        pass

try:
    from claude_code.utils.mtls import get_web_socket_tls_options  # type: ignore
except ImportError:
    def get_web_socket_tls_options() -> Optional[Dict[str, Any]]:  # type: ignore
        return None

try:
    from claude_code.utils.proxy import (  # type: ignore
        get_proxy_fetch_options,
        get_web_socket_proxy_agent,
        get_web_socket_proxy_url,
    )
except ImportError:
    def get_proxy_fetch_options() -> Dict[str, Any]:  # type: ignore
        return {}
    def get_web_socket_proxy_agent(url: str) -> Optional[Any]:  # type: ignore
        return None
    def get_web_socket_proxy_url(url: str) -> Optional[str]:  # type: ignore
        return None

try:
    from claude_code.constants.oauth import get_oauth_config  # type: ignore
except ImportError:
    def get_oauth_config() -> Dict[str, str]:  # type: ignore
        return {
            "MCP_PROXY_URL": "https://claude.ai",
            "MCP_PROXY_PATH": "/api/mcp/{server_id}",
        }

try:
    from claude_code.constants.product import PRODUCT_URL  # type: ignore
except ImportError:
    PRODUCT_URL = "https://www.anthropic.com"

try:
    from claude_code.bootstrap.state import get_original_cwd, get_session_id  # type: ignore
except ImportError:
    def get_original_cwd() -> str:  # type: ignore
        return os.getcwd()
    def get_session_id() -> str:  # type: ignore
        return "unknown-session"

try:
    from claude_code.services.mcp.elicitation_handler import (  # type: ignore
        run_elicitation_hooks,
        run_elicitation_result_hooks,
        ElicitationWaitingState,
    )
except ImportError:
    async def run_elicitation_hooks(*a: Any, **kw: Any) -> Any:  # type: ignore
        return None
    async def run_elicitation_result_hooks(*a: Any, **kw: Any) -> None:  # type: ignore
        pass
    ElicitationWaitingState = dict  # type: ignore

try:
    from claude_code.services.mcp.utils import get_logging_safe_mcp_base_url  # type: ignore
except ImportError:
    def get_logging_safe_mcp_base_url(config: Any) -> Optional[str]:  # type: ignore
        if isinstance(config, dict):
            return config.get("url")
        return getattr(config, "url", None)

try:
    from claude_code.services.mcp.headers_helper import get_mcp_server_headers  # type: ignore
except ImportError:
    async def get_mcp_server_headers(name: str, config: Any) -> Dict[str, str]:  # type: ignore
        return {}

try:
    from claude_code.tools.mcp_tool import MCPTool, MCPProgress  # type: ignore
    from claude_code.tools.list_mcp_resources_tool import ListMcpResourcesTool  # type: ignore
    from claude_code.tools.read_mcp_resource_tool import ReadMcpResourceTool  # type: ignore
    from claude_code.tools.mcp_auth_tool import create_mcp_auth_tool  # type: ignore
except ImportError:
    MCPTool = None  # type: ignore
    MCPProgress = None  # type: ignore
    ListMcpResourcesTool = None  # type: ignore
    ReadMcpResourceTool = None  # type: ignore
    def create_mcp_auth_tool(*a: Any) -> Any:  # type: ignore
        return None

try:
    from claude_code.services.mcp.claudeai import mark_claude_ai_mcp_connected  # type: ignore
except ImportError:
    def mark_claude_ai_mcp_connected() -> None:  # type: ignore
        pass

try:
    from claude_code.utils.secure_storage.mac_os_keychain_helpers import clear_keychain_cache  # type: ignore
except ImportError:
    def clear_keychain_cache() -> None:  # type: ignore
        pass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MCP_TOOL_TIMEOUT_MS = 100_000_000  # ~27.8 hours
MAX_MCP_DESCRIPTION_LENGTH = 2048
MCP_AUTH_CACHE_TTL_MS = 15 * 60 * 1000  # 15 min
MCP_REQUEST_TIMEOUT_MS = 60_000  # 60 seconds
MCP_STREAMABLE_HTTP_ACCEPT = "application/json, text/event-stream"
IMAGE_MIME_TYPES: Set[str] = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MCP_FETCH_CACHE_SIZE = 20

ALLOWED_IDE_TOOLS = {"mcp__ide__executeCode", "mcp__ide__getDiagnostics"}


def get_mcp_tool_timeout_ms() -> int:
    """
    Gets the timeout for MCP tool calls in milliseconds.
    Uses MCP_TOOL_TIMEOUT env var if set; defaults to ~27.8 hours.
    """
    return int(os.environ.get("MCP_TOOL_TIMEOUT") or "") if os.environ.get("MCP_TOOL_TIMEOUT") else DEFAULT_MCP_TOOL_TIMEOUT_MS


def get_connection_timeout_ms() -> int:
    return int(os.environ.get("MCP_TIMEOUT") or "") if os.environ.get("MCP_TIMEOUT") else 30_000


def get_mcp_server_connection_batch_size() -> int:
    return int(os.environ.get("MCP_SERVER_CONNECTION_BATCH_SIZE") or "") \
        if os.environ.get("MCP_SERVER_CONNECTION_BATCH_SIZE") else 3


def _get_remote_mcp_server_connection_batch_size() -> int:
    return int(os.environ.get("MCP_REMOTE_SERVER_CONNECTION_BATCH_SIZE") or "") \
        if os.environ.get("MCP_REMOTE_SERVER_CONNECTION_BATCH_SIZE") else 20


def _is_local_mcp_server(config: Any) -> bool:
    server_type = (
        config.get("type") if isinstance(config, dict)
        else getattr(config, "type", None)
    )
    return not server_type or server_type in ("stdio", "sdk")


def is_included_mcp_tool(tool: Any) -> bool:
    """For IDE MCP servers, only include specific tools."""
    tool_name = getattr(tool, "name", "") or (tool.get("name", "") if isinstance(tool, dict) else "")
    return not tool_name.startswith("mcp__ide__") or tool_name in ALLOWED_IDE_TOOLS


# ---------------------------------------------------------------------------
# Error classes
# ---------------------------------------------------------------------------

class McpAuthError(Exception):
    """MCP tool call failed due to authentication issues (e.g. expired OAuth token → 401)."""
    server_name: str

    def __init__(self, server_name: str, message: str) -> None:
        super().__init__(message)
        self.name = "McpAuthError"
        self.server_name = server_name


class McpSessionExpiredError(Exception):
    """
    Thrown when an MCP session has expired and the connection cache has been cleared.
    Caller should get a fresh client via ensureConnectedClient and retry.
    """
    def __init__(self, server_name: str) -> None:
        super().__init__(f'MCP server "{server_name}" session expired')
        self.name = "McpSessionExpiredError"


class McpToolCallError(TelemetrySafeError):
    """
    Thrown when an MCP tool returns isError: true.
    Carries the result's _meta so SDK consumers can still receive it.
    """
    def __init__(
        self,
        message: str,
        telemetry_message: str,
        mcp_meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, telemetry_message)
        self.name = "McpToolCallError"
        self.mcp_meta = mcp_meta


# ---------------------------------------------------------------------------
# MCP Session expired detection
# ---------------------------------------------------------------------------

def is_mcp_session_expired_error(error: BaseException) -> bool:
    """
    Detects whether an error is an MCP "Session not found" error (HTTP 404 + JSON-RPC -32001).
    Per MCP spec, servers return 404 when a session ID is no longer valid.
    """
    http_status = getattr(error, "code", None)
    if http_status != 404:
        return False
    msg = str(error)
    return '"code":-32001' in msg or '"code": -32001' in msg


# ---------------------------------------------------------------------------
# Auth cache helpers
# ---------------------------------------------------------------------------

McpAuthCacheData = Dict[str, Dict[str, int]]

_auth_cache_promise: Optional[asyncio.Task[McpAuthCacheData]] = None

_write_chain: asyncio.Future = asyncio.get_event_loop().create_future() \
    if asyncio.get_event_loop().is_running() else asyncio.new_event_loop().create_future()


def _get_mcp_auth_cache_path() -> str:
    return os.path.join(get_claude_config_home_dir(), "mcp-needs-auth-cache.json")


async def _get_mcp_auth_cache() -> McpAuthCacheData:
    """
    Memoized read of the auth cache. Shared across concurrent callers.
    Invalidated on write (set_mcp_auth_cache_entry) and clear (clear_mcp_auth_cache).
    """
    global _auth_cache_promise

    if _auth_cache_promise is not None:
        return await _auth_cache_promise

    loop = asyncio.get_event_loop()
    fut: asyncio.Future[McpAuthCacheData] = loop.create_future()
    _auth_cache_promise = asyncio.ensure_future(_read_auth_cache_file(fut))
    return await _auth_cache_promise


async def _read_auth_cache_file(fut: asyncio.Future) -> McpAuthCacheData:
    try:
        path = _get_mcp_auth_cache_path()
        with open(path, "r") as f:
            data = json_parse(f.read())
        return data
    except Exception:
        return {}


async def is_mcp_auth_cached(server_id: str) -> bool:
    """Return True if the server recently returned 401 (within TTL)."""
    cache = await _get_mcp_auth_cache()
    entry = cache.get(server_id)
    if not entry:
        return False
    return int(time.time() * 1000) - entry.get("timestamp", 0) < MCP_AUTH_CACHE_TTL_MS


# Serialize cache writes to prevent concurrent read-modify-write races
_cache_write_lock = asyncio.Lock()


def set_mcp_auth_cache_entry(server_id: str) -> None:
    """Record that a server returned 401. Async fire-and-forget."""
    global _auth_cache_promise

    async def _write() -> None:
        global _auth_cache_promise
        async with _cache_write_lock:
            try:
                cache = await _get_mcp_auth_cache()
                cache[server_id] = {"timestamp": int(time.time() * 1000)}
                cache_path = _get_mcp_auth_cache_path()
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, "w") as f:
                    f.write(json_stringify(cache))
                # Invalidate so subsequent reads see the new entry
                _auth_cache_promise = None
            except Exception:
                pass  # Best-effort

    asyncio.ensure_future(_write())


def clear_mcp_auth_cache() -> None:
    """Invalidate the in-memory auth cache and delete the cache file."""
    global _auth_cache_promise
    _auth_cache_promise = None
    try:
        os.unlink(_get_mcp_auth_cache_path())
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# Server URL analytics helper
# ---------------------------------------------------------------------------

def _mcp_base_url_analytics(server_ref: Any) -> Dict[str, Any]:
    """Return analytics field for a server's base URL (query-stripped, safe to log)."""
    url = get_logging_safe_mcp_base_url(server_ref)
    if url:
        return {"mcpServerBaseUrl": url}
    return {}


# ---------------------------------------------------------------------------
# Auth failure helper
# ---------------------------------------------------------------------------

def handle_remote_auth_failure(
    name: str,
    server_ref: Any,
    transport_type: str,
) -> Dict[str, Any]:
    """
    Shared handler for sse/http/claudeai-proxy auth failures during connect:
    emits event, caches the needs-auth entry, and returns the needs-auth connection result.
    """
    log_event("tengu_mcp_server_needs_auth", {
        "transportType": transport_type,
        **_mcp_base_url_analytics(server_ref),
    })
    label = {"sse": "SSE", "http": "HTTP", "claudeai-proxy": "claude.ai proxy"}
    log_mcp_debug(
        name,
        f"Authentication required for {label.get(transport_type, transport_type)} server",
    )
    set_mcp_auth_cache_entry(name)
    return {"name": name, "type": "needs-auth", "config": server_ref}


# ---------------------------------------------------------------------------
# Claude.ai proxy fetch
# ---------------------------------------------------------------------------

async def create_claude_ai_proxy_fetch(
    inner_fetch: Callable,
) -> Callable:
    """
    Fetch wrapper for claude.ai proxy connections.

    Attaches the OAuth bearer token and retries once on 401 via handle_oauth_401_error.
    Mirrors the retry logic from withRetry.ts / grove.ts for the Anthropic API path.
    """
    async def do_request() -> Tuple[Any, str]:
        await check_and_refresh_oauth_token_if_needed()
        current_tokens = get_claude_ai_oauth_tokens()
        if not current_tokens:
            raise RuntimeError("No claude.ai OAuth token available")
        access_token = (
            current_tokens.access_token
            if hasattr(current_tokens, "access_token")
            else current_tokens.get("accessToken", "")
        )
        response = await inner_fetch(
            {
                "Authorization": f"Bearer {access_token}",
            }
        )
        return response, access_token

    async def wrapped(url: Any, **kwargs: Any) -> Any:
        response, sent_token = await do_request()

        status = getattr(response, "status", None) or getattr(response, "status_code", None)
        if status != 401:
            return response

        token_changed = False
        try:
            token_changed = await handle_oauth_401_error(sent_token)
        except Exception:
            pass

        log_event("tengu_mcp_claudeai_proxy_401", {"tokenChanged": token_changed})

        if not token_changed:
            # Check if token changed underneath us (ELOCKED contention)
            current = get_claude_ai_oauth_tokens()
            now_token = (
                getattr(current, "access_token", None) or
                (current.get("accessToken") if isinstance(current, dict) else None)
            ) if current else None
            if not now_token or now_token == sent_token:
                return response

        try:
            resp2, _ = await do_request()
            return resp2
        except Exception:
            # Retry itself failed (network error). Return the original 401.
            return response

    return wrapped


# ---------------------------------------------------------------------------
# wrapFetchWithTimeout
# ---------------------------------------------------------------------------

def wrap_fetch_with_timeout(base_fetch: Callable) -> Callable:
    """
    Wraps a fetch function to apply a fresh timeout signal to each request.

    Avoids the stale-AbortSignal bug that kills all subsequent requests after
    the first timeout fires.

    Also ensures the Accept header required by MCP Streamable HTTP spec is
    present on POSTs. GET requests are excluded (long-lived SSE streams).
    """
    async def wrapped(url: Any, **kwargs: Any) -> Any:
        method = kwargs.pop("method", "GET").upper()

        # Skip timeout for GET (long-lived SSE streams)
        if method == "GET":
            return await base_fetch(url, method=method, **kwargs)

        # Ensure Streamable-HTTP Accept header
        headers = dict(kwargs.pop("headers", {}) or {})
        if "accept" not in {k.lower() for k in headers}:
            headers["accept"] = MCP_STREAMABLE_HTTP_ACCEPT

        timeout_s = MCP_REQUEST_TIMEOUT_MS / 1000.0
        try:
            return await asyncio.wait_for(
                base_fetch(url, method=method, headers=headers, **kwargs),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            raise TimeoutError("The operation timed out.")

    return wrapped


# ---------------------------------------------------------------------------
# Server cache key
# ---------------------------------------------------------------------------

def get_server_cache_key(
    name: str,
    server_ref: Any,
) -> str:
    """Generates the cache key for a server connection."""
    return f"{name}-{json_stringify(server_ref if isinstance(server_ref, dict) else vars(server_ref))}"


# ---------------------------------------------------------------------------
# Connection cache (mirrors TS memoize on connectToServer)
# ---------------------------------------------------------------------------

_server_connection_cache: Dict[str, asyncio.Future[Dict[str, Any]]] = {}


def _server_type(config: Any) -> Optional[str]:
    return config.get("type") if isinstance(config, dict) else getattr(config, "type", None)


def _server_url(config: Any) -> Optional[str]:
    return config.get("url") if isinstance(config, dict) else getattr(config, "url", None)


def _server_env(config: Any) -> Dict[str, str]:
    env = config.get("env") if isinstance(config, dict) else getattr(config, "env", None)
    return env or {}


def _server_command(config: Any) -> str:
    return config.get("command", "") if isinstance(config, dict) else getattr(config, "command", "")


def _server_args(config: Any) -> List[str]:
    return config.get("args", []) if isinstance(config, dict) else getattr(config, "args", [])


def _server_oauth(config: Any) -> Any:
    return config.get("oauth") if isinstance(config, dict) else getattr(config, "oauth", None)


# ---------------------------------------------------------------------------
# connectToServer
# ---------------------------------------------------------------------------

async def connect_to_server(
    name: str,
    server_ref: Any,
    server_stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Attempts to connect to a single MCP server.
    Memoized by server cache key so concurrent callers share the same connection future.

    Supports: stdio, sse, sse-ide, ws-ide, ws, http, claudeai-proxy, sdk transport types.

    Returns a dict with 'type' key: 'connected' | 'needs-auth' | 'failed'.
    """
    cache_key = get_server_cache_key(name, server_ref)
    if cache_key in _server_connection_cache:
        return await _server_connection_cache[cache_key]

    loop = asyncio.get_event_loop()
    fut: asyncio.Future[Dict[str, Any]] = loop.create_future()
    _server_connection_cache[cache_key] = fut

    try:
        result = await _do_connect_to_server(name, server_ref, server_stats)
        fut.set_result(result)
        return result
    except Exception as e:
        fut.set_exception(e)
        _server_connection_cache.pop(cache_key, None)
        raise


async def _do_connect_to_server(
    name: str,
    server_ref: Any,
    server_stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Internal: performs the actual connection to an MCP server.

    Handles all transport types and authentication.
    Returns MCPServerConnection dict.
    """
    connect_start_time = int(time.time() * 1000)
    server_type = _server_type(server_ref)
    server_url_str = _server_url(server_ref)

    log_mcp_debug(name, f"Connecting to server (type={server_type!r})")

    if server_type == "sdk":
        raise RuntimeError("SDK servers should be handled in print.ts")

    # ----------------------------------------------------------------
    # Check if already cached as needing auth
    # ----------------------------------------------------------------
    if await is_mcp_auth_cached(name):
        log_mcp_debug(name, "Server recently returned 401, skipping connection")
        return {"name": name, "type": "needs-auth", "config": server_ref}

    # ----------------------------------------------------------------
    # Bail early for servers known to have discovery but no token
    # ----------------------------------------------------------------
    if server_type in ("sse", "http") and server_url_str:
        if has_mcp_discovery_but_no_token(name, server_ref):
            log_mcp_debug(name, "Discovery state found but no token — skipping connection")
            return handle_remote_auth_failure(name, server_ref, server_type)

    # ----------------------------------------------------------------
    # Prepare transport (type-specific logic)
    # ----------------------------------------------------------------
    connection_timeout_s = get_connection_timeout_ms() / 1000.0
    client_info: Dict[str, Any] = {
        "name": "claude-code",
        "title": "Claude Code",
        "version": "0.0.0",
        "description": "Anthropic's agentic coding tool",
        "websiteUrl": PRODUCT_URL,
    }

    try:
        if server_type in ("sse", "http"):
            # Remote server with OAuth auth
            auth_provider = ClaudeAuthProvider(name, server_ref) if ClaudeAuthProvider else None
            combined_headers = await get_mcp_server_headers(name, server_ref)

            log_mcp_debug(
                name,
                f"{'SSE' if server_type == 'sse' else 'HTTP'} transport initialized, "
                f"url={server_url_str}",
            )

            # Build connection metadata
            conn: Dict[str, Any] = {
                "type": "connected",
                "name": name,
                "config": server_ref,
                "transport_type": server_type,
                "auth_provider": auth_provider,
                "headers": combined_headers,
                "connected_at": int(time.time() * 1000),
            }

            # Try to fetch tools to confirm connectivity
            try:
                tools_result = await asyncio.wait_for(
                    _probe_server_tools(name, server_url_str, auth_provider, combined_headers, server_type),
                    timeout=connection_timeout_s,
                )
                conn["tools"] = tools_result
                conn["server_info"] = {"type": server_type, "url": server_url_str}
            except Exception as probe_err:
                msg = error_message(probe_err)
                if "401" in msg or "Unauthorized" in msg or "unauthorized" in msg:
                    return handle_remote_auth_failure(name, server_ref, server_type)
                log_mcp_debug(name, f"Tool probe failed: {msg}")
                # Still count as connected; tool fetch will be retried lazily

            log_event("tengu_mcp_server_connected", {
                "transportType": server_type,
                "serverName": name,
                "connectDurationMs": int(time.time() * 1000) - connect_start_time,
                **_mcp_base_url_analytics(server_ref),
            })
            return conn

        elif server_type == "claudeai-proxy":
            # claude.ai proxy
            tokens = get_claude_ai_oauth_tokens()
            if not tokens:
                raise RuntimeError("No claude.ai OAuth token found")

            oauth_config = get_oauth_config()
            server_id = (
                server_ref.get("id") if isinstance(server_ref, dict)
                else getattr(server_ref, "id", "")
            )
            proxy_url = (
                oauth_config["MCP_PROXY_URL"]
                + oauth_config["MCP_PROXY_PATH"].replace("{server_id}", str(server_id))
            )

            log_mcp_debug(name, f"Using claude.ai proxy at {proxy_url}")

            conn = {
                "type": "connected",
                "name": name,
                "config": server_ref,
                "transport_type": "claudeai-proxy",
                "proxy_url": proxy_url,
                "connected_at": int(time.time() * 1000),
            }

            log_event("tengu_mcp_server_connected", {
                "transportType": "claudeai-proxy",
                "serverName": name,
                "connectDurationMs": int(time.time() * 1000) - connect_start_time,
                **_mcp_base_url_analytics(server_ref),
            })
            mark_claude_ai_mcp_connected()
            return conn

        elif server_type in ("stdio", None):
            # Local subprocess
            final_command = os.environ.get("CLAUDE_CODE_SHELL_PREFIX") or _server_command(server_ref)
            final_args = (
                [f"{_server_command(server_ref)} {' '.join(_server_args(server_ref))}"]
                if os.environ.get("CLAUDE_CODE_SHELL_PREFIX")
                else _server_args(server_ref)
            )
            env = {**subprocess_env(), **_server_env(server_ref)}

            log_mcp_debug(name, f"Starting stdio subprocess: {final_command} {' '.join(final_args)}")

            process = await asyncio.wait_for(
                _start_stdio_subprocess(name, final_command, final_args, env),
                timeout=connection_timeout_s,
            )

            conn = {
                "type": "connected",
                "name": name,
                "config": server_ref,
                "transport_type": "stdio",
                "process": process,
                "connected_at": int(time.time() * 1000),
            }

            # Code-indexing detection
            if detect_code_indexing_from_mcp_server_name(name):
                conn["is_code_indexing"] = True
                log_mcp_debug(name, "Detected code indexing MCP server")

            maybe_notify_ide_connected(name, "stdio")

            log_event("tengu_mcp_server_connected", {
                "transportType": "stdio",
                "serverName": name,
                "connectDurationMs": int(time.time() * 1000) - connect_start_time,
            })
            return conn

        elif server_type in ("sse-ide", "ws-ide", "ws"):
            conn = {
                "type": "connected",
                "name": name,
                "config": server_ref,
                "transport_type": server_type,
                "url": server_url_str,
                "connected_at": int(time.time() * 1000),
            }
            maybe_notify_ide_connected(name, server_type)

            log_event("tengu_mcp_server_connected", {
                "transportType": server_type,
                "serverName": name,
                "connectDurationMs": int(time.time() * 1000) - connect_start_time,
                **_mcp_base_url_analytics(server_ref),
            })
            return conn

        else:
            raise ValueError(f"Unsupported server type: {server_type}")

    except McpAuthError as e:
        log_mcp_debug(name, f"Auth error during connect: {e}")
        return handle_remote_auth_failure(name, server_ref, server_type or "unknown")

    except Exception as e:
        msg = error_message(e)
        log_mcp_debug(name, f"Failed to connect: {msg}")
        log_event("tengu_mcp_server_failed", {
            "transportType": server_type,
            "serverName": name,
            "errorMessage": msg,
            "connectDurationMs": int(time.time() * 1000) - connect_start_time,
            **_mcp_base_url_analytics(server_ref),
        })
        return {
            "name": name,
            "type": "failed",
            "config": server_ref,
            "error": msg,
        }


async def _probe_server_tools(
    name: str,
    url: Optional[str],
    auth_provider: Any,
    headers: Dict[str, str],
    transport_type: str,
) -> List[Any]:
    """
    Lightweight probe: fetch the tool list from the MCP server to confirm connectivity.
    Returns an empty list if tools cannot be fetched.
    """
    if not url:
        return []
    try:
        # Attempt GET /tools or equivalent
        req_headers = dict(headers)
        req_headers.setdefault("User-Agent", get_mcp_user_agent())
        if auth_provider:
            tokens = await auth_provider.tokens()
            if tokens and tokens.access_token:
                req_headers["Authorization"] = f"Bearer {tokens.access_token}"

        import urllib.request
        req = urllib.request.Request(url.rstrip("/") + "/tools", headers=req_headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode()
            data = json.loads(body)
            return data.get("tools", [])
    except Exception:
        return []


async def _start_stdio_subprocess(
    name: str,
    command: str,
    args: List[str],
    env: Dict[str, str],
) -> asyncio.subprocess.Process:
    """
    Starts a stdio subprocess for an MCP server.
    Returns the process handle.
    """
    process = await asyncio.create_subprocess_exec(
        command,
        *args,
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    log_mcp_debug(name, f"Started subprocess PID={process.pid}")
    return process


# ---------------------------------------------------------------------------
# clearServerCache
# ---------------------------------------------------------------------------

async def clear_server_cache(
    name: Optional[str] = None,
    server_ref: Optional[Any] = None,
) -> None:
    """
    Clears the server connection cache.
    If name/server_ref are provided, clears only that specific server's cache.
    Otherwise, clears all cached connections.
    """
    global _server_connection_cache

    if name and server_ref:
        cache_key = get_server_cache_key(name, server_ref)
        conn = _server_connection_cache.pop(cache_key, None)
        if conn:
            try:
                result = await conn
                # Close the subprocess if it's a stdio connection
                process = (result or {}).get("process")
                if process and not process.returncode:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        process.kill()
            except Exception as e:
                log_mcp_debug(name, f"Error during cache clear: {error_message(e)}")
    else:
        old_cache = _server_connection_cache
        _server_connection_cache = {}
        for key, conn_fut in old_cache.items():
            try:
                result = await conn_fut
                process = (result or {}).get("process")
                if process and not process.returncode:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        process.kill()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# ensureConnectedClient
# ---------------------------------------------------------------------------

async def ensure_connected_client(
    name: str,
    server_ref: Any,
) -> Optional[Dict[str, Any]]:
    """
    Ensures we have a live, connected client for the given server.

    If the cached client is for a stale session, clears the cache and reconnects.
    Returns the connected MCPServerConnection, or None on failure.
    """
    try:
        conn = await connect_to_server(name, server_ref)
        if conn.get("type") == "connected":
            return conn
        return None
    except McpSessionExpiredError:
        # Session expired: clear cache and reconnect
        log_mcp_debug(name, "Session expired, clearing cache and reconnecting")
        await clear_server_cache(name, server_ref)
        try:
            conn = await connect_to_server(name, server_ref)
            if conn.get("type") == "connected":
                return conn
        except Exception as e:
            log_mcp_debug(name, f"Reconnection failed: {error_message(e)}")
        return None
    except Exception as e:
        log_mcp_debug(name, f"Connection failed: {error_message(e)}")
        return None


# ---------------------------------------------------------------------------
# areMcpConfigsEqual
# ---------------------------------------------------------------------------

def are_mcp_configs_equal(
    a: Any,
    b: Any,
) -> bool:
    """
    Compares two MCP server configurations to determine if they are functionally equivalent.
    Used to detect config changes that require reconnection.
    """
    try:
        return json_stringify(
            a if isinstance(a, dict) else vars(a)
        ) == json_stringify(
            b if isinstance(b, dict) else vars(b)
        )
    except Exception:
        return False


# ---------------------------------------------------------------------------
# mcpToolInputToAutoClassifierInput
# ---------------------------------------------------------------------------

def mcp_tool_input_to_auto_classifier_input(tool_input: Any) -> Dict[str, Any]:
    """Convert MCP tool input to a format suitable for auto-classifier processing."""
    if isinstance(tool_input, dict):
        return tool_input
    return vars(tool_input)


# ---------------------------------------------------------------------------
# inferCompactSchema
# ---------------------------------------------------------------------------

def infer_compact_schema(value: Any, depth: int = 2) -> str:
    """
    Infers a compact JSON schema description from a value.
    Used for structured content display.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        if not value:
            return "array"
        if depth <= 0:
            return "array"
        item_schema = infer_compact_schema(value[0], depth - 1)
        return f"array<{item_schema}>"
    if isinstance(value, dict):
        if not value or depth <= 0:
            return "object"
        fields = []
        for k, v in list(value.items())[:5]:
            fields.append(f"{k}: {infer_compact_schema(v, depth - 1)}")
        suffix = ", ..." if len(value) > 5 else ""
        return "{" + ", ".join(fields) + suffix + "}"
    return type(value).__name__


# ---------------------------------------------------------------------------
# fetchToolsForClient
# ---------------------------------------------------------------------------

_tools_cache: Dict[str, Tuple[float, List[Any]]] = {}
_TOOLS_CACHE_TTL_S = 60.0


async def fetch_tools_for_client(
    client: Dict[str, Any],
    *,
    force_refresh: bool = False,
) -> List[Any]:
    """
    Fetches the list of tools available from a connected MCP server.
    Results are memoized with an LRU cache (configurable TTL).

    Returns a list of Tool-like dicts/objects.
    """
    client_key = client.get("name", "")
    if not force_refresh and client_key in _tools_cache:
        cached_at, cached_tools = _tools_cache[client_key]
        if time.time() - cached_at < _TOOLS_CACHE_TTL_S:
            return cached_tools

    if client.get("type") != "connected":
        return []

    conn_type = client.get("transport_type")
    log_mcp_debug(client_key, f"Fetching tools (transport={conn_type!r})")

    tools = []
    try:
        tools = await _fetch_tools_from_connection(client)
    except Exception as e:
        log_mcp_debug(client_key, f"Failed to fetch tools: {error_message(e)}")
        if _is_auth_error(e):
            raise McpAuthError(client_key, f"Auth error fetching tools: {error_message(e)}")
        return []

    # Apply description length cap
    capped_tools = []
    for tool in tools:
        if isinstance(tool, dict):
            desc = tool.get("description") or ""
            if len(desc) > MAX_MCP_DESCRIPTION_LENGTH:
                tool = {**tool, "description": desc[:MAX_MCP_DESCRIPTION_LENGTH]}
            capped_tools.append(tool)
        else:
            capped_tools.append(tool)

    _tools_cache[client_key] = (time.time(), capped_tools)
    return capped_tools


async def _fetch_tools_from_connection(client: Dict[str, Any]) -> List[Any]:
    """Low-level: fetch tool list from a connected client."""
    tools = client.get("tools")
    if tools is not None:
        return tools
    # Could expand to call an actual MCP SDK client here
    return []


def _is_auth_error(e: BaseException) -> bool:
    """Heuristic: is this error an authentication/authorization error?"""
    msg = error_message(e).lower()
    return any(k in msg for k in ("401", "unauthorized", "403", "forbidden", "auth"))


# ---------------------------------------------------------------------------
# fetchResourcesForClient
# ---------------------------------------------------------------------------

_resources_cache: Dict[str, Tuple[float, List[Any]]] = {}


async def fetch_resources_for_client(
    client: Dict[str, Any],
    *,
    force_refresh: bool = False,
) -> List[Any]:
    """
    Fetches the list of resources available from a connected MCP server.
    Memoized with LRU cache.
    """
    client_key = client.get("name", "")
    if not force_refresh and client_key in _resources_cache:
        cached_at, cached_resources = _resources_cache[client_key]
        if time.time() - cached_at < _TOOLS_CACHE_TTL_S:
            return cached_resources

    if client.get("type") != "connected":
        return []

    try:
        resources: List[Any] = await _fetch_resources_from_connection(client)
        _resources_cache[client_key] = (time.time(), resources)
        return resources
    except Exception as e:
        log_mcp_debug(client_key, f"Failed to fetch resources: {error_message(e)}")
        return []


async def _fetch_resources_from_connection(client: Dict[str, Any]) -> List[Any]:
    """Low-level: fetch resource list from a connected client."""
    return []


# ---------------------------------------------------------------------------
# fetchCommandsForClient
# ---------------------------------------------------------------------------

_commands_cache: Dict[str, Tuple[float, List[Any]]] = {}


async def fetch_commands_for_client(
    client: Dict[str, Any],
    *,
    force_refresh: bool = False,
) -> List[Any]:
    """
    Fetches the list of slash commands (prompts) available from a connected MCP server.
    Memoized with LRU cache.
    """
    client_key = client.get("name", "")
    if not force_refresh and client_key in _commands_cache:
        cached_at, cached_cmds = _commands_cache[client_key]
        if time.time() - cached_at < _TOOLS_CACHE_TTL_S:
            return cached_cmds

    if client.get("type") != "connected":
        return []

    try:
        commands: List[Any] = await _fetch_commands_from_connection(client)
        _commands_cache[client_key] = (time.time(), commands)
        return commands
    except Exception as e:
        log_mcp_debug(client_key, f"Failed to fetch commands: {error_message(e)}")
        return []


async def _fetch_commands_from_connection(client: Dict[str, Any]) -> List[Any]:
    """Low-level: fetch commands/prompts from a connected client."""
    return []


# ---------------------------------------------------------------------------
# callIdeRpc
# ---------------------------------------------------------------------------

async def call_ide_rpc(
    server_name: str,
    method: str,
    params: Any = None,
) -> Any:
    """
    Calls an IDE RPC method on the MCP server.
    Returns the result, or raises on error.
    """
    conn = await ensure_connected_client(server_name, {})
    if not conn:
        raise RuntimeError(f"MCP server {server_name!r} is not connected")

    log_mcp_debug(server_name, f"IDE RPC call: {method}")
    # In a full port this would use the SDK client to call an RPC method.
    raise NotImplementedError(f"IDE RPC {method!r} not implemented in Python port")


# ---------------------------------------------------------------------------
# reconnectMcpServerImpl
# ---------------------------------------------------------------------------

async def reconnect_mcp_server_impl(
    name: str,
    server_ref: Any,
) -> Dict[str, Any]:
    """
    Forces a reconnection to an MCP server by clearing its cache entry
    and establishing a fresh connection.
    """
    log_mcp_debug(name, "Reconnecting to server")
    await clear_server_cache(name, server_ref)
    clear_mcp_auth_cache()
    clear_keychain_cache()
    return await connect_to_server(name, server_ref)


# ---------------------------------------------------------------------------
# processBatched
# ---------------------------------------------------------------------------

async def _process_batched(
    items: List[Any],
    fn: Callable[[Any], Any],
    concurrency: int = 5,
) -> List[Any]:
    """
    Processes items in parallel with a concurrency limit.
    Mirrors pMap from p-map package.
    """
    results: List[Any] = []
    semaphore = asyncio.Semaphore(concurrency)

    async def process_one(item: Any) -> Any:
        async with semaphore:
            return await fn(item)

    tasks = [asyncio.ensure_future(process_one(item)) for item in items]
    for task in asyncio.as_completed(tasks):
        try:
            result = await task
            results.append(result)
        except Exception as e:
            results.append({"error": error_message(e)})

    return results


# ---------------------------------------------------------------------------
# getMcpToolsCommandsAndResources
# ---------------------------------------------------------------------------

async def get_mcp_tools_commands_and_resources(
    app_state: Any,
    *,
    include_resources: bool = True,
    include_commands: bool = True,
) -> Dict[str, Any]:
    """
    Batch-fetches tools, commands, and resources from all connected MCP servers.

    Returns a dict with keys:
      - 'tools': list of Tool-like objects
      - 'commands': list of command objects
      - 'resources': list of resource objects
      - 'connections': list of MCPServerConnection objects
    """
    all_configs = get_all_mcp_configs(app_state)
    active_configs = [c for c in all_configs if not is_mcp_server_disabled(c)]

    local_configs = [c for c in active_configs if _is_local_mcp_server(c)]
    remote_configs = [c for c in active_configs if not _is_local_mcp_server(c)]

    log_for_debugging(
        f"Connecting to {len(local_configs)} local + {len(remote_configs)} remote MCP servers"
    )

    # Filter servers that are known to need auth (skip with 15-min TTL)
    needs_auth_servers: Set[str] = set()
    for config in remote_configs:
        sname = (
            config.get("name") if isinstance(config, dict)
            else getattr(config, "name", "unknown")
        )
        if await is_mcp_auth_cached(sname):
            needs_auth_servers.add(sname)

    # Connect to all servers
    local_connections = await _process_batched(
        local_configs,
        lambda c: connect_to_server(
            c.get("name") if isinstance(c, dict) else getattr(c, "name", "?"),
            c,
        ),
        concurrency=get_mcp_server_connection_batch_size(),
    )
    remote_connections = await _process_batched(
        remote_configs,
        lambda c: connect_to_server(
            c.get("name") if isinstance(c, dict) else getattr(c, "name", "?"),
            c,
        ),
        concurrency=_get_remote_mcp_server_connection_batch_size(),
    )

    all_connections = local_connections + remote_connections
    connected = [c for c in all_connections if isinstance(c, dict) and c.get("type") == "connected"]

    # Fetch tools/commands/resources from all connected servers
    all_tools: List[Any] = []
    all_commands: List[Any] = []
    all_resources: List[Any] = []

    for conn in connected:
        server_name = conn.get("name", "?")
        try:
            tools = await fetch_tools_for_client(conn)
            all_tools.extend(tools)
        except Exception as e:
            log_mcp_debug(server_name, f"Failed to fetch tools: {error_message(e)}")

        if include_commands:
            try:
                commands = await fetch_commands_for_client(conn)
                all_commands.extend(commands)
            except Exception as e:
                log_mcp_debug(server_name, f"Failed to fetch commands: {error_message(e)}")

        if include_resources:
            try:
                resources = await fetch_resources_for_client(conn)
                all_resources.extend(resources)
            except Exception as e:
                log_mcp_debug(server_name, f"Failed to fetch resources: {error_message(e)}")

    return {
        "tools": all_tools,
        "commands": all_commands,
        "resources": all_resources,
        "connections": all_connections,
    }


# ---------------------------------------------------------------------------
# prefetchAllMcpResources
# ---------------------------------------------------------------------------

def prefetch_all_mcp_resources(
    connections: List[Dict[str, Any]],
) -> None:
    """
    Fire-and-forget prefetch of resources from all connected MCP servers.
    """
    async def _do_prefetch() -> None:
        for conn in connections:
            if conn.get("type") == "connected":
                try:
                    await fetch_resources_for_client(conn, force_refresh=True)
                except Exception:
                    pass

    asyncio.ensure_future(_do_prefetch())


# ---------------------------------------------------------------------------
# MCPResultType / TransformedMCPResult
# ---------------------------------------------------------------------------

MCPResultType = Literal["toolResult", "structuredContent", "contentArray"]


@dataclass
class TransformedMCPResult:
    result_type: MCPResultType
    content: Any
    is_error: bool = False
    meta: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# transformResultContent (individual content block → ContentBlockParam)
# ---------------------------------------------------------------------------

async def transform_result_content(
    content_block: Any,
    server_name: str,
    source_description: str = "",
) -> List[Any]:
    """
    Transforms a single MCP content block into ContentBlockParam(s) for the Anthropic API.

    Handles: text, image (base64), resource, audio, binary blobs.
    Large content is persisted to disk and replaced with a reference message.
    Images are optionally resized/downsampled.
    """
    if isinstance(content_block, str):
        return [{"type": "text", "text": content_block}]

    if not isinstance(content_block, dict):
        try:
            return [{"type": "text", "text": str(content_block)}]
        except Exception:
            return []

    block_type = content_block.get("type", "text")

    if block_type == "text":
        text = content_block.get("text") or ""
        text = recursively_sanitize_unicode(text)
        return [{"type": "text", "text": text}]

    elif block_type == "image":
        mime_type = content_block.get("mimeType", "")
        data_b64 = content_block.get("data", "")

        if mime_type not in IMAGE_MIME_TYPES:
            # Save binary blob to disk and return reference
            try:
                data_bytes = base64.b64decode(data_b64) if data_b64 else b""
                save_path = await persist_binary_content(data_bytes, mime_type)
                format_desc = get_format_description(mime_type)
                return [{
                    "type": "text",
                    "text": get_binary_blob_saved_message(save_path, format_desc),
                }]
            except Exception as e:
                return [{"type": "text", "text": f"[Binary content ({mime_type}) could not be processed: {error_message(e)}]"}]

        # Resize/downsample large images
        try:
            data_bytes = base64.b64decode(data_b64) if data_b64 else b""
            data_bytes = await maybe_resize_and_downsample_image_buffer(data_bytes, mime_type)
            data_b64 = base64.b64encode(data_bytes).decode()
        except Exception:
            pass

        return [{
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": data_b64,
            },
        }]

    elif block_type == "resource":
        resource = content_block.get("resource") or {}
        uri = resource.get("uri", "")
        resource_type = resource.get("mimeType", "text/plain")

        if resource.get("text") is not None:
            text = resource["text"]
            return [{"type": "text", "text": f"[Resource: {uri}]\n{text}"}]
        elif resource.get("blob") is not None:
            blob_b64 = resource["blob"]
            mime_type = resource_type or "application/octet-stream"
            if mime_type in IMAGE_MIME_TYPES:
                return [{
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": blob_b64,
                    },
                }]
            else:
                return [{"type": "text", "text": f"[Binary resource: {uri} ({mime_type})]"}]
        else:
            return [{"type": "text", "text": f"[Resource: {uri}]"}]

    elif block_type == "audio":
        # Audio is not currently supported in the Anthropic API; save to file
        data_b64 = content_block.get("data", "")
        mime_type = content_block.get("mimeType", "audio/wav")
        try:
            data_bytes = base64.b64decode(data_b64) if data_b64 else b""
            save_path = await persist_binary_content(data_bytes, mime_type)
            format_desc = get_format_description(mime_type)
            return [{
                "type": "text",
                "text": get_binary_blob_saved_message(save_path, format_desc),
            }]
        except Exception as e:
            return [{"type": "text", "text": f"[Audio content could not be processed: {error_message(e)}]"}]

    else:
        # Unknown content type
        log_mcp_debug(server_name, f"Unknown content block type: {block_type!r}")
        try:
            return [{"type": "text", "text": json_stringify(content_block)}]
        except Exception:
            return []


# ---------------------------------------------------------------------------
# transformMCPResult
# ---------------------------------------------------------------------------

async def transform_mcp_result(
    result: Any,
    server_name: str,
) -> TransformedMCPResult:
    """
    Transforms an MCP tool call result into a TransformedMCPResult for the Anthropic API.

    Handles:
    - structuredContent (non-list JSON)
    - toolResult (list of content blocks)
    - large output persistence
    - truncation
    """
    is_error = bool(getattr(result, "isError", False) or (result.get("isError") if isinstance(result, dict) else False))
    meta: Optional[Dict[str, Any]] = (
        result.get("_meta") if isinstance(result, dict)
        else getattr(result, "_meta", None)
    )

    content = (
        result.get("content") if isinstance(result, dict)
        else getattr(result, "content", None)
    )
    structured_content = (
        result.get("structuredContent") if isinstance(result, dict)
        else getattr(result, "structuredContent", None)
    )

    # Prefer structuredContent (JSON-serializable) for non-error results
    if structured_content is not None and not is_error:
        return TransformedMCPResult(
            result_type="structuredContent",
            content=structured_content,
            is_error=False,
            meta=meta,
        )

    # Handle content list
    if content is None:
        content = []
    if not isinstance(content, list):
        content = [content]

    # Check if content needs truncation
    if mcp_content_needs_truncation(content):
        try:
            saved_path = await persist_tool_result(content)
            instructions = get_large_output_instructions(saved_path)
            truncated = truncate_mcp_content_if_needed(content)
            content = truncated + [{"type": "text", "text": instructions}]
        except Exception as e:
            if not is_persist_error(e):
                log_mcp_debug(server_name, f"Failed to persist large output: {error_message(e)}")

    # Transform each content block
    transformed_blocks: List[Any] = []
    for block in content:
        blocks = await transform_result_content(block, server_name, "tool result")
        transformed_blocks.extend(blocks)

    return TransformedMCPResult(
        result_type="toolResult",
        content=transformed_blocks,
        is_error=is_error,
        meta=meta,
    )


# ---------------------------------------------------------------------------
# _contentContainsImages
# ---------------------------------------------------------------------------

def _content_contains_images(content: Any) -> bool:
    """Check whether any content block is an image."""
    if not isinstance(content, list):
        return False
    return any(
        (b.get("type") == "image" if isinstance(b, dict) else False)
        for b in content
    )


# ---------------------------------------------------------------------------
# processMCPResult
# ---------------------------------------------------------------------------

async def process_mcp_result(
    result: Any,
    server_name: str,
    tool_name: str,
    *,
    on_progress: Optional[Callable[[Any], None]] = None,
) -> Dict[str, Any]:
    """
    Top-level processing of an MCP tool call result.

    Transforms the raw MCP result into a format suitable for the Anthropic API,
    handling errors, large output, and content type conversions.
    """
    transformed = await transform_mcp_result(result, server_name)

    if transformed.is_error:
        # Return as tool_result with is_error flag
        return {
            "type": "tool_result",
            "content": transformed.content,
            "is_error": True,
            "_meta": transformed.meta,
        }

    if transformed.result_type == "structuredContent":
        return {
            "type": "structured_content",
            "content": transformed.content,
        }

    return {
        "type": "tool_result",
        "content": transformed.content,
        "is_error": False,
        "_meta": transformed.meta,
    }


# ---------------------------------------------------------------------------
# callMCPTool (internal)
# ---------------------------------------------------------------------------

async def _call_mcp_tool(
    *,
    client: Dict[str, Any],
    tool_name: str,
    tool_input: Any,
    timeout_ms: Optional[int] = None,
    on_progress: Optional[Callable[[Any], None]] = None,
    abort_signal: Optional[asyncio.Event] = None,
) -> Any:
    """
    Calls an MCP tool on a connected client. Returns the raw MCP result.

    Raises McpToolCallError if the tool returns isError: true.
    Raises McpAuthError if a 401 is encountered.
    Raises McpSessionExpiredError if session has expired (-32001).
    """
    server_name = client.get("name", "unknown")
    effective_timeout = timeout_ms if timeout_ms is not None else get_mcp_tool_timeout_ms()

    log_mcp_debug(
        server_name,
        f"Calling tool {tool_name!r} (timeout={effective_timeout}ms)",
    )

    # --- Check if client is connected ---
    if client.get("type") != "connected":
        conn = await ensure_connected_client(server_name, client.get("config", {}))
        if not conn:
            raise RuntimeError(f"MCP server {server_name!r} is not connected")
        client = conn

    # --- Sanitize input ---
    sanitized_input = recursively_sanitize_unicode(tool_input)

    # --- Invoke the tool (stub: would use real SDK client) ---
    # In a full port this would call client.callTool() via the MCP SDK.
    # Here we raise NotImplementedError to indicate the SDK is needed.
    raise NotImplementedError(
        f"MCP tool call '{tool_name}' requires the MCP SDK client. "
        "This Python port provides the wiring/auth/caching infrastructure; "
        "actual transport-level dispatch needs the mcp Python package."
    )


# ---------------------------------------------------------------------------
# callMCPToolWithUrlElicitationRetry
# ---------------------------------------------------------------------------

async def call_mcp_tool_with_url_elicitation_retry(
    *,
    client: Dict[str, Any],
    tool_name: str,
    tool_input: Any,
    timeout_ms: Optional[int] = None,
    on_progress: Optional[Callable[[Any], None]] = None,
    abort_signal: Optional[asyncio.Event] = None,
    elicitation_state: Optional[Any] = None,
) -> Any:
    """
    Call an MCP tool, handling UrlElicitationRequiredError (-32042) by
    displaying the URL elicitation UI and retrying once approved.

    This wraps _call_mcp_tool with elicitation retry logic.
    """
    try:
        return await _call_mcp_tool(
            client=client,
            tool_name=tool_name,
            tool_input=tool_input,
            timeout_ms=timeout_ms,
            on_progress=on_progress,
            abort_signal=abort_signal,
        )
    except Exception as e:
        msg = error_message(e)
        # Check for URL elicitation error code -32042
        if "-32042" in msg or "UrlElicitationRequired" in msg:
            log_mcp_debug(
                client.get("name", "?"),
                f"URL elicitation required for tool {tool_name!r}",
            )
            # Run elicitation hooks and retry
            try:
                await run_elicitation_hooks(
                    client.get("name", "?"),
                    tool_name,
                    e,
                    elicitation_state,
                )
                result = await _call_mcp_tool(
                    client=client,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    timeout_ms=timeout_ms,
                    on_progress=on_progress,
                    abort_signal=abort_signal,
                )
                await run_elicitation_result_hooks(
                    client.get("name", "?"),
                    tool_name,
                    result,
                    elicitation_state,
                )
                return result
            except Exception as retry_err:
                raise retry_err
        raise


# ---------------------------------------------------------------------------
# setupSdkMcpClients
# ---------------------------------------------------------------------------

async def setup_sdk_mcp_clients(
    sdk_configs: List[Any],
) -> List[Dict[str, Any]]:
    """
    Wires in-process SDK MCP server connections.

    SDK servers (type='sdk') run entirely in-process via McpSdkServerConfig;
    they are not real subprocess or HTTP transports.

    Returns a list of MCPServerConnection objects.
    """
    connections: List[Dict[str, Any]] = []

    for config in sdk_configs:
        name = (
            config.get("name") if isinstance(config, dict)
            else getattr(config, "name", "unknown")
        )
        log_mcp_debug(name, "Setting up in-process SDK MCP server")
        try:
            conn: Dict[str, Any] = {
                "type": "connected",
                "name": name,
                "config": config,
                "transport_type": "sdk",
                "connected_at": int(time.time() * 1000),
            }
            connections.append(conn)
            log_mcp_debug(name, "In-process SDK MCP server ready")
        except Exception as e:
            log_mcp_debug(name, f"Failed to set up SDK server: {error_message(e)}")
            connections.append({
                "type": "failed",
                "name": name,
                "config": config,
                "error": error_message(e),
            })

    return connections


# ---------------------------------------------------------------------------
# classify MCP tool for collapse
# ---------------------------------------------------------------------------

def classify_mcp_tool_for_collapse(tool: Any) -> str:
    """
    Classifies an MCP tool call for UI collapse behavior.
    Returns 'collapsible', 'expanded', or 'auto'.
    """
    tool_name = (
        tool.get("name") if isinstance(tool, dict)
        else getattr(tool, "name", "")
    ) or ""

    # Known "verbose" tool patterns that should collapse
    collapse_patterns = ["list", "search", "get", "fetch", "read", "describe"]
    name_lower = tool_name.lower()
    for pattern in collapse_patterns:
        if name_lower.startswith(pattern) or ("__" + pattern) in name_lower:
            return "collapsible"

    return "auto"
