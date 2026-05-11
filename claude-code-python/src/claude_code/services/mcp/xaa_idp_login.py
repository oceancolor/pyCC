"""
services/mcp/xaa_idp_login.py — XAA IdP Login (OIDC authorization_code + PKCE).
Ported from services/mcp/xaaIdpLogin.ts (487 lines).

Acquires an OIDC id_token from an enterprise IdP via the standard
authorization_code + PKCE flow, then caches it by IdP issuer.

This is the "one browser pop" in the XAA value prop: one IdP login → N silent
MCP server auths. The id_token is cached in the keychain and reused until expiry.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
from urllib.parse import parse_qs, urlparse

import aiohttp  # type: ignore

logger = logging.getLogger(__name__)

IDP_LOGIN_TIMEOUT_S = 5 * 60         # 5 minutes
IDP_REQUEST_TIMEOUT_S = 30
ID_TOKEN_EXPIRY_BUFFER_S = 60


# ---------------------------------------------------------------------------
# Lazy helpers
# ---------------------------------------------------------------------------

def _log_mcp_debug(server: str, msg: str) -> None:
    try:
        from claude_code.utils.log import log_mcp_debug
        log_mcp_debug(server, msg)
    except (ImportError, Exception):
        logger.debug("[%s] %s", server, msg)


def _is_env_truthy(val: Optional[str]) -> bool:
    if not val:
        return False
    return val.strip().lower() in ("1", "true", "yes")


def _get_secure_storage():
    try:
        from claude_code.utils.secure_storage import get_secure_storage
        return get_secure_storage()
    except (ImportError, Exception):
        return None


def _get_initial_settings() -> dict:
    try:
        from claude_code.utils.settings.settings import get_initial_settings
        return dict(get_initial_settings() or {})
    except (ImportError, Exception):
        return {}


def _open_browser(url: str) -> None:
    try:
        from claude_code.utils.browser import open_browser
        open_browser(url)
    except (ImportError, Exception):
        import webbrowser
        webbrowser.open(url)


def _get_platform() -> str:
    try:
        from claude_code.utils.platform import get_platform
        return get_platform()
    except (ImportError, Exception):
        import sys
        if sys.platform == "win32":
            return "windows"
        elif sys.platform == "darwin":
            return "mac"
        return "linux"


# ---------------------------------------------------------------------------
# Feature gate
# ---------------------------------------------------------------------------

def is_xaa_enabled() -> bool:
    """Check if XAA is enabled via CLAUDE_CODE_ENABLE_XAA env var."""
    return _is_env_truthy(os.environ.get("CLAUDE_CODE_ENABLE_XAA"))


# ---------------------------------------------------------------------------
# XaaIdpSettings
# ---------------------------------------------------------------------------

@dataclass
class XaaIdpSettings:
    issuer: str
    client_id: str
    callback_port: Optional[int] = None


def get_xaa_idp_settings() -> Optional[XaaIdpSettings]:
    """
    Typed accessor for settings.xaaIdp. The field is env-gated in SettingsSchema
    so it doesn't surface in SDK types — this is the one cast.
    """
    settings = _get_initial_settings()
    xaa_idp = settings.get("xaaIdp")
    if not xaa_idp or not isinstance(xaa_idp, dict):
        return None
    issuer = xaa_idp.get("issuer")
    client_id = xaa_idp.get("clientId")
    if not issuer or not client_id:
        return None
    return XaaIdpSettings(
        issuer=issuer,
        client_id=client_id,
        callback_port=xaa_idp.get("callbackPort"),
    )


# ---------------------------------------------------------------------------
# Issuer key normalization
# ---------------------------------------------------------------------------

def issuer_key(issuer: str) -> str:
    """
    Normalize an IdP issuer URL for use as a cache key: strip trailing slashes,
    lowercase host. Exported so the setup command can compare issuers.
    """
    try:
        u = urlparse(issuer)
        path = u.path.rstrip("/")
        host = u.hostname or ""
        port_str = f":{u.port}" if u.port else ""
        normalized = f"{u.scheme}://{host}{port_str}{path}"
        if u.query:
            normalized += f"?{u.query}"
        return normalized
    except Exception:
        return issuer.rstrip("/")


# ---------------------------------------------------------------------------
# id_token cache (keychain / secure storage)
# ---------------------------------------------------------------------------

def get_cached_idp_id_token(idp_issuer: str) -> Optional[str]:
    """
    Read a cached id_token for the given IdP issuer from secure storage.
    Returns None if missing or within ID_TOKEN_EXPIRY_BUFFER_S of expiring.
    """
    storage = _get_secure_storage()
    if not storage:
        return None
    try:
        data = storage.read() or {}
        entry = (data.get("mcpXaaIdp") or {}).get(issuer_key(idp_issuer))
        if not entry:
            return None
        remaining_ms = entry.get("expiresAt", 0) - (time.time() * 1000)
        if remaining_ms <= ID_TOKEN_EXPIRY_BUFFER_S * 1000:
            return None
        return entry.get("idToken")
    except Exception:
        return None


def _save_idp_id_token(idp_issuer: str, id_token: str, expires_at: int) -> None:
    """Save id_token to secure storage keyed by issuer."""
    storage = _get_secure_storage()
    if not storage:
        return
    try:
        existing = storage.read() or {}
        xaa_idp = dict(existing.get("mcpXaaIdp") or {})
        xaa_idp[issuer_key(idp_issuer)] = {"idToken": id_token, "expiresAt": expires_at}
        storage.update({**existing, "mcpXaaIdp": xaa_idp})
    except Exception:
        pass


def save_idp_id_token_from_jwt(idp_issuer: str, id_token: str) -> int:
    """
    Save an externally-obtained id_token into the XAA cache.
    Parses the JWT's exp claim for cache TTL.
    Returns the expiresAt it computed.
    """
    exp = _jwt_exp(id_token)
    expires_at = exp * 1000 if exp else int(time.time() * 1000) + 3600 * 1000
    _save_idp_id_token(idp_issuer, id_token, expires_at)
    return expires_at


def clear_idp_id_token(idp_issuer: str) -> None:
    """Remove the cached id_token for the given issuer."""
    storage = _get_secure_storage()
    if not storage:
        return
    try:
        existing = storage.read()
        if not existing:
            return
        key = issuer_key(idp_issuer)
        xaa_idp = dict(existing.get("mcpXaaIdp") or {})
        if key not in xaa_idp:
            return
        del xaa_idp[key]
        storage.update({**existing, "mcpXaaIdp": xaa_idp})
    except Exception:
        pass


def save_idp_client_secret(
    idp_issuer: str, client_secret: str
) -> Dict[str, Any]:
    """
    Save an IdP client secret to secure storage, keyed by IdP issuer.
    Returns {"success": bool, "warning": str|None}.
    """
    storage = _get_secure_storage()
    if not storage:
        return {"success": False, "warning": "Secure storage not available"}
    try:
        existing = storage.read() or {}
        idp_config = dict(existing.get("mcpXaaIdpConfig") or {})
        idp_config[issuer_key(idp_issuer)] = {"clientSecret": client_secret}
        result = storage.update({**existing, "mcpXaaIdpConfig": idp_config})
        if isinstance(result, dict):
            return result
        return {"success": True}
    except Exception as e:
        return {"success": False, "warning": str(e)}


def get_idp_client_secret(idp_issuer: str) -> Optional[str]:
    """Read the IdP client secret for the given issuer from secure storage."""
    storage = _get_secure_storage()
    if not storage:
        return None
    try:
        data = storage.read() or {}
        return (data.get("mcpXaaIdpConfig") or {}).get(
            issuer_key(idp_issuer), {}
        ).get("clientSecret")
    except Exception:
        return None


def clear_idp_client_secret(idp_issuer: str) -> None:
    """Remove the IdP client secret for the given issuer from secure storage."""
    storage = _get_secure_storage()
    if not storage:
        return
    try:
        existing = storage.read()
        if not existing:
            return
        key = issuer_key(idp_issuer)
        idp_config = dict(existing.get("mcpXaaIdpConfig") or {})
        if key not in idp_config:
            return
        del idp_config[key]
        storage.update({**existing, "mcpXaaIdpConfig": idp_config})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# OIDC discovery
# ---------------------------------------------------------------------------

async def discover_oidc(idp_issuer: str) -> dict:
    """
    OIDC Discovery §4.1: {issuer}/.well-known/openid-configuration.
    Path APPEND (not replace) to handle Azure AD, Okta custom auth servers, Keycloak.
    """
    base = idp_issuer if idp_issuer.endswith("/") else idp_issuer + "/"
    # Use relative URL resolution for path safety (mirrors TS `new URL('...', base)`)
    from urllib.parse import urljoin
    url = urljoin(base, ".well-known/openid-configuration")

    timeout = aiohttp.ClientTimeout(total=IDP_REQUEST_TIMEOUT_S)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers={"Accept": "application/json"}) as resp:
            if not resp.ok:
                raise Exception(
                    f"XAA IdP: OIDC discovery failed: HTTP {resp.status} at {url}"
                )
            try:
                body = await resp.json(content_type=None)
            except Exception:
                raise Exception(
                    f"XAA IdP: OIDC discovery returned non-JSON at {url} "
                    f"(captive portal or proxy?)"
                )

    token_endpoint = body.get("token_endpoint")
    authorization_endpoint = body.get("authorization_endpoint")

    if not token_endpoint or not authorization_endpoint:
        raise Exception(f"XAA IdP: invalid OIDC metadata: missing required endpoints")

    if not token_endpoint.startswith("https://"):
        raise Exception(
            f"XAA IdP: refusing non-HTTPS token endpoint: {token_endpoint}"
        )

    return body


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def _jwt_exp(jwt: str) -> Optional[int]:
    """
    Decode the exp claim from a JWT without verifying its signature.
    Returns None if parsing fails or exp is absent.
    Used only to derive a cache TTL.
    """
    parts = jwt.split(".")
    if len(parts) != 3:
        return None
    try:
        # Add padding for base64url
        payload_b64 = parts[1] + "=="
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
        exp = payload.get("exp")
        return int(exp) if isinstance(exp, (int, float)) else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def _generate_code_verifier() -> str:
    """Generate a PKCE code_verifier (43-128 chars, URL-safe)."""
    return secrets.token_urlsafe(64)


def _generate_code_challenge(code_verifier: str) -> str:
    """Generate PKCE code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# ---------------------------------------------------------------------------
# Callback server
# ---------------------------------------------------------------------------

async def _wait_for_callback(
    port: int,
    expected_state: str,
    on_listening: Callable,
    abort_event: Optional[asyncio.Event] = None,
) -> str:
    """
    Wait for the OAuth authorization code on a local callback server.
    Returns the code once /callback is hit with a matching state.
    on_listening fires after the socket is bound.
    """
    from aiohttp import web

    code_future: asyncio.Future = asyncio.get_event_loop().create_future()
    server = web.Application()

    async def callback_handler(request: web.Request) -> web.Response:
        error = request.rel_url.query.get("error")
        if error:
            desc = request.rel_url.query.get("error_description", "")
            if not code_future.done():
                code_future.set_exception(
                    Exception(f"XAA IdP: {error}" + (f" — {desc}" if desc else ""))
                )
            return web.Response(
                status=400,
                content_type="text/html",
                text=f"<html><body><h3>IdP login failed</h3><p>{error}</p><p>{desc}</p></body></html>",
            )

        state = request.rel_url.query.get("state")
        if state != expected_state:
            if not code_future.done():
                code_future.set_exception(
                    Exception("XAA IdP: state mismatch (possible CSRF)")
                )
            return web.Response(
                status=400,
                content_type="text/html",
                text="<html><body><h3>State mismatch</h3></body></html>",
            )

        code = request.rel_url.query.get("code")
        if not code:
            if not code_future.done():
                code_future.set_exception(Exception("XAA IdP: callback missing code"))
            return web.Response(
                status=400,
                content_type="text/html",
                text="<html><body><h3>Missing code</h3></body></html>",
            )

        if not code_future.done():
            code_future.set_result(code)
        return web.Response(
            status=200,
            content_type="text/html",
            text="<html><body><h3>IdP login complete — you can close this window.</h3></body></html>",
        )

    server.router.add_get("/callback", callback_handler)
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)

    try:
        await site.start()
    except OSError as e:
        if e.errno == 98:  # EADDRINUSE
            plat = _get_platform()
            find_cmd = (
                f"netstat -ano | findstr :{port}"
                if plat == "windows"
                else f"lsof -ti:{port} -sTCP:LISTEN"
            )
            raise Exception(
                f"XAA IdP: callback port {port} is already in use. "
                f"Run `{find_cmd}` to find the holder."
            )
        raise Exception(f"XAA IdP: callback server failed: {e}")

    try:
        on_listening()
    except Exception as e:
        await runner.cleanup()
        raise

    try:
        # Wait for code or timeout
        try:
            if abort_event is not None:
                done, _ = await asyncio.wait(
                    [
                        asyncio.ensure_future(code_future),
                        asyncio.ensure_future(abort_event.wait()),
                    ],
                    timeout=IDP_LOGIN_TIMEOUT_S,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if abort_event.is_set():
                    raise Exception("XAA IdP: login cancelled")
                if not done:
                    raise Exception("XAA IdP: login timed out")
                return await code_future
            else:
                return await asyncio.wait_for(code_future, timeout=IDP_LOGIN_TIMEOUT_S)
        except asyncio.TimeoutError:
            raise Exception("XAA IdP: login timed out")
    finally:
        await runner.cleanup()


# ---------------------------------------------------------------------------
# IdpLoginOptions
# ---------------------------------------------------------------------------

@dataclass
class IdpLoginOptions:
    idp_issuer: str
    idp_client_id: str
    idp_client_secret: Optional[str] = None
    callback_port: Optional[int] = None
    on_authorization_url: Optional[Callable[[str], None]] = None
    skip_browser_open: bool = False
    abort_event: Optional[asyncio.Event] = None


# ---------------------------------------------------------------------------
# Build redirect URI / find available port
# ---------------------------------------------------------------------------

def _build_redirect_uri(port: int) -> str:
    try:
        from claude_code.services.mcp.oauth_port import build_redirect_uri
        return build_redirect_uri(port)
    except (ImportError, Exception):
        return f"http://127.0.0.1:{port}/callback"


async def _find_available_port() -> int:
    try:
        from claude_code.services.mcp.oauth_port import find_available_port
        return await find_available_port()
    except (ImportError, Exception):
        import socket
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        return port


# ---------------------------------------------------------------------------
# Main: acquire id_token
# ---------------------------------------------------------------------------

async def acquire_idp_id_token(opts: IdpLoginOptions) -> str:
    """
    Acquire an id_token from the IdP: return cached if valid, otherwise run
    the full OIDC authorization_code + PKCE flow (one browser pop).
    """
    idp_issuer = opts.idp_issuer
    idp_client_id = opts.idp_client_id

    cached = get_cached_idp_id_token(idp_issuer)
    if cached:
        _log_mcp_debug("xaa", f"Using cached id_token for {idp_issuer}")
        return cached

    _log_mcp_debug("xaa", f"No cached id_token for {idp_issuer}; starting OIDC login")

    metadata = await discover_oidc(idp_issuer)
    port = opts.callback_port or await _find_available_port()
    redirect_uri = _build_redirect_uri(port)
    state = secrets.token_urlsafe(32)
    code_verifier = _generate_code_verifier()
    code_challenge = _generate_code_challenge(code_verifier)

    auth_endpoint = metadata.get("authorization_endpoint", "")
    if not auth_endpoint:
        raise Exception("XAA IdP: OIDC metadata missing authorization_endpoint")

    # Build authorization URL
    from urllib.parse import urlencode
    auth_params = {
        "response_type": "code",
        "client_id": idp_client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    authorization_url = f"{auth_endpoint}?{urlencode(auth_params)}"

    # Wait for the callback (fires browser after socket is bound)
    authorization_code = await _wait_for_callback(
        port=port,
        expected_state=state,
        abort_event=opts.abort_event,
        on_listening=lambda: (
            (opts.on_authorization_url(authorization_url) if opts.on_authorization_url else None)
            or (
                None if opts.skip_browser_open
                else _open_browser(authorization_url)
            )
        ),
    )

    # Exchange authorization code for tokens
    token_endpoint = metadata.get("token_endpoint", "")
    token_params: dict = {
        "grant_type": "authorization_code",
        "code": authorization_code,
        "redirect_uri": redirect_uri,
        "client_id": idp_client_id,
        "code_verifier": code_verifier,
    }
    if opts.idp_client_secret:
        token_params["client_secret"] = opts.idp_client_secret

    timeout = aiohttp.ClientTimeout(total=IDP_REQUEST_TIMEOUT_S)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            token_endpoint,
            data=token_params,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as resp:
            if not resp.ok:
                body = await resp.text()
                raise Exception(
                    f"XAA IdP: token exchange failed: HTTP {resp.status}: {body[:200]}"
                )
            tokens = await resp.json(content_type=None)

    id_token = tokens.get("id_token")
    if not id_token:
        raise Exception(
            "XAA IdP: token response missing id_token (check scope=openid)"
        )

    # Cache the id_token
    exp_from_jwt = _jwt_exp(id_token)
    if exp_from_jwt:
        expires_at = exp_from_jwt * 1000
    else:
        expires_at = int(time.time() * 1000) + (tokens.get("expires_in", 3600)) * 1000

    _save_idp_id_token(idp_issuer, id_token, expires_at)
    _log_mcp_debug(
        "xaa",
        f"Cached id_token for {idp_issuer} "
        f"(expires {time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(expires_at / 1000))}Z)",
    )

    return id_token
