"""
MCP auth module. Ported from services/mcp/auth.ts

Provides OAuth 2.0 / PKCE authentication for MCP servers:
- ClaudeAuthProvider: OAuthClientProvider implementation
- performMCPOAuthFlow: full OAuth code+PKCE flow with local callback server
- revokeServerTokens: RFC 7009 token revocation
- token storage helpers via SecureStorage
- XAA (Cross-App Access) silent token refresh
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Tuple,
    Union,
    runtime_checkable,
)

# ---------------------------------------------------------------------------
# Conditional / optional imports
# ---------------------------------------------------------------------------
try:
    import aiohttp  # type: ignore
    _HAS_AIOHTTP = True
except ImportError:
    _HAS_AIOHTTP = False

try:
    from http.server import BaseHTTPRequestHandler, HTTPServer
    _HAS_HTTP_SERVER = True
except ImportError:
    _HAS_HTTP_SERVER = False

if TYPE_CHECKING:
    pass  # keep TYPE_CHECKING block for future typed imports

# ---------------------------------------------------------------------------
# Internal imports (soft – guard with try/except for missing modules)
# ---------------------------------------------------------------------------
try:
    from claude_code.utils.log import log_mcp_debug, log_mcp_error  # type: ignore
except ImportError:
    def log_mcp_debug(server_name: str, msg: str) -> None:  # type: ignore
        logging.debug("[MCP:%s] %s", server_name, msg)

    def log_mcp_error(server_name: str, msg: Any) -> None:  # type: ignore
        logging.error("[MCP:%s] %s", server_name, msg)

try:
    from claude_code.utils.errors import error_message  # type: ignore
except ImportError:
    def error_message(e: BaseException) -> str:  # type: ignore
        return str(e)

try:
    from claude_code.utils.env_utils import get_claude_config_home_dir  # type: ignore
except ImportError:
    def get_claude_config_home_dir() -> str:  # type: ignore
        return os.path.expanduser("~/.config/claude")

try:
    from claude_code.utils.secure_storage import get_secure_storage  # type: ignore
    from claude_code.utils.secure_storage.types import SecureStorageData  # type: ignore
except ImportError:
    def get_secure_storage():  # type: ignore
        return _FallbackSecureStorage()

    SecureStorageData = dict  # type: ignore

try:
    from claude_code.utils.lockfile import acquire_lock, release_lock  # type: ignore
except ImportError:
    async def acquire_lock(path: str) -> bool:  # type: ignore
        return True

    async def release_lock(path: str) -> None:  # type: ignore
        pass

try:
    from claude_code.services.analytics import log_event  # type: ignore
except ImportError:
    def log_event(name: str, meta: dict | None = None) -> None:  # type: ignore
        pass

try:
    from claude_code.utils.platform import get_platform  # type: ignore
except ImportError:
    def get_platform() -> str:  # type: ignore
        return sys.platform

try:
    from claude_code.utils.json_utils import json_parse, json_stringify  # type: ignore
except ImportError:
    def json_parse(s: str) -> Any:  # type: ignore
        return json.loads(s)

    def json_stringify(v: Any) -> str:  # type: ignore
        return json.dumps(v)

try:
    from claude_code.utils.sleep import sleep  # type: ignore
except ImportError:
    async def sleep(ms: int) -> None:  # type: ignore
        await asyncio.sleep(ms / 1000.0)

try:
    from claude_code.utils.browser import open_browser  # type: ignore
except ImportError:
    async def open_browser(url: str) -> None:  # type: ignore
        import webbrowser
        webbrowser.open(url)

try:
    from claude_code.services.mcp.oauth_port import build_redirect_uri, find_available_port  # type: ignore
except ImportError:
    def build_redirect_uri(port: int = 54321) -> str:  # type: ignore
        return f"http://127.0.0.1:{port}/callback"

    async def find_available_port() -> int:  # type: ignore
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

try:
    from claude_code.services.mcp.types import McpSSEServerConfig, McpHTTPServerConfig  # type: ignore
except ImportError:
    McpSSEServerConfig = dict  # type: ignore
    McpHTTPServerConfig = dict  # type: ignore

try:
    from claude_code.services.mcp.utils import get_logging_safe_mcp_base_url  # type: ignore
except ImportError:
    def get_logging_safe_mcp_base_url(config: Any) -> Optional[str]:  # type: ignore
        url = getattr(config, "url", None) or (config.get("url") if isinstance(config, dict) else None)
        if not url:
            return None
        try:
            parsed = urllib.parse.urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        except Exception:
            return None

try:
    from claude_code.services.mcp.xaa import perform_cross_app_access, XaaTokenExchangeError  # type: ignore
except ImportError:
    async def perform_cross_app_access(*args: Any, **kwargs: Any) -> Any:  # type: ignore
        raise NotImplementedError("XAA not available")

    class XaaTokenExchangeError(Exception):  # type: ignore
        should_clear_id_token: bool = False

try:
    from claude_code.services.mcp.xaa_idp_login import (  # type: ignore
        acquire_idp_id_token,
        clear_idp_id_token,
        discover_oidc,
        get_cached_idp_id_token,
        get_idp_client_secret,
        get_xaa_idp_settings,
        is_xaa_enabled,
        get_xaa_idp_settings,
    )
except ImportError:
    def is_xaa_enabled() -> bool:  # type: ignore
        return os.environ.get("CLAUDE_CODE_ENABLE_XAA", "") == "1"

    def get_xaa_idp_settings() -> Optional[Any]:  # type: ignore
        return None

    def get_cached_idp_id_token(issuer: str) -> Optional[str]:  # type: ignore
        return None

    def clear_idp_id_token(issuer: str) -> None:  # type: ignore
        pass

    def get_idp_client_secret(issuer: str) -> Optional[str]:  # type: ignore
        return None

    async def acquire_idp_id_token(**kwargs: Any) -> str:  # type: ignore
        raise NotImplementedError("IdP login not available")

    async def discover_oidc(issuer: str) -> Any:  # type: ignore
        raise NotImplementedError("OIDC discovery not available")

try:
    from claude_code.utils.secure_storage.mac_os_keychain_helpers import clear_keychain_cache  # type: ignore
except ImportError:
    def clear_keychain_cache() -> None:  # type: ignore
        pass

try:
    from claude_code.constants.oauth import MCP_CLIENT_METADATA_URL  # type: ignore
except ImportError:
    MCP_CLIENT_METADATA_URL = "https://claude.ai/oauth/clients/mcp"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AUTH_REQUEST_TIMEOUT_MS = 30_000
MAX_LOCK_RETRIES = 5

SENSITIVE_OAUTH_PARAMS = [
    "state",
    "nonce",
    "code_challenge",
    "code_verifier",
    "code",
]

NONSTANDARD_INVALID_GRANT_ALIASES = frozenset([
    "invalid_refresh_token",
    "expired_refresh_token",
    "token_expired",
])

# ---------------------------------------------------------------------------
# Lightweight fallback SecureStorage
# ---------------------------------------------------------------------------

class _FallbackSecureStorage:
    """In-memory secure storage fallback when the real implementation is unavailable."""
    _data: Dict[str, Any] = {}

    def read(self) -> Optional[Dict[str, Any]]:
        return self._data or None

    async def read_async(self) -> Optional[Dict[str, Any]]:
        return self._data or None

    def update(self, new_data: Dict[str, Any]) -> None:
        self._data = new_data


# ---------------------------------------------------------------------------
# Type literals / failure reason strings
# ---------------------------------------------------------------------------

MCPRefreshFailureReason = str  # 'metadata_discovery_failed' | 'no_client_info' | ...
MCPOAuthFlowErrorReason = str  # 'cancelled' | 'timeout' | 'provider_denied' | ...
XaaFailureStage = str  # 'idp_login' | 'discovery' | 'token_exchange' | 'jwt_bearer'


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class AuthenticationCancelledError(Exception):
    """Raised when the user cancels OAuth authentication."""
    def __init__(self) -> None:
        super().__init__("Authentication was cancelled")


class OAuthError(Exception):
    """Base OAuth error (mirrors SDK OAuthError)."""
    def __init__(self, message: str, error_code: str = "unknown") -> None:
        super().__init__(message)
        self.error_code = error_code


class InvalidGrantError(OAuthError):
    """RFC 6749 invalid_grant error."""
    def __init__(self, message: str = "invalid_grant") -> None:
        super().__init__(message, "invalid_grant")


class ServerError(OAuthError):
    """OAuth server error."""
    def __init__(self, message: str = "server_error") -> None:
        super().__init__(message, "server_error")


class TemporarilyUnavailableError(OAuthError):
    def __init__(self, message: str = "temporarily_unavailable") -> None:
        super().__init__(message, "temporarily_unavailable")


class TooManyRequestsError(OAuthError):
    def __init__(self, message: str = "too_many_requests") -> None:
        super().__init__(message, "too_many_requests")


# ---------------------------------------------------------------------------
# Data types (mirrors SDK / TS interfaces)
# ---------------------------------------------------------------------------

@dataclass
class OAuthTokens:
    access_token: str
    token_type: str = "Bearer"
    refresh_token: Optional[str] = None
    expires_in: Optional[float] = None
    scope: Optional[str] = None


@dataclass
class OAuthClientMetadata:
    client_name: str
    redirect_uris: List[str]
    grant_types: List[str]
    response_types: List[str]
    token_endpoint_auth_method: str
    scope: Optional[str] = None


@dataclass
class OAuthClientInformation:
    client_id: str
    client_secret: Optional[str] = None


@dataclass
class OAuthClientInformationFull:
    client_id: str
    client_secret: Optional[str] = None


@dataclass
class AuthorizationServerMetadata:
    """Subset of RFC 8414 Authorization Server Metadata."""
    issuer: Optional[str] = None
    authorization_endpoint: Optional[str] = None
    token_endpoint: Optional[str] = None
    revocation_endpoint: Optional[str] = None
    registration_endpoint: Optional[str] = None
    scopes_supported: Optional[List[str]] = None
    response_types_supported: Optional[List[str]] = None
    grant_types_supported: Optional[List[str]] = None
    token_endpoint_auth_methods_supported: Optional[List[str]] = None
    revocation_endpoint_auth_methods_supported: Optional[List[str]] = None
    client_id_metadata_document_supported: Optional[bool] = None
    # Non-standard but used by some providers
    scope: Optional[str] = None
    default_scope: Optional[str] = None
    # Extra raw fields
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OAuthDiscoveryState:
    authorization_server_url: Optional[str] = None
    resource_metadata_url: Optional[str] = None


# ---------------------------------------------------------------------------
# OAuth request / response schemas (minimal Zod-equivalent parse helpers)
# ---------------------------------------------------------------------------

def _parse_oauth_tokens(data: Dict[str, Any]) -> Optional[OAuthTokens]:
    """Parse an OAuth token response dict into OAuthTokens, returning None on failure."""
    if not isinstance(data, dict):
        return None
    if "access_token" not in data:
        return None
    return OAuthTokens(
        access_token=data["access_token"],
        token_type=data.get("token_type", "Bearer"),
        refresh_token=data.get("refresh_token"),
        expires_in=data.get("expires_in"),
        scope=data.get("scope"),
    )


def _is_oauth_error_response(data: Dict[str, Any]) -> bool:
    """Return True if data looks like an OAuth error response."""
    return isinstance(data, dict) and "error" in data and isinstance(data["error"], str)


def _parse_auth_server_metadata(data: Dict[str, Any]) -> AuthorizationServerMetadata:
    """Parse a raw JSON dict into AuthorizationServerMetadata."""
    known = {
        "issuer", "authorization_endpoint", "token_endpoint",
        "revocation_endpoint", "registration_endpoint", "scopes_supported",
        "response_types_supported", "grant_types_supported",
        "token_endpoint_auth_methods_supported",
        "revocation_endpoint_auth_methods_supported",
        "client_id_metadata_document_supported",
        "scope", "default_scope",
    }
    extra = {k: v for k, v in data.items() if k not in known}
    return AuthorizationServerMetadata(
        issuer=data.get("issuer"),
        authorization_endpoint=data.get("authorization_endpoint"),
        token_endpoint=data.get("token_endpoint"),
        revocation_endpoint=data.get("revocation_endpoint"),
        registration_endpoint=data.get("registration_endpoint"),
        scopes_supported=data.get("scopes_supported"),
        response_types_supported=data.get("response_types_supported"),
        grant_types_supported=data.get("grant_types_supported"),
        token_endpoint_auth_methods_supported=data.get(
            "token_endpoint_auth_methods_supported"
        ),
        revocation_endpoint_auth_methods_supported=data.get(
            "revocation_endpoint_auth_methods_supported"
        ),
        client_id_metadata_document_supported=data.get(
            "client_id_metadata_document_supported"
        ),
        scope=data.get("scope"),
        default_scope=data.get("default_scope"),
        extra=extra,
    )


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def redact_sensitive_url_params(url: str) -> str:
    """Redact sensitive OAuth query parameters from a URL for safe logging."""
    try:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        for param in SENSITIVE_OAUTH_PARAMS:
            if param in qs:
                qs[param] = ["[REDACTED]"]
        new_query = urllib.parse.urlencode(qs, doseq=True)
        return urllib.parse.urlunparse(parsed._replace(query=new_query))
    except Exception:
        return url


# ---------------------------------------------------------------------------
# normalizeOAuthErrorBody equivalent
# ---------------------------------------------------------------------------

async def normalize_oauth_error_body(
    status: int,
    headers: Dict[str, str],
    body_text: str,
) -> Tuple[int, str]:
    """
    If a 2xx POST response actually contains an OAuth error JSON, rewrite
    the status to 400 so callers handle it as an error.

    Returns (new_status, body_text).

    Mirrors TypeScript normalizeOAuthErrorBody.
    """
    if status < 200 or status >= 300:
        return status, body_text

    try:
        parsed = json_parse(body_text)
    except Exception:
        return status, body_text

    # If it parses as valid tokens, leave it alone
    if _parse_oauth_tokens(parsed) is not None:
        return status, body_text

    # If it looks like an OAuth error response, rewrite to 400
    if _is_oauth_error_response(parsed):
        error_code = parsed["error"]
        if error_code in NONSTANDARD_INVALID_GRANT_ALIASES:
            parsed = {
                "error": "invalid_grant",
                "error_description": parsed.get(
                    "error_description",
                    f"Server returned non-standard error code: {error_code}",
                ),
            }
        return 400, json_stringify(parsed)

    return status, body_text


# ---------------------------------------------------------------------------
# Auth fetch helpers
# ---------------------------------------------------------------------------

async def _do_fetch(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[str] = None,
    timeout_s: float = AUTH_REQUEST_TIMEOUT_MS / 1000.0,
) -> Tuple[int, Dict[str, str], str]:
    """
    Low-level HTTP request helper. Returns (status, response_headers, body_text).
    Uses aiohttp when available, falls back to urllib.
    """
    if _HAS_AIOHTTP:
        import aiohttp as aio
        timeout = aio.ClientTimeout(total=timeout_s)
        async with aio.ClientSession(timeout=timeout) as session:
            async with session.request(
                method,
                url,
                headers=headers or {},
                data=body,
            ) as resp:
                body_text = await resp.text()
                resp_headers = dict(resp.headers)
                return resp.status, resp_headers, body_text
    else:
        import urllib.request as ureq
        req = ureq.Request(url, method=method)
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        if body:
            req.data = body.encode()
        try:
            with ureq.urlopen(req, timeout=timeout_s) as resp:
                body_bytes = resp.read()
                resp_headers = {k: v for k, v in resp.getheaders()}
                return resp.status, resp_headers, body_bytes.decode()
        except Exception as e:
            # Wrap HTTP errors
            if hasattr(e, "code"):
                body_bytes = e.read() if hasattr(e, "read") else b""
                return e.code, {}, body_bytes.decode()
            raise


# ---------------------------------------------------------------------------
# Auth server metadata discovery
# ---------------------------------------------------------------------------

async def fetch_auth_server_metadata(
    server_name: str,
    server_url: str,
    configured_metadata_url: Optional[str] = None,
    resource_metadata_url: Optional[str] = None,
) -> Optional[AuthorizationServerMetadata]:
    """
    Fetches OAuth authorization server metadata.

    Discovery order when no configured URL:
    1. RFC 9728: probe /.well-known/oauth-protected-resource on the MCP server,
       read authorization_servers[0], then RFC 8414 against that URL.
    2. Fallback: RFC 8414 directly against the MCP server URL (path-aware).

    Note: configuredMetadataUrl is user-controlled via .mcp.json.
    The HTTPS requirement is defense-in-depth beyond schema validation.
    """
    if configured_metadata_url:
        if not configured_metadata_url.startswith("https://"):
            raise ValueError(
                f"authServerMetadataUrl must use https:// "
                f"(got: {configured_metadata_url})"
            )
        status, _, body = await _do_fetch(
            configured_metadata_url,
            headers={"Accept": "application/json"},
        )
        if 200 <= status < 300:
            return _parse_auth_server_metadata(json_parse(body))
        raise RuntimeError(
            f"HTTP {status} fetching configured auth server metadata "
            f"from {configured_metadata_url}"
        )

    # Attempt RFC 9728 discovery
    try:
        metadata = await _discover_oauth_server_info(
            server_name, server_url, resource_metadata_url=resource_metadata_url
        )
        if metadata is not None:
            return metadata
    except Exception as err:
        log_mcp_debug(
            server_name,
            f"RFC 9728 discovery failed, falling back: {error_message(err)}",
        )

    # Fallback: path-aware RFC 8414 probe
    parsed = urllib.parse.urlparse(server_url)
    if parsed.path and parsed.path != "/":
        return await _discover_authorization_server_metadata(server_url)

    return None


async def _discover_oauth_server_info(
    server_name: str,
    server_url: str,
    resource_metadata_url: Optional[str] = None,
) -> Optional[AuthorizationServerMetadata]:
    """
    Try RFC 9728 (oauth-protected-resource) discovery, then RFC 8414.
    """
    base = server_url.rstrip("/")
    # Try /.well-known/oauth-protected-resource
    probe_url = urllib.parse.urljoin(base + "/", ".well-known/oauth-protected-resource")
    try:
        status, _, body = await _do_fetch(
            probe_url, headers={"Accept": "application/json"}
        )
        if 200 <= status < 300:
            data = json_parse(body)
            as_servers = data.get("authorization_servers", [])
            if as_servers:
                as_url = as_servers[0]
                return await _discover_authorization_server_metadata(as_url)
    except Exception:
        pass

    # RFC 8414 direct
    return await _discover_authorization_server_metadata(server_url)


async def _discover_authorization_server_metadata(
    url: str,
) -> Optional[AuthorizationServerMetadata]:
    """Probe RFC 8414 /.well-known/oauth-authorization-server endpoints."""
    parsed = urllib.parse.urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")

    candidates = [
        f"{base}/.well-known/oauth-authorization-server{path}",
        f"{base}/.well-known/oauth-authorization-server",
        f"{base}/.well-known/openid-configuration",
        f"{url.rstrip('/')}/.well-known/oauth-authorization-server",
    ]

    for probe_url in candidates:
        try:
            status, _, body = await _do_fetch(
                probe_url, headers={"Accept": "application/json"}
            )
            if 200 <= status < 300:
                return _parse_auth_server_metadata(json_parse(body))
        except Exception:
            continue

    return None


# ---------------------------------------------------------------------------
# Server key helpers
# ---------------------------------------------------------------------------

def get_server_key(
    server_name: str,
    server_config: Any,
) -> str:
    """
    Generates a unique key for server credentials based on both name and config hash.
    Prevents credential reuse across different servers with the same name.
    """
    if isinstance(server_config, dict):
        config_type = server_config.get("type", "")
        config_url = server_config.get("url", "")
        config_headers = server_config.get("headers") or {}
    else:
        config_type = getattr(server_config, "type", "") or ""
        config_url = getattr(server_config, "url", "") or ""
        config_headers = getattr(server_config, "headers", None) or {}

    config_json = json_stringify({
        "type": config_type,
        "url": config_url,
        "headers": config_headers,
    })
    hash_hex = hashlib.sha256(config_json.encode()).hexdigest()[:16]
    return f"{server_name}|{hash_hex}"


def has_mcp_discovery_but_no_token(
    server_name: str,
    server_config: Any,
) -> bool:
    """
    True when we have probed this server before (OAuth discovery state is
    stored) but hold no credentials to try. A connection attempt in this
    state is guaranteed to 401.

    XAA servers can silently re-auth via cached id_token even without an
    access/refresh token — skip so auto-auth branch is reachable.
    """
    oauth_config = (
        server_config.get("oauth") if isinstance(server_config, dict)
        else getattr(server_config, "oauth", None)
    )
    if is_xaa_enabled() and oauth_config and (
        oauth_config.get("xaa") if isinstance(oauth_config, dict)
        else getattr(oauth_config, "xaa", False)
    ):
        return False

    server_key = get_server_key(server_name, server_config)
    entry = (get_secure_storage().read() or {}).get("mcpOAuth", {}).get(server_key)
    return (
        entry is not None
        and not entry.get("accessToken")
        and not entry.get("refreshToken")
    )


# ---------------------------------------------------------------------------
# Token revocation (RFC 7009)
# ---------------------------------------------------------------------------

async def _revoke_token(
    *,
    server_name: str,
    endpoint: str,
    token: str,
    token_type_hint: str,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    access_token: Optional[str] = None,
    auth_method: str = "client_secret_basic",
) -> None:
    """
    Revokes a single OAuth token.

    Per RFC 7009, public clients include client_id in the request body
    (not via Authorization header). We also do a Bearer-auth fallback for
    non-compliant servers.
    """
    params: Dict[str, str] = {
        "token": token,
        "token_type_hint": token_type_hint,
    }
    headers: Dict[str, str] = {"Content-Type": "application/x-www-form-urlencoded"}

    # RFC 7009 §2.1 requires client auth per RFC 6749 §2.3
    if client_id and client_secret:
        if auth_method == "client_secret_post":
            params["client_id"] = client_id
            params["client_secret"] = client_secret
        else:
            import base64
            basic = base64.b64encode(
                f"{urllib.parse.quote(client_id)}:{urllib.parse.quote(client_secret)}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {basic}"
    elif client_id:
        params["client_id"] = client_id
    else:
        log_mcp_debug(
            server_name,
            f"No client_id available for {token_type_hint} revocation - server may reject",
        )

    body = urllib.parse.urlencode(params)
    status, _, _ = await _do_fetch(endpoint, method="POST", headers=headers, body=body)

    if status == 200:
        log_mcp_debug(server_name, f"Successfully revoked {token_type_hint}")
        return

    if status == 401 and access_token:
        # Fallback: Bearer auth for non-RFC-7009-compliant servers
        log_mcp_debug(
            server_name,
            f"Got 401, retrying {token_type_hint} revocation with Bearer auth",
        )
        params.pop("client_id", None)
        params.pop("client_secret", None)
        body = urllib.parse.urlencode(params)
        headers_retry = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Bearer {access_token}",
        }
        status2, _, _ = await _do_fetch(
            endpoint, method="POST", headers=headers_retry, body=body
        )
        if status2 < 400:
            log_mcp_debug(
                server_name,
                f"Successfully revoked {token_type_hint} with Bearer auth",
            )
            return
        raise RuntimeError(
            f"Token revocation failed with Bearer auth: HTTP {status2}"
        )

    raise RuntimeError(f"Token revocation failed: HTTP {status}")


async def revoke_server_tokens(
    server_name: str,
    server_config: Any,
    *,
    preserve_step_up_state: bool = False,
) -> None:
    """
    Revokes tokens on the OAuth server if a revocation endpoint is available.

    Per RFC 7009, we revoke the refresh token first (the long-lived credential),
    then the access token.
    """
    storage = get_secure_storage()
    existing_data = storage.read()
    if not existing_data or "mcpOAuth" not in existing_data:
        return

    server_key = get_server_key(server_name, server_config)
    token_data = existing_data.get("mcpOAuth", {}).get(server_key)

    server_url = (
        server_config.get("url") if isinstance(server_config, dict)
        else getattr(server_config, "url", "")
    ) or ""
    oauth_config = (
        server_config.get("oauth") if isinstance(server_config, dict)
        else getattr(server_config, "oauth", None)
    )
    auth_server_metadata_url = (
        oauth_config.get("authServerMetadataUrl") if isinstance(oauth_config, dict)
        else getattr(oauth_config, "authServerMetadataUrl", None)
    ) if oauth_config else None

    # Attempt server-side revocation if there are tokens to revoke (best-effort)
    if token_data and (token_data.get("accessToken") or token_data.get("refreshToken")):
        try:
            as_url = (
                (token_data.get("discoveryState") or {}).get(
                    "authorizationServerUrl"
                )
                or server_url
            )
            metadata = await fetch_auth_server_metadata(
                server_name, as_url, auth_server_metadata_url
            )

            if metadata is None:
                log_mcp_debug(server_name, "No OAuth metadata found")
            else:
                revocation_endpoint = getattr(metadata, "revocation_endpoint", None) or metadata.extra.get("revocation_endpoint")
                if not revocation_endpoint:
                    log_mcp_debug(server_name, "Server does not support token revocation")
                else:
                    revocation_endpoint_str = str(revocation_endpoint)

                    rev_auth_methods = (
                        metadata.revocation_endpoint_auth_methods_supported
                        or metadata.token_endpoint_auth_methods_supported
                    )
                    if (
                        rev_auth_methods
                        and "client_secret_basic" not in rev_auth_methods
                        and "client_secret_post" in rev_auth_methods
                    ):
                        auth_method = "client_secret_post"
                    else:
                        auth_method = "client_secret_basic"

                    log_mcp_debug(
                        server_name,
                        f"Revoking tokens via {revocation_endpoint_str} ({auth_method})",
                    )

                    # Revoke refresh token first
                    if token_data.get("refreshToken"):
                        try:
                            await _revoke_token(
                                server_name=server_name,
                                endpoint=revocation_endpoint_str,
                                token=token_data["refreshToken"],
                                token_type_hint="refresh_token",
                                client_id=token_data.get("clientId"),
                                client_secret=token_data.get("clientSecret"),
                                access_token=token_data.get("accessToken"),
                                auth_method=auth_method,
                            )
                        except Exception as err:
                            log_mcp_debug(
                                server_name,
                                f"Failed to revoke refresh token: {error_message(err)}",
                            )

                    # Then revoke access token
                    if token_data.get("accessToken"):
                        try:
                            await _revoke_token(
                                server_name=server_name,
                                endpoint=revocation_endpoint_str,
                                token=token_data["accessToken"],
                                token_type_hint="access_token",
                                client_id=token_data.get("clientId"),
                                client_secret=token_data.get("clientSecret"),
                                access_token=token_data.get("accessToken"),
                                auth_method=auth_method,
                            )
                        except Exception as err:
                            log_mcp_debug(
                                server_name,
                                f"Failed to revoke access token: {error_message(err)}",
                            )
        except Exception as err:
            # Best-effort: log but don't raise
            log_mcp_debug(
                server_name,
                f"Failed to revoke tokens: {error_message(err)}",
            )
    else:
        log_mcp_debug(server_name, "No tokens to revoke")

    # Always clear local tokens
    clear_server_tokens_from_local_storage(server_name, server_config)

    # When re-authenticating, optionally preserve step-up auth state
    if (
        preserve_step_up_state
        and token_data
        and (token_data.get("stepUpScope") or token_data.get("discoveryState"))
    ):
        fresh_data = storage.read() or {}
        updated: Dict[str, Any] = {
            **fresh_data,
            "mcpOAuth": {
                **(fresh_data.get("mcpOAuth") or {}),
                server_key: {
                    **(fresh_data.get("mcpOAuth", {}).get(server_key) or {}),
                    "serverName": server_name,
                    "serverUrl": server_url,
                    "accessToken": (fresh_data.get("mcpOAuth", {}).get(server_key) or {}).get("accessToken", ""),
                    "expiresAt": (fresh_data.get("mcpOAuth", {}).get(server_key) or {}).get("expiresAt", 0),
                    **({"stepUpScope": token_data["stepUpScope"]} if token_data.get("stepUpScope") else {}),
                    **(
                        {
                            "discoveryState": {
                                "authorizationServerUrl": token_data["discoveryState"].get(
                                    "authorizationServerUrl"
                                ),
                                "resourceMetadataUrl": token_data["discoveryState"].get(
                                    "resourceMetadataUrl"
                                ),
                            }
                        }
                        if token_data.get("discoveryState")
                        else {}
                    ),
                },
            },
        }
        storage.update(updated)
        log_mcp_debug(server_name, "Preserved step-up auth state across revocation")


def clear_server_tokens_from_local_storage(
    server_name: str,
    server_config: Any,
) -> None:
    """Remove stored OAuth tokens for a server from local storage."""
    storage = get_secure_storage()
    existing_data = storage.read()
    if not existing_data or "mcpOAuth" not in existing_data:
        return

    server_key = get_server_key(server_name, server_config)
    mcp_oauth = existing_data.get("mcpOAuth", {})
    if server_key in mcp_oauth:
        del mcp_oauth[server_key]
        storage.update(existing_data)
        log_mcp_debug(server_name, "Cleared stored tokens")


# ---------------------------------------------------------------------------
# XAA (Cross-App Access) auth
# ---------------------------------------------------------------------------

async def _perform_mcp_xaa_auth(
    server_name: str,
    server_config: Any,
    on_authorization_url: Callable[[str], None],
    abort_event: Optional[asyncio.Event] = None,
    skip_browser_open: bool = False,
) -> None:
    """
    XAA (Cross-App Access) auth flow.

    One IdP browser login is reused across all XAA-configured MCP servers:
    1. Acquire id_token from IdP (cached in keychain; if missing runs OIDC flow)
    2. Run RFC 8693 + RFC 7523 exchange (no browser)
    3. Save tokens to keychain slot
    """
    oauth_config = (
        server_config.get("oauth") if isinstance(server_config, dict)
        else getattr(server_config, "oauth", None)
    )
    if not oauth_config or not (
        oauth_config.get("xaa") if isinstance(oauth_config, dict)
        else getattr(oauth_config, "xaa", False)
    ):
        raise ValueError("XAA: oauth.xaa must be set")

    idp = get_xaa_idp_settings()
    if not idp:
        raise RuntimeError(
            "XAA: no IdP connection configured. "
            "Run 'claude mcp xaa setup --issuer <url> --client-id <id> --client-secret' to configure."
        )

    client_id = (
        oauth_config.get("clientId") if isinstance(oauth_config, dict)
        else getattr(oauth_config, "clientId", None)
    )
    if not client_id:
        raise RuntimeError(
            f"XAA: server '{server_name}' needs an AS client_id. Re-add with --client-id."
        )

    client_config = get_mcp_client_config(server_name, server_config)
    client_secret = client_config.get("clientSecret") if client_config else None
    if not client_secret:
        raise RuntimeError(
            f"XAA: AS client secret not found for '{server_name}'. Re-add with --client-secret."
        )

    log_mcp_debug(server_name, "XAA: starting cross-app access flow")

    idp_issuer = (
        idp.get("issuer") if isinstance(idp, dict) else getattr(idp, "issuer", "")
    )
    idp_client_id = (
        idp.get("clientId") if isinstance(idp, dict) else getattr(idp, "clientId", "")
    )
    idp_client_secret = get_idp_client_secret(idp_issuer)
    id_token_cache_hit = get_cached_idp_id_token(idp_issuer) is not None

    failure_stage: XaaFailureStage = "idp_login"
    try:
        try:
            id_token = await acquire_idp_id_token(
                idp_issuer=idp_issuer,
                idp_client_id=idp_client_id,
                idp_client_secret=idp_client_secret,
                on_authorization_url=on_authorization_url,
                skip_browser_open=skip_browser_open,
                abort_event=abort_event,
            )
        except Exception as e:
            if abort_event and abort_event.is_set():
                raise AuthenticationCancelledError() from e
            raise

        failure_stage = "discovery"
        oidc = await discover_oidc(idp_issuer)

        failure_stage = "token_exchange"
        server_url = (
            server_config.get("url") if isinstance(server_config, dict)
            else getattr(server_config, "url", "")
        )
        try:
            tokens = await perform_cross_app_access(
                server_url,
                {
                    "clientId": client_id,
                    "clientSecret": client_secret,
                    "idpClientId": idp_client_id,
                    "idpClientSecret": idp_client_secret,
                    "idpIdToken": id_token,
                    "idpTokenEndpoint": oidc.get("token_endpoint", ""),
                },
                server_name,
                abort_event,
            )
        except Exception as e:
            if abort_event and abort_event.is_set():
                raise AuthenticationCancelledError() from e
            msg = error_message(e)
            if isinstance(e, XaaTokenExchangeError):
                if e.should_clear_id_token:
                    clear_idp_id_token(idp_issuer)
                    log_mcp_debug(
                        server_name,
                        "XAA: cleared cached id_token after token-exchange failure",
                    )
            elif (
                "PRM discovery failed" in msg
                or "AS metadata discovery failed" in msg
                or "no authorization server supports jwt-bearer" in msg
            ):
                failure_stage = "discovery"
            elif "jwt-bearer" in msg:
                failure_stage = "jwt_bearer"
            raise

        # Save tokens via same storage path as normal OAuth
        storage = get_secure_storage()
        existing_data = storage.read() or {}
        server_key = get_server_key(server_name, server_config)
        prev = (existing_data.get("mcpOAuth") or {}).get(server_key) or {}
        storage.update({
            **existing_data,
            "mcpOAuth": {
                **(existing_data.get("mcpOAuth") or {}),
                server_key: {
                    **prev,
                    "serverName": server_name,
                    "serverUrl": server_url,
                    "accessToken": tokens.get("access_token", ""),
                    "refreshToken": tokens.get("refresh_token") or prev.get("refreshToken"),
                    "expiresAt": int(time.time() * 1000) + (tokens.get("expires_in", 3600) * 1000),
                    "scope": tokens.get("scope"),
                    "clientId": client_id,
                    "clientSecret": client_secret,
                    "discoveryState": {
                        "authorizationServerUrl": tokens.get("authorizationServerUrl"),
                    },
                },
            },
        })

        log_mcp_debug(server_name, "XAA: tokens saved")
        log_event("tengu_mcp_oauth_flow_success", {
            "authMethod": "xaa",
            "idTokenCacheHit": id_token_cache_hit,
        })
    except Exception as e:
        if isinstance(e, AuthenticationCancelledError):
            raise
        log_event("tengu_mcp_oauth_flow_failure", {
            "authMethod": "xaa",
            "xaaFailureStage": failure_stage,
            "idTokenCacheHit": id_token_cache_hit,
        })
        raise


# ---------------------------------------------------------------------------
# performMCPOAuthFlow
# ---------------------------------------------------------------------------

async def perform_mcp_oauth_flow(
    server_name: str,
    server_config: Any,
    on_authorization_url: Callable[[str], None],
    abort_event: Optional[asyncio.Event] = None,
    *,
    skip_browser_open: bool = False,
    on_waiting_for_callback: Optional[Callable[[Callable[[str], None]], None]] = None,
) -> None:
    """
    Full OAuth 2.0 authorization_code + PKCE flow for an MCP server.

    For XAA-configured servers, delegates to _perform_mcp_xaa_auth instead.
    """
    oauth_config = (
        server_config.get("oauth") if isinstance(server_config, dict)
        else getattr(server_config, "oauth", None)
    )
    xaa_enabled = oauth_config and (
        oauth_config.get("xaa") if isinstance(oauth_config, dict)
        else getattr(oauth_config, "xaa", False)
    )

    if xaa_enabled:
        if not is_xaa_enabled():
            raise RuntimeError(
                f"XAA is not enabled (set CLAUDE_CODE_ENABLE_XAA=1). "
                f"Remove 'oauth.xaa' from server '{server_name}' to use the standard consent flow."
            )
        server_url = (
            server_config.get("url") if isinstance(server_config, dict)
            else getattr(server_config, "url", "")
        )
        log_event("tengu_mcp_oauth_flow_start", {
            "isOAuthFlow": True,
            "authMethod": "xaa",
            "transportType": (
                server_config.get("type") if isinstance(server_config, dict)
                else getattr(server_config, "type", None)
            ),
            "mcpServerBaseUrl": get_logging_safe_mcp_base_url(server_config),
        })
        await _perform_mcp_xaa_auth(
            server_name,
            server_config,
            on_authorization_url,
            abort_event,
            skip_browser_open,
        )
        return

    # ----------------------------------------------------------------
    # Standard consent / PKCE flow
    # ----------------------------------------------------------------

    # Check for cached step-up scope and resource metadata URL
    storage = get_secure_storage()
    server_key = get_server_key(server_name, server_config)
    cached_entry = (storage.read() or {}).get("mcpOAuth", {}).get(server_key) or {}
    cached_step_up_scope = cached_entry.get("stepUpScope")
    cached_resource_metadata_url_str = (
        cached_entry.get("discoveryState") or {}
    ).get("resourceMetadataUrl")

    # Clear existing stored credentials to ensure fresh client registration
    clear_server_tokens_from_local_storage(server_name, server_config)

    resource_metadata_url: Optional[str] = None
    if cached_resource_metadata_url_str:
        try:
            # Validate it's a valid URL
            urllib.parse.urlparse(cached_resource_metadata_url_str)
            resource_metadata_url = cached_resource_metadata_url_str
        except Exception:
            log_mcp_debug(
                server_name,
                f"Invalid cached resourceMetadataUrl: {cached_resource_metadata_url_str}",
            )

    www_auth_params: Dict[str, Any] = {
        "scope": cached_step_up_scope,
        "resource_metadata_url": resource_metadata_url,
    }

    flow_attempt_id = secrets.token_hex(16)

    server_url = (
        server_config.get("url") if isinstance(server_config, dict)
        else getattr(server_config, "url", "")
    )
    server_type = (
        server_config.get("type") if isinstance(server_config, dict)
        else getattr(server_config, "type", None)
    )
    auth_server_metadata_url = (
        oauth_config.get("authServerMetadataUrl") if isinstance(oauth_config, dict)
        else getattr(oauth_config, "authServerMetadataUrl", None)
    ) if oauth_config else None
    configured_callback_port = (
        oauth_config.get("callbackPort") if isinstance(oauth_config, dict)
        else getattr(oauth_config, "callbackPort", None)
    ) if oauth_config else None

    log_event("tengu_mcp_oauth_flow_start", {
        "flowAttemptId": flow_attempt_id,
        "isOAuthFlow": True,
        "transportType": server_type,
        "mcpServerBaseUrl": get_logging_safe_mcp_base_url(server_config),
    })

    authorization_code_obtained = False

    try:
        port = configured_callback_port or await find_available_port()
        redirect_uri = build_redirect_uri(port)
        log_mcp_debug(
            server_name,
            f"Using redirect port: {port}"
            + (" (from config)" if configured_callback_port else ""),
        )

        provider = ClaudeAuthProvider(
            server_name,
            server_config,
            redirect_uri=redirect_uri,
            handle_redirection=True,
            on_authorization_url=on_authorization_url,
            skip_browser_open=skip_browser_open,
        )

        # Fetch and store OAuth metadata for scope information
        try:
            metadata = await fetch_auth_server_metadata(
                server_name,
                server_url,
                auth_server_metadata_url,
                resource_metadata_url=resource_metadata_url,
            )
            if metadata:
                provider.set_metadata(metadata)
                log_mcp_debug(
                    server_name,
                    f"Fetched OAuth metadata with scope: {get_scope_from_metadata(metadata) or 'NONE'}",
                )
        except Exception as err:
            log_mcp_debug(
                server_name,
                f"Failed to fetch OAuth metadata: {error_message(err)}",
            )

        # Start the OAuth flow (redirect to authorization URL)
        auth_url = await _start_oauth_flow(
            server_name=server_name,
            server_url=server_url,
            provider=provider,
            scope=www_auth_params.get("scope"),
            resource_metadata_url=www_auth_params.get("resource_metadata_url"),
        )

        if auth_url:
            log_mcp_debug(server_name, f"Authorization URL: {redact_sensitive_url_params(auth_url)}")
            on_authorization_url(auth_url)
            if not skip_browser_open:
                try:
                    await open_browser(auth_url)
                except Exception as err:
                    log_mcp_debug(server_name, f"Failed to open browser: {error_message(err)}")

        # Start the callback server and wait for the authorization code
        oauth_state = await provider.state()
        authorization_code = await _wait_for_oauth_callback(
            server_name=server_name,
            port=port,
            oauth_state=oauth_state,
            abort_event=abort_event,
            on_waiting_for_callback=on_waiting_for_callback,
        )

        authorization_code_obtained = True

        # Complete the auth flow with the received code
        log_mcp_debug(server_name, "Completing auth flow with authorization code")
        await _complete_oauth_flow(
            server_name=server_name,
            server_url=server_url,
            provider=provider,
            authorization_code=authorization_code,
            resource_metadata_url=www_auth_params.get("resource_metadata_url"),
        )

        log_mcp_debug(server_name, "OAuth flow completed successfully")
        log_event("tengu_mcp_oauth_flow_success", {
            "flowAttemptId": flow_attempt_id,
            "transportType": server_type,
            "mcpServerBaseUrl": get_logging_safe_mcp_base_url(server_config),
        })

    except Exception as error:
        log_mcp_debug(server_name, f"Error during auth: {error_message(error)}")

        reason: MCPOAuthFlowErrorReason = "unknown"
        oauth_error_code: Optional[str] = None

        if isinstance(error, AuthenticationCancelledError):
            reason = "cancelled"
        elif authorization_code_obtained:
            reason = "token_exchange_failed"
        else:
            msg = error_message(error)
            if "Authentication timeout" in msg:
                reason = "timeout"
            elif "OAuth state mismatch" in msg:
                reason = "state_mismatch"
            elif "OAuth error:" in msg:
                reason = "provider_denied"
            elif any(s in msg for s in ["already in use", "EADDRINUSE", "callback server failed", "No available port"]):
                reason = "port_unavailable"
            elif "SDK auth failed" in msg:
                reason = "sdk_auth_failed"

        if isinstance(error, OAuthError):
            oauth_error_code = error.error_code
            if (
                error.error_code == "invalid_client"
                and "Client not found" in str(error)
            ):
                st = storage.read() or {}
                existing_oauth = st.get("mcpOAuth", {})
                entry = existing_oauth.get(server_key) or {}
                entry.pop("clientId", None)
                entry.pop("clientSecret", None)
                storage.update(st)

        log_event("tengu_mcp_oauth_flow_error", {
            "flowAttemptId": flow_attempt_id,
            "reason": reason,
            "error_code": oauth_error_code,
            "transportType": server_type,
            "mcpServerBaseUrl": get_logging_safe_mcp_base_url(server_config),
        })
        raise


async def _start_oauth_flow(
    server_name: str,
    server_url: str,
    provider: "ClaudeAuthProvider",
    scope: Optional[str] = None,
    resource_metadata_url: Optional[str] = None,
) -> Optional[str]:
    """
    Initiates the OAuth authorization code flow.
    Returns the authorization URL to redirect the user to.
    """
    try:
        metadata = await fetch_auth_server_metadata(
            server_name,
            server_url,
            None,
            resource_metadata_url=resource_metadata_url,
        )
        if not metadata or not metadata.authorization_endpoint:
            log_mcp_debug(server_name, "No authorization endpoint found in metadata")
            return None

        # Build authorization URL with PKCE
        code_verifier = secrets.token_urlsafe(64)
        provider._code_verifier = code_verifier

        code_challenge = hashlib.sha256(code_verifier.encode()).digest()
        import base64
        code_challenge_b64 = base64.urlsafe_b64encode(code_challenge).rstrip(b"=").decode()

        state = await provider.state()
        client_info = await provider.client_information()
        client_id = (client_info.client_id if client_info else None) or (
            provider.client_metadata_url or "unknown-client"
        )

        params: Dict[str, str] = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": provider.redirect_url,
            "state": state,
            "code_challenge": code_challenge_b64,
            "code_challenge_method": "S256",
        }
        effective_scope = scope or get_scope_from_metadata(provider._metadata)
        if effective_scope:
            params["scope"] = effective_scope

        auth_url = metadata.authorization_endpoint + "?" + urllib.parse.urlencode(params)
        provider._authorization_url = auth_url
        return auth_url
    except Exception as err:
        log_mcp_debug(server_name, f"Failed to start OAuth flow: {error_message(err)}")
        return None


async def _wait_for_oauth_callback(
    server_name: str,
    port: int,
    oauth_state: str,
    abort_event: Optional[asyncio.Event] = None,
    on_waiting_for_callback: Optional[Callable[[Callable[[str], None]], None]] = None,
    timeout_s: float = 5 * 60,
) -> str:
    """
    Starts a local HTTP callback server and waits for the OAuth authorization code.
    Returns the authorization code.
    Raises AuthenticationCancelledError on abort.
    Raises RuntimeError on timeout.
    """
    loop = asyncio.get_event_loop()
    code_future: asyncio.Future[str] = loop.create_future()

    # Allow manual callback URL paste
    if on_waiting_for_callback:
        def submit_callback(callback_url: str) -> None:
            if code_future.done():
                return
            try:
                parsed = urllib.parse.urlparse(callback_url)
                qs = urllib.parse.parse_qs(parsed.query)
                code = (qs.get("code") or [None])[0]
                state = (qs.get("state") or [None])[0]
                error = (qs.get("error") or [None])[0]

                if error:
                    error_desc = (qs.get("error_description") or [""])[0]
                    code_future.set_exception(
                        RuntimeError(f"OAuth error: {error} - {error_desc}")
                    )
                    return

                if not code:
                    return  # Not a valid callback URL, ignore

                if state != oauth_state:
                    code_future.set_exception(
                        RuntimeError("OAuth state mismatch - possible CSRF attack")
                    )
                    return

                log_mcp_debug(server_name, "Received auth code via manual callback URL")
                loop.call_soon_threadsafe(code_future.set_result, code)
            except Exception:
                pass

        on_waiting_for_callback(submit_callback)

    # Start local HTTP callback server
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class _CallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass  # Suppress default HTTP log output

        def do_GET(self) -> None:  # noqa: N802
            parsed_url = urllib.parse.urlparse(self.path)
            if parsed_url.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return

            qs = urllib.parse.parse_qs(parsed_url.query)
            code = (qs.get("code") or [None])[0]
            state = (qs.get("state") or [None])[0]
            error = (qs.get("error") or [None])[0]
            error_description = (qs.get("error_description") or [""])[0]
            error_uri = (qs.get("error_uri") or [""])[0]

            if not error and state != oauth_state:
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<h1>Authentication Error</h1><p>Invalid state parameter. Please try again.</p>"
                )
                if not code_future.done():
                    loop.call_soon_threadsafe(
                        code_future.set_exception,
                        RuntimeError("OAuth state mismatch - possible CSRF attack"),
                    )
                return

            if error:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                # Basic XSS escaping
                safe_error = str(error).replace("<", "&lt;").replace(">", "&gt;")
                safe_desc = str(error_description).replace("<", "&lt;").replace(">", "&gt;")
                self.wfile.write(
                    f"<h1>Authentication Error</h1><p>{safe_error}: {safe_desc}</p>"
                    "<p>You can close this window.</p>".encode()
                )
                err_msg = f"OAuth error: {error}"
                if error_description:
                    err_msg += f" - {error_description}"
                if error_uri:
                    err_msg += f" (See: {error_uri})"
                if not code_future.done():
                    loop.call_soon_threadsafe(
                        code_future.set_exception, RuntimeError(err_msg)
                    )
                return

            if code:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<h1>Authentication Successful</h1>"
                    b"<p>You can close this window. Return to Claude Code.</p>"
                )
                if not code_future.done():
                    loop.call_soon_threadsafe(code_future.set_result, code)

    try:
        httpd = HTTPServer(("127.0.0.1", port), _CallbackHandler)
    except OSError as err:
        raise RuntimeError(
            f"OAuth callback port {port} is already in use — another process may be holding it."
        ) from err

    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    try:
        tasks = [asyncio.ensure_future(asyncio.wrap_future(code_future))]
        if abort_event:
            async def wait_abort() -> None:
                await abort_event.wait()
                if not code_future.done():
                    loop.call_soon_threadsafe(
                        code_future.set_exception,
                        AuthenticationCancelledError(),
                    )
            tasks.append(asyncio.ensure_future(wait_abort()))

        try:
            done, pending = await asyncio.wait(
                tasks,
                timeout=timeout_s,
                return_when=asyncio.FIRST_COMPLETED,
            )
        except Exception:
            raise
        finally:
            for t in tasks:
                t.cancel()
                try:
                    await t
                except Exception:
                    pass

        if not done:
            raise RuntimeError("Authentication timeout")

        # Get result or re-raise exception
        return code_future.result()

    finally:
        httpd.shutdown()


async def _complete_oauth_flow(
    server_name: str,
    server_url: str,
    provider: "ClaudeAuthProvider",
    authorization_code: str,
    resource_metadata_url: Optional[str] = None,
) -> None:
    """
    Exchanges the authorization code for tokens and saves them.
    """
    metadata = await fetch_auth_server_metadata(
        server_name,
        server_url,
        None,
        resource_metadata_url=resource_metadata_url,
    )
    if not metadata or not metadata.token_endpoint:
        raise RuntimeError(f"No token endpoint found for server {server_name}")

    client_info = await provider.client_information()
    client_id = (client_info.client_id if client_info else None) or "unknown-client"

    params: Dict[str, str] = {
        "grant_type": "authorization_code",
        "code": authorization_code,
        "redirect_uri": provider.redirect_url,
        "client_id": client_id,
    }
    if provider._code_verifier:
        params["code_verifier"] = provider._code_verifier

    status, _, body = await _do_fetch(
        metadata.token_endpoint,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=urllib.parse.urlencode(params),
    )

    # Normalize error bodies from non-spec-compliant servers
    status, body = await normalize_oauth_error_body(
        status, {}, body
    )

    if status >= 400:
        try:
            err_data = json.loads(body)
            raise OAuthError(
                f"Token exchange failed: {err_data.get('error_description', err_data.get('error', 'unknown'))}",
                err_data.get("error", "unknown"),
            )
        except (json.JSONDecodeError, KeyError):
            raise RuntimeError(f"Token exchange failed with HTTP {status}: {body[:200]}")

    tokens_data = json.loads(body)
    tokens = OAuthTokens(
        access_token=tokens_data["access_token"],
        token_type=tokens_data.get("token_type", "Bearer"),
        refresh_token=tokens_data.get("refresh_token"),
        expires_in=tokens_data.get("expires_in"),
        scope=tokens_data.get("scope"),
    )
    await provider.save_tokens(tokens)
    log_mcp_debug(server_name, "Tokens saved after authorization code exchange")


# ---------------------------------------------------------------------------
# wrapFetchWithStepUpDetection
# ---------------------------------------------------------------------------

def wrap_fetch_with_step_up_detection(
    base_fetch: Callable,
    provider: "ClaudeAuthProvider",
) -> Callable:
    """
    Wraps a fetch callable to detect 403 insufficient_scope responses and mark
    step-up pending on the provider BEFORE the SDK's handler calls auth().

    Without this, the SDK would attempt a (useless) refresh for scope elevation
    — RFC 6749 §6 forbids scope elevation via refresh.
    """
    async def wrapped(url: Any, **kwargs: Any) -> Any:
        response = await base_fetch(url, **kwargs)
        status = getattr(response, "status", None) or getattr(response, "status_code", None)
        if status == 403:
            www_auth = None
            if hasattr(response, "headers"):
                www_auth = (
                    response.headers.get("WWW-Authenticate")
                    or response.headers.get("www-authenticate")
                )
            if www_auth and "insufficient_scope" in www_auth:
                match = re.search(r'scope=(?:"([^"]+)"|([^\s,]+))', www_auth)
                scope = (match.group(1) or match.group(2)) if match else None
                if scope:
                    provider.mark_step_up_pending(scope)
        return response

    return wrapped


# ---------------------------------------------------------------------------
# ClaudeAuthProvider
# ---------------------------------------------------------------------------

class ClaudeAuthProvider:
    """
    OAuthClientProvider implementation for MCP servers.

    Handles token storage, refresh, client registration, and OAuth state
    management for a single MCP server connection.
    """

    def __init__(
        self,
        server_name: str,
        server_config: Any,
        redirect_uri: str = "",
        handle_redirection: bool = False,
        on_authorization_url: Optional[Callable[[str], None]] = None,
        skip_browser_open: bool = False,
    ) -> None:
        self.server_name = server_name
        self.server_config = server_config
        self.redirect_uri = redirect_uri or build_redirect_uri()
        self.handle_redirection = handle_redirection
        self.on_authorization_url_callback = on_authorization_url
        self.skip_browser_open = skip_browser_open

        self._code_verifier: Optional[str] = None
        self._authorization_url: Optional[str] = None
        self._state: Optional[str] = None
        self._scopes: Optional[str] = None
        self._metadata: Optional[AuthorizationServerMetadata] = None
        self._refresh_in_progress: Optional[asyncio.Task] = None
        self._pending_step_up_scope: Optional[str] = None

    # --- Properties ---

    @property
    def redirect_url(self) -> str:
        return self.redirect_uri

    @property
    def authorization_url(self) -> Optional[str]:
        return self._authorization_url

    @property
    def client_metadata(self) -> OAuthClientMetadata:
        """Build OAuthClientMetadata from current configuration."""
        metadata_scope = get_scope_from_metadata(self._metadata)
        meta = OAuthClientMetadata(
            client_name=f"Claude Code ({self.server_name})",
            redirect_uris=[self.redirect_uri],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="none",  # Public client
        )
        if metadata_scope:
            meta.scope = metadata_scope
            log_mcp_debug(self.server_name, f"Using scope from metadata: {meta.scope}")
        return meta

    @property
    def client_metadata_url(self) -> Optional[str]:
        """
        CIMD (SEP-991): URL-based client_id.
        Override via MCP_OAUTH_CLIENT_METADATA_URL env var.
        """
        override = os.environ.get("MCP_OAUTH_CLIENT_METADATA_URL")
        if override:
            log_mcp_debug(self.server_name, f"Using CIMD URL from env: {override}")
            return override
        return MCP_CLIENT_METADATA_URL

    # --- Setters ---

    def set_metadata(self, metadata: Optional[AuthorizationServerMetadata]) -> None:
        self._metadata = metadata

    def mark_step_up_pending(self, scope: str) -> None:
        """
        Called when a 403 insufficient_scope response is detected.
        Causes tokens() to omit refresh_token so the SDK falls through to the PKCE flow.
        """
        self._pending_step_up_scope = scope
        log_mcp_debug(self.server_name, f"Marked step-up pending: {scope}")

    # --- OAuthClientProvider interface ---

    async def state(self) -> str:
        """Generate (or return existing) OAuth CSRF state parameter."""
        if not self._state:
            self._state = secrets.token_urlsafe(32)
            log_mcp_debug(self.server_name, "Generated new OAuth state")
        return self._state

    async def client_information(self) -> Optional[OAuthClientInformation]:
        """Return stored or pre-configured client information."""
        storage = get_secure_storage()
        data = storage.read() or {}
        server_key = get_server_key(self.server_name, self.server_config)

        stored_info = (data.get("mcpOAuth") or {}).get(server_key) or {}
        if stored_info.get("clientId"):
            log_mcp_debug(self.server_name, "Found client info")
            return OAuthClientInformation(
                client_id=stored_info["clientId"],
                client_secret=stored_info.get("clientSecret"),
            )

        oauth_config = (
            self.server_config.get("oauth")
            if isinstance(self.server_config, dict)
            else getattr(self.server_config, "oauth", None)
        )
        config_client_id = (
            oauth_config.get("clientId") if isinstance(oauth_config, dict)
            else getattr(oauth_config, "clientId", None)
        ) if oauth_config else None

        if config_client_id:
            client_config = get_mcp_client_config(self.server_name, self.server_config)
            log_mcp_debug(self.server_name, "Using pre-configured client ID")
            return OAuthClientInformation(
                client_id=config_client_id,
                client_secret=(client_config or {}).get("clientSecret"),
            )

        log_mcp_debug(self.server_name, "No client info found")
        return None

    async def save_client_information(
        self, client_information: OAuthClientInformationFull
    ) -> None:
        """Store OAuth client information returned from Dynamic Client Registration."""
        storage = get_secure_storage()
        existing_data = storage.read() or {}
        server_key = get_server_key(self.server_name, self.server_config)

        server_url = (
            self.server_config.get("url")
            if isinstance(self.server_config, dict)
            else getattr(self.server_config, "url", "")
        )
        existing_mcp_oauth = existing_data.get("mcpOAuth") or {}
        existing_entry = existing_mcp_oauth.get(server_key) or {}

        storage.update({
            **existing_data,
            "mcpOAuth": {
                **existing_mcp_oauth,
                server_key: {
                    **existing_entry,
                    "serverName": self.server_name,
                    "serverUrl": server_url,
                    "clientId": client_information.client_id,
                    "clientSecret": client_information.client_secret,
                    "accessToken": existing_entry.get("accessToken", ""),
                    "expiresAt": existing_entry.get("expiresAt", 0),
                },
            },
        })

    async def tokens(self) -> Optional[OAuthTokens]:
        """
        Return current OAuth tokens, refreshing proactively if expiring.
        Returns None if no tokens or if tokens have expired without a refresh token.

        XAA: fires a silent exchange when the access_token is absent/expiring and
        no refresh_token is available.
        """
        storage = get_secure_storage()
        data = await storage.read_async() if hasattr(storage, "read_async") else storage.read()
        server_key = get_server_key(self.server_name, self.server_config)
        token_data = (data or {}).get("mcpOAuth", {}).get(server_key)

        oauth_config = (
            self.server_config.get("oauth")
            if isinstance(self.server_config, dict)
            else getattr(self.server_config, "oauth", None)
        )
        xaa_config = (
            oauth_config.get("xaa") if isinstance(oauth_config, dict)
            else getattr(oauth_config, "xaa", False)
        ) if oauth_config else False

        # XAA silent refresh path
        if (
            is_xaa_enabled()
            and xaa_config
            and not (token_data or {}).get("refreshToken")
            and (
                not (token_data or {}).get("accessToken")
                or (
                    (token_data or {}).get("expiresAt", 0) - int(time.time() * 1000)
                ) / 1000 <= 300
            )
        ):
            if not self._refresh_in_progress:
                log_mcp_debug(
                    self.server_name,
                    "XAA: access_token expiring, attempting silent exchange"
                    if token_data
                    else "XAA: no access_token yet, attempting silent exchange",
                )
                self._refresh_in_progress = asyncio.ensure_future(self._xaa_refresh())

                def _clear_refresh(_: Any) -> None:
                    self._refresh_in_progress = None

                self._refresh_in_progress.add_done_callback(_clear_refresh)

            try:
                refreshed = await self._refresh_in_progress
                if refreshed:
                    return refreshed
            except Exception as e:
                log_mcp_debug(
                    self.server_name,
                    f"XAA silent exchange failed: {error_message(e)}",
                )

        if not token_data:
            log_mcp_debug(self.server_name, "No token data found")
            return None

        expires_in = (token_data.get("expiresAt", 0) - int(time.time() * 1000)) / 1000

        # Step-up check
        current_scopes = set((token_data.get("scope") or "").split())
        needs_step_up = (
            self._pending_step_up_scope is not None
            and any(
                s not in current_scopes
                for s in self._pending_step_up_scope.split()
            )
        )
        if needs_step_up:
            log_mcp_debug(
                self.server_name,
                f"Step-up pending ({self._pending_step_up_scope}), omitting refresh_token",
            )

        if expires_in <= 0 and not token_data.get("refreshToken"):
            log_mcp_debug(self.server_name, "Token expired without refresh token")
            return None

        # Proactive refresh if expiring within 5 minutes
        if expires_in <= 300 and token_data.get("refreshToken") and not needs_step_up:
            if not self._refresh_in_progress:
                log_mcp_debug(
                    self.server_name,
                    f"Token expires in {int(expires_in)}s, attempting proactive refresh",
                )
                self._refresh_in_progress = asyncio.ensure_future(
                    self.refresh_authorization(token_data["refreshToken"])
                )

                def _clear_refresh2(_: Any) -> None:
                    self._refresh_in_progress = None

                self._refresh_in_progress.add_done_callback(_clear_refresh2)
            else:
                log_mcp_debug(
                    self.server_name,
                    "Token refresh already in progress, reusing existing promise",
                )

            try:
                refreshed = await self._refresh_in_progress
                if refreshed:
                    log_mcp_debug(self.server_name, "Token refreshed successfully")
                    return refreshed
                log_mcp_debug(
                    self.server_name, "Token refresh failed, returning current tokens"
                )
            except Exception as e:
                log_mcp_debug(
                    self.server_name, f"Token refresh error: {error_message(e)}"
                )

        tokens = OAuthTokens(
            access_token=token_data.get("accessToken", ""),
            token_type="Bearer",
            refresh_token=None if needs_step_up else token_data.get("refreshToken"),
            expires_in=expires_in,
            scope=token_data.get("scope"),
        )

        log_mcp_debug(self.server_name, "Returning tokens")
        log_mcp_debug(self.server_name, f"Token length: {len(tokens.access_token or '')}")
        log_mcp_debug(self.server_name, f"Has refresh token: {bool(tokens.refresh_token)}")
        log_mcp_debug(self.server_name, f"Expires in: {int(expires_in)}s")

        return tokens

    async def save_tokens(self, tokens: OAuthTokens) -> None:
        """Persist OAuth tokens to secure storage."""
        self._pending_step_up_scope = None
        storage = get_secure_storage()
        existing_data = storage.read() or {}
        server_key = get_server_key(self.server_name, self.server_config)

        log_mcp_debug(self.server_name, "Saving tokens")
        log_mcp_debug(self.server_name, f"Token expires in: {tokens.expires_in}")
        log_mcp_debug(self.server_name, f"Has refresh token: {bool(tokens.refresh_token)}")

        server_url = (
            self.server_config.get("url")
            if isinstance(self.server_config, dict)
            else getattr(self.server_config, "url", "")
        )
        existing_mcp_oauth = existing_data.get("mcpOAuth") or {}
        existing_entry = existing_mcp_oauth.get(server_key) or {}

        storage.update({
            **existing_data,
            "mcpOAuth": {
                **existing_mcp_oauth,
                server_key: {
                    **existing_entry,
                    "serverName": self.server_name,
                    "serverUrl": server_url,
                    "accessToken": tokens.access_token,
                    "refreshToken": tokens.refresh_token,
                    "expiresAt": int(time.time() * 1000) + int((tokens.expires_in or 3600) * 1000),
                    "scope": tokens.scope,
                },
            },
        })

    async def redirect_to_authorization(self, authorization_url: str) -> None:
        """Called by SDK to redirect the user to the OAuth authorization URL."""
        self._authorization_url = authorization_url
        if self.on_authorization_url_callback:
            self.on_authorization_url_callback(authorization_url)
        if self.handle_redirection and not self.skip_browser_open:
            try:
                await open_browser(authorization_url)
            except Exception as e:
                log_mcp_debug(
                    self.server_name,
                    f"Failed to open browser: {error_message(e)}",
                )

    async def refresh_authorization(
        self, refresh_token: str
    ) -> Optional[OAuthTokens]:
        """
        Refreshes the access token using the refresh token.

        Uses a lockfile to prevent concurrent refreshes across processes.
        Returns new tokens on success, None on failure.
        """
        import os
        lock_path = os.path.join(
            get_claude_config_home_dir(),
            f"mcp-refresh-{get_server_key(self.server_name, self.server_config)}.lock",
        )

        storage = get_secure_storage()
        data = storage.read()
        server_key = get_server_key(self.server_name, self.server_config)
        token_data = (data or {}).get("mcpOAuth", {}).get(server_key) or {}

        server_url = (
            self.server_config.get("url")
            if isinstance(self.server_config, dict)
            else getattr(self.server_config, "url", "")
        )
        oauth_config = (
            self.server_config.get("oauth")
            if isinstance(self.server_config, dict)
            else getattr(self.server_config, "oauth", None)
        )
        auth_server_metadata_url = (
            oauth_config.get("authServerMetadataUrl") if isinstance(oauth_config, dict)
            else getattr(oauth_config, "authServerMetadataUrl", None)
        ) if oauth_config else None

        as_url = (token_data.get("discoveryState") or {}).get("authorizationServerUrl") or server_url

        for attempt in range(MAX_LOCK_RETRIES):
            try:
                log_mcp_debug(
                    self.server_name,
                    f"Acquiring refresh lock (attempt {attempt + 1}/{MAX_LOCK_RETRIES})",
                )
                got_lock = await acquire_lock(lock_path)
                if not got_lock:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue

                try:
                    # Re-read storage after acquiring lock to pick up concurrent refreshes
                    fresh_data = storage.read()
                    fresh_token_data = (fresh_data or {}).get("mcpOAuth", {}).get(server_key) or {}

                    # If another process already refreshed, use their token
                    if (
                        fresh_token_data.get("accessToken")
                        and fresh_token_data.get("accessToken") != token_data.get("accessToken")
                        and (fresh_token_data.get("expiresAt", 0) - int(time.time() * 1000)) / 1000 > 60
                    ):
                        log_mcp_debug(
                            self.server_name,
                            "Another process already refreshed the token",
                        )
                        return OAuthTokens(
                            access_token=fresh_token_data["accessToken"],
                            refresh_token=fresh_token_data.get("refreshToken"),
                            expires_in=(fresh_token_data.get("expiresAt", 0) - int(time.time() * 1000)) / 1000,
                            scope=fresh_token_data.get("scope"),
                        )

                    metadata = await fetch_auth_server_metadata(
                        self.server_name, as_url, auth_server_metadata_url
                    )
                    if not metadata:
                        log_event("tengu_mcp_oauth_refresh_failure", {
                            "reason": "metadata_discovery_failed",
                            "serverName": self.server_name,
                        })
                        return None

                    client_info = await self.client_information()
                    if not client_info:
                        log_event("tengu_mcp_oauth_refresh_failure", {
                            "reason": "no_client_info",
                            "serverName": self.server_name,
                        })
                        return None

                    params: Dict[str, str] = {
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": client_info.client_id,
                    }
                    if client_info.client_secret:
                        params["client_secret"] = client_info.client_secret

                    if not metadata.token_endpoint:
                        log_mcp_debug(self.server_name, "No token endpoint found")
                        return None

                    status, _, body = await _do_fetch(
                        metadata.token_endpoint,
                        method="POST",
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                        body=urllib.parse.urlencode(params),
                    )

                    status, body = await normalize_oauth_error_body(status, {}, body)

                    if status >= 400:
                        err_data: Dict[str, Any] = {}
                        try:
                            err_data = json.loads(body)
                        except Exception:
                            pass

                        error_code = err_data.get("error", "unknown")
                        if error_code == "invalid_grant":
                            # Invalidate credentials on invalid_grant
                            self._invalidate_credentials("tokens")
                            log_event("tengu_mcp_oauth_refresh_failure", {
                                "reason": "invalid_grant",
                                "serverName": self.server_name,
                            })
                            raise InvalidGrantError()

                        if status in (503, 429) and attempt < MAX_LOCK_RETRIES - 1:
                            await asyncio.sleep(1.0 * (attempt + 1))
                            continue

                        log_event("tengu_mcp_oauth_refresh_failure", {
                            "reason": "request_failed",
                            "serverName": self.server_name,
                        })
                        return None

                    tokens_data = json.loads(body)
                    new_tokens = OAuthTokens(
                        access_token=tokens_data.get("access_token", ""),
                        token_type=tokens_data.get("token_type", "Bearer"),
                        refresh_token=tokens_data.get("refresh_token") or refresh_token,
                        expires_in=tokens_data.get("expires_in"),
                        scope=tokens_data.get("scope"),
                    )

                    if not new_tokens.access_token:
                        log_event("tengu_mcp_oauth_refresh_failure", {
                            "reason": "no_tokens_returned",
                            "serverName": self.server_name,
                        })
                        return None

                    await self.save_tokens(new_tokens)
                    log_mcp_debug(self.server_name, "Token refresh successful")
                    return new_tokens

                finally:
                    await release_lock(lock_path)

            except InvalidGrantError:
                raise
            except Exception as e:
                log_mcp_debug(
                    self.server_name,
                    f"Refresh attempt {attempt + 1} failed: {error_message(e)}",
                )
                if attempt < MAX_LOCK_RETRIES - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
                else:
                    log_event("tengu_mcp_oauth_refresh_failure", {
                        "reason": "transient_retries_exhausted",
                        "serverName": self.server_name,
                    })
                    return None

        return None

    def _invalidate_credentials(self, what: str = "tokens") -> None:
        """Remove tokens (or all credentials) from storage."""
        storage = get_secure_storage()
        data = storage.read() or {}
        server_key = get_server_key(self.server_name, self.server_config)
        mcp_oauth = data.get("mcpOAuth") or {}
        entry = mcp_oauth.get(server_key) or {}

        if what == "tokens":
            entry.pop("accessToken", None)
            entry.pop("refreshToken", None)
            entry.pop("expiresAt", None)
            mcp_oauth[server_key] = entry
            storage.update({**data, "mcpOAuth": mcp_oauth})
        elif what == "all":
            mcp_oauth.pop(server_key, None)
            storage.update({**data, "mcpOAuth": mcp_oauth})

    async def _xaa_refresh(self) -> Optional[OAuthTokens]:
        """
        XAA silent refresh: cached id_token → Layer-2 exchange → new access_token.
        No browser popup required.

        Returns None if the id_token is gone from cache.
        """
        idp = get_xaa_idp_settings()
        if not idp:
            return None

        idp_issuer = (
            idp.get("issuer") if isinstance(idp, dict) else getattr(idp, "issuer", "")
        )
        id_token = get_cached_idp_id_token(idp_issuer)
        if not id_token:
            log_mcp_debug(
                self.server_name,
                "XAA: id_token not cached, needs interactive re-auth",
            )
            return None

        oauth_config = (
            self.server_config.get("oauth")
            if isinstance(self.server_config, dict)
            else getattr(self.server_config, "oauth", None)
        )
        client_id = (
            oauth_config.get("clientId") if isinstance(oauth_config, dict)
            else getattr(oauth_config, "clientId", None)
        ) if oauth_config else None
        client_config = get_mcp_client_config(self.server_name, self.server_config)
        client_secret = (client_config or {}).get("clientSecret")

        if not client_id or not client_secret:
            log_mcp_debug(
                self.server_name,
                "XAA: missing clientId or clientSecret in config — skipping silent refresh",
            )
            return None

        idp_client_id = (
            idp.get("clientId") if isinstance(idp, dict) else getattr(idp, "clientId", "")
        )
        idp_client_secret = get_idp_client_secret(idp_issuer)

        try:
            oidc = await discover_oidc(idp_issuer)
        except Exception as e:
            log_mcp_debug(
                self.server_name,
                f"XAA: OIDC discovery failed in silent refresh: {error_message(e)}",
            )
            return None

        server_url = (
            self.server_config.get("url")
            if isinstance(self.server_config, dict)
            else getattr(self.server_config, "url", "")
        )

        try:
            tokens_raw = await perform_cross_app_access(
                server_url,
                {
                    "clientId": client_id,
                    "clientSecret": client_secret,
                    "idpClientId": idp_client_id,
                    "idpClientSecret": idp_client_secret,
                    "idpIdToken": id_token,
                    "idpTokenEndpoint": oidc.get("token_endpoint", ""),
                },
                self.server_name,
            )
        except XaaTokenExchangeError as e:
            if e.should_clear_id_token:
                clear_idp_id_token(idp_issuer)
                log_mcp_debug(
                    self.server_name,
                    "XAA: cleared cached id_token after silent refresh failure",
                )
            return None
        except Exception as e:
            log_mcp_debug(
                self.server_name,
                f"XAA: silent exchange failed: {error_message(e)}",
            )
            return None

        # Write tokens directly to avoid instantiating whole provider
        storage = get_secure_storage()
        existing_data = storage.read() or {}
        server_key = get_server_key(self.server_name, self.server_config)
        prev = (existing_data.get("mcpOAuth") or {}).get(server_key) or {}
        new_entry = {
            **prev,
            "serverName": self.server_name,
            "serverUrl": server_url,
            "accessToken": tokens_raw.get("access_token", ""),
            "refreshToken": tokens_raw.get("refresh_token") or prev.get("refreshToken"),
            "expiresAt": int(time.time() * 1000) + int((tokens_raw.get("expires_in", 3600)) * 1000),
            "scope": tokens_raw.get("scope"),
            "clientId": client_id,
            "clientSecret": client_secret,
            "discoveryState": {
                "authorizationServerUrl": tokens_raw.get("authorizationServerUrl"),
            },
        }
        storage.update({
            **existing_data,
            "mcpOAuth": {
                **(existing_data.get("mcpOAuth") or {}),
                server_key: new_entry,
            },
        })

        return OAuthTokens(
            access_token=new_entry["accessToken"],
            token_type="Bearer",
            refresh_token=new_entry.get("refreshToken"),
            expires_in=(new_entry.get("expiresAt", 0) - int(time.time() * 1000)) / 1000,
            scope=new_entry.get("scope"),
        )


# ---------------------------------------------------------------------------
# Client secret / client config helpers
# ---------------------------------------------------------------------------

async def read_client_secret() -> str:
    """
    Reads the OAuth client secret from the environment or prompts the user.

    Mirrors TypeScript readClientSecret.
    """
    env_secret = os.environ.get("MCP_CLIENT_SECRET")
    if env_secret:
        return env_secret

    if not sys.stdin.isatty():
        raise RuntimeError(
            "No TTY available to prompt for client secret. "
            "Set MCP_CLIENT_SECRET env var instead."
        )

    sys.stderr.write("Enter OAuth client secret: ")
    sys.stderr.flush()

    # Read without echoing (Unix-specific)
    try:
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            chars: List[str] = []
            while True:
                ch = sys.stdin.read(1)
                if ch in ("\n", "\r"):
                    break
                elif ch == "\x03":  # Ctrl+C
                    raise RuntimeError("Cancelled")
                elif ch in ("\x7f", "\x08"):  # Backspace
                    if chars:
                        chars.pop()
                else:
                    chars.append(ch)
            return "".join(chars)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            sys.stderr.write("\n")
            sys.stderr.flush()
    except ImportError:
        # Windows fallback
        import getpass
        return getpass.getpass("")


def save_mcp_client_secret(
    server_name: str,
    server_config: Any,
    client_secret: str,
) -> None:
    """Persist an OAuth client secret to secure storage."""
    storage = get_secure_storage()
    existing_data = storage.read() or {}
    server_key = get_server_key(server_name, server_config)
    storage.update({
        **existing_data,
        "mcpOAuthClientConfig": {
            **(existing_data.get("mcpOAuthClientConfig") or {}),
            server_key: {"clientSecret": client_secret},
        },
    })


def clear_mcp_client_config(
    server_name: str,
    server_config: Any,
) -> None:
    """Remove stored OAuth client configuration from secure storage."""
    storage = get_secure_storage()
    existing_data = storage.read()
    if not existing_data or "mcpOAuthClientConfig" not in existing_data:
        return
    server_key = get_server_key(server_name, server_config)
    mcp_client_config = existing_data.get("mcpOAuthClientConfig") or {}
    if server_key in mcp_client_config:
        del mcp_client_config[server_key]
        storage.update(existing_data)


def get_mcp_client_config(
    server_name: str,
    server_config: Any,
) -> Optional[Dict[str, Any]]:
    """Retrieve OAuth client configuration from secure storage."""
    storage = get_secure_storage()
    data = storage.read()
    server_key = get_server_key(server_name, server_config)
    return (data or {}).get("mcpOAuthClientConfig", {}).get(server_key)


# ---------------------------------------------------------------------------
# Scope extraction helper
# ---------------------------------------------------------------------------

def get_scope_from_metadata(
    metadata: Optional[AuthorizationServerMetadata],
) -> Optional[str]:
    """
    Safely extracts scope information from AuthorizationServerMetadata.

    Different providers use different fields:
    - 'scope' (non-standard but used by some providers)
    - 'default_scope' (non-standard)
    - 'scopes_supported' (standard OAuth 2.0)
    """
    if metadata is None:
        return None
    if metadata.scope:
        return metadata.scope
    if metadata.default_scope:
        return metadata.default_scope
    if metadata.scopes_supported:
        return " ".join(metadata.scopes_supported)
    return None
