"""
services/mcp/xaa.py — Cross-App Access (XAA) / Enterprise Managed Authorization.
Ported from services/mcp/xaa.ts (511 lines).

Obtains an MCP access token WITHOUT a browser consent screen by chaining:
  1. RFC 8693 Token Exchange at the IdP: id_token → ID-JAG
  2. RFC 7523 JWT Bearer Grant at the AS: ID-JAG → access_token

Spec refs:
  - ID-JAG (IETF draft): https://datatracker.ietf.org/doc/draft-ietf-oauth-identity-assertion-authz-grant/
  - MCP ext-auth (SEP-990): https://github.com/modelcontextprotocol/ext-auth
  - RFC 8693 (Token Exchange), RFC 7523 (JWT Bearer), RFC 9728 (PRM)
"""
from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urlparse

import aiohttp  # type: ignore

logger = logging.getLogger(__name__)

XAA_REQUEST_TIMEOUT_S = 30.0

TOKEN_EXCHANGE_GRANT = "urn:ietf:params:oauth:grant-type:token-exchange"
JWT_BEARER_GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"
ID_JAG_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:id-jag"
ID_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:id_token"

# Matches quoted values for known token-bearing keys (for redaction in logs).
_SENSITIVE_TOKEN_RE = re.compile(
    r'"(access_token|refresh_token|id_token|assertion|subject_token|client_secret)"\s*:\s*"[^"]*"'
)


def _log_mcp_debug(server_name: str, msg: str) -> None:
    try:
        from claude_code.utils.log import log_mcp_debug
        log_mcp_debug(server_name, msg)
    except (ImportError, Exception):
        logger.debug("[%s] %s", server_name, msg)


def _redact_tokens(raw: Any) -> str:
    """Redact token values from a string or JSON-serializable object."""
    if isinstance(raw, str):
        s = raw
    else:
        try:
            s = json.dumps(raw)
        except Exception:
            s = str(raw)
    return _SENSITIVE_TOKEN_RE.sub(lambda m: f'"{m.group(1)}":"[REDACTED]"', s)


def _normalize_url(url: str) -> str:
    """
    RFC 8414 §3.3 / RFC 9728 §3.3 identifier comparison.
    Roundtrip through URL for syntax-based normalization, then strip trailing slash.
    """
    try:
        parsed = urlparse(url)
        # Reconstruct with lowercased scheme + netloc
        normalized = parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=parsed.netloc.lower(),
        ).geturl()
        return normalized.rstrip("/")
    except Exception:
        return url.rstrip("/")


# ---------------------------------------------------------------------------
# XaaTokenExchangeError
# ---------------------------------------------------------------------------

class XaaTokenExchangeError(Exception):
    """
    Thrown by request_jwt_authorization_grant when the IdP token-exchange
    leg fails. Carries should_clear_id_token so callers can decide whether
    to drop the cached id_token:
      - 4xx / invalid_grant / invalid_token → clear it
      - 5xx → IdP is down, keep it
      - 200 with invalid body → protocol violation, clear it
    """
    def __init__(self, message: str, should_clear_id_token: bool) -> None:
        super().__init__(message)
        self.name = "XaaTokenExchangeError"
        self.should_clear_id_token = should_clear_id_token


# ---------------------------------------------------------------------------
# Layer 2: Discovery
# ---------------------------------------------------------------------------

@dataclass
class ProtectedResourceMetadata:
    resource: str
    authorization_servers: List[str]


@dataclass
class AuthorizationServerMetadata:
    issuer: str
    token_endpoint: str
    grant_types_supported: Optional[List[str]] = None
    token_endpoint_auth_methods_supported: Optional[List[str]] = None


async def discover_protected_resource(
    server_url: str,
    timeout_s: float = XAA_REQUEST_TIMEOUT_S,
    session: Optional[aiohttp.ClientSession] = None,
) -> ProtectedResourceMetadata:
    """
    RFC 9728 PRM discovery plus RFC 9728 §3.3 resource-mismatch validation.
    """
    # Construct PRM discovery URL: /.well-known/oauth-protected-resource
    base = server_url.rstrip("/")
    prm_url = f"{base}/.well-known/oauth-protected-resource"

    close_session = False
    if session is None:
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_s))
        close_session = True

    try:
        async with session.get(prm_url, headers={"Accept": "application/json"}) as resp:
            if not resp.ok:
                raise Exception(f"HTTP {resp.status} at {prm_url}")
            try:
                prm = await resp.json(content_type=None)
            except Exception:
                raise Exception(f"XAA: PRM discovery returned non-JSON at {prm_url}")
    except aiohttp.ClientError as e:
        raise Exception(f"XAA: PRM discovery failed: {e}") from e
    finally:
        if close_session:
            await session.close()

    resource = prm.get("resource")
    auth_servers = prm.get("authorization_servers") or []
    if not resource or not auth_servers:
        raise Exception(
            "XAA: PRM discovery failed: PRM missing resource or authorization_servers"
        )
    if _normalize_url(resource) != _normalize_url(server_url):
        raise Exception(
            f"XAA: PRM discovery failed: PRM resource mismatch: "
            f"expected {server_url}, got {resource}"
        )
    return ProtectedResourceMetadata(
        resource=resource,
        authorization_servers=auth_servers,
    )


async def discover_authorization_server(
    as_url: str,
    timeout_s: float = XAA_REQUEST_TIMEOUT_S,
    session: Optional[aiohttp.ClientSession] = None,
) -> AuthorizationServerMetadata:
    """
    AS metadata discovery (RFC 8414 + OIDC fallback), plus RFC 8414 §3.3
    issuer-mismatch validation.
    """
    # Try RFC 8414 /.well-known/oauth-authorization-server first,
    # then OIDC /.well-known/openid-configuration.
    base = as_url.rstrip("/")
    urls = [
        f"{base}/.well-known/oauth-authorization-server",
        f"{base}/.well-known/openid-configuration",
    ]

    close_session = False
    if session is None:
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_s))
        close_session = True

    meta = None
    last_err = None
    try:
        for url in urls:
            try:
                async with session.get(url, headers={"Accept": "application/json"}) as resp:
                    if resp.ok:
                        meta = await resp.json(content_type=None)
                        break
            except Exception as e:
                last_err = e
                continue
    finally:
        if close_session:
            await session.close()

    if not meta:
        raise Exception(
            f"XAA: AS metadata discovery failed: no valid metadata at {as_url}"
            + (f": {last_err}" if last_err else "")
        )

    issuer = meta.get("issuer")
    token_endpoint = meta.get("token_endpoint")

    if not issuer or not token_endpoint:
        raise Exception(
            f"XAA: AS metadata discovery failed: no valid metadata at {as_url}"
        )

    if _normalize_url(issuer) != _normalize_url(as_url):
        raise Exception(
            f"XAA: AS metadata discovery failed: issuer mismatch: "
            f"expected {as_url}, got {issuer}"
        )

    # RFC 8414 §3.3 / RFC 9728 §3 require HTTPS.
    if not token_endpoint.startswith("https://"):
        raise Exception(f"XAA: refusing non-HTTPS token endpoint: {token_endpoint}")

    return AuthorizationServerMetadata(
        issuer=issuer,
        token_endpoint=token_endpoint,
        grant_types_supported=meta.get("grant_types_supported"),
        token_endpoint_auth_methods_supported=meta.get(
            "token_endpoint_auth_methods_supported"
        ),
    )


# ---------------------------------------------------------------------------
# Layer 2: Exchange
# ---------------------------------------------------------------------------

@dataclass
class JwtAuthGrantResult:
    """Result of RFC 8693 token exchange: id_token → ID-JAG."""
    jwt_auth_grant: str
    expires_in: Optional[int] = None
    scope: Optional[str] = None


async def request_jwt_authorization_grant(
    *,
    token_endpoint: str,
    audience: str,
    resource: str,
    id_token: str,
    client_id: str,
    client_secret: Optional[str] = None,
    scope: Optional[str] = None,
    timeout_s: float = XAA_REQUEST_TIMEOUT_S,
    session: Optional[aiohttp.ClientSession] = None,
) -> JwtAuthGrantResult:
    """
    RFC 8693 Token Exchange at the IdP: id_token → ID-JAG.
    Validates issued_token_type is urn:ietf:params:oauth:token-type:id-jag.
    """
    params: Dict[str, str] = {
        "grant_type": TOKEN_EXCHANGE_GRANT,
        "requested_token_type": ID_JAG_TOKEN_TYPE,
        "audience": audience,
        "resource": resource,
        "subject_token": id_token,
        "subject_token_type": ID_TOKEN_TYPE,
        "client_id": client_id,
    }
    if client_secret:
        params["client_secret"] = client_secret
    if scope:
        params["scope"] = scope

    close_session = False
    if session is None:
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_s))
        close_session = True

    try:
        async with session.post(
            token_endpoint,
            data=params,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as resp:
            body_text = await resp.text()
            if not resp.ok:
                body_redacted = _redact_tokens(body_text)[:200]
                should_clear = resp.status < 500
                raise XaaTokenExchangeError(
                    f"XAA: token exchange failed: HTTP {resp.status}: {body_redacted}",
                    should_clear,
                )
            try:
                result = json.loads(body_text)
            except json.JSONDecodeError:
                raise XaaTokenExchangeError(
                    f"XAA: token exchange returned non-JSON (captive portal?) at {token_endpoint}",
                    False,
                )
    except XaaTokenExchangeError:
        raise
    except aiohttp.ClientError as e:
        raise XaaTokenExchangeError(
            f"XAA: token exchange request failed: {e}", False
        )
    finally:
        if close_session:
            await session.close()

    access_token = result.get("access_token")
    if not access_token:
        raise XaaTokenExchangeError(
            f"XAA: token exchange response missing access_token: {_redact_tokens(result)}",
            True,
        )
    issued_type = result.get("issued_token_type")
    if issued_type != ID_JAG_TOKEN_TYPE:
        raise XaaTokenExchangeError(
            f"XAA: token exchange returned unexpected issued_token_type: {issued_type}",
            True,
        )

    return JwtAuthGrantResult(
        jwt_auth_grant=access_token,
        expires_in=result.get("expires_in"),
        scope=result.get("scope"),
    )


@dataclass
class XaaTokenResult:
    access_token: str
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    scope: Optional[str] = None
    refresh_token: Optional[str] = None


@dataclass
class XaaResult:
    access_token: str
    token_type: str
    authorization_server_url: str
    expires_in: Optional[int] = None
    scope: Optional[str] = None
    refresh_token: Optional[str] = None


async def exchange_jwt_auth_grant(
    *,
    token_endpoint: str,
    assertion: str,
    client_id: str,
    client_secret: str,
    auth_method: str = "client_secret_basic",
    scope: Optional[str] = None,
    timeout_s: float = XAA_REQUEST_TIMEOUT_S,
    session: Optional[aiohttp.ClientSession] = None,
) -> XaaTokenResult:
    """
    RFC 7523 JWT Bearer Grant at the AS: ID-JAG → access_token.
    auth_method defaults to 'client_secret_basic' (SEP-990 conformance).
    """
    params: Dict[str, str] = {
        "grant_type": JWT_BEARER_GRANT,
        "assertion": assertion,
    }
    if scope:
        params["scope"] = scope

    headers: Dict[str, str] = {
        "Content-Type": "application/x-www-form-urlencoded",
    }
    if auth_method == "client_secret_basic":
        raw = f"{client_id}:{client_secret}"
        basic_auth = base64.b64encode(raw.encode()).decode()
        headers["Authorization"] = f"Basic {basic_auth}"
    else:
        # client_secret_post
        params["client_id"] = client_id
        params["client_secret"] = client_secret

    close_session = False
    if session is None:
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_s))
        close_session = True

    try:
        async with session.post(token_endpoint, data=params, headers=headers) as resp:
            body_text = await resp.text()
            if not resp.ok:
                body_redacted = _redact_tokens(body_text)[:200]
                raise Exception(
                    f"XAA: jwt-bearer grant failed: HTTP {resp.status}: {body_redacted}"
                )
            try:
                result = json.loads(body_text)
            except json.JSONDecodeError:
                raise Exception(
                    f"XAA: jwt-bearer grant returned non-JSON (captive portal?) at {token_endpoint}"
                )
    except Exception:
        raise
    finally:
        if close_session:
            await session.close()

    access_token = result.get("access_token")
    if not access_token:
        raise Exception(
            f"XAA: jwt-bearer response missing access_token: {_redact_tokens(result)}"
        )

    return XaaTokenResult(
        access_token=access_token,
        token_type=result.get("token_type", "Bearer"),
        expires_in=result.get("expires_in"),
        scope=result.get("scope"),
        refresh_token=result.get("refresh_token"),
    )


# ---------------------------------------------------------------------------
# Layer 3: Orchestrator
# ---------------------------------------------------------------------------

@dataclass
class XaaConfig:
    """Config needed to run the full XAA orchestrator."""
    client_id: str
    client_secret: str
    idp_client_id: str
    idp_id_token: str
    idp_token_endpoint: str
    idp_client_secret: Optional[str] = None


async def perform_cross_app_access(
    server_url: str,
    config: XaaConfig,
    server_name: str = "xaa",
    abort_event=None,   # asyncio.Event — if set, abort
) -> XaaResult:
    """
    Full XAA flow: PRM → AS metadata → token-exchange → jwt-bearer → access_token.
    Thin composition of the four Layer-2 ops.

    @param server_url: The MCP server URL
    @param config: IdP + AS credentials
    @param server_name: Server name for debug logging
    """
    timeout = aiohttp.ClientTimeout(total=XAA_REQUEST_TIMEOUT_S)
    async with aiohttp.ClientSession(timeout=timeout) as sess:

        _log_mcp_debug(server_name, f"XAA: discovering PRM for {server_url}")
        prm = await discover_protected_resource(server_url, session=sess)
        _log_mcp_debug(
            server_name,
            f"XAA: discovered resource={prm.resource} "
            f"ASes=[{', '.join(prm.authorization_servers)}]",
        )

        # Try each advertised AS in order.
        as_meta: Optional[AuthorizationServerMetadata] = None
        as_errors: List[str] = []

        for as_url in prm.authorization_servers:
            try:
                candidate = await discover_authorization_server(as_url, session=sess)
            except Exception as e:
                as_errors.append(f"{as_url}: {e}")
                continue

            supported = candidate.grant_types_supported
            if supported and JWT_BEARER_GRANT not in supported:
                as_errors.append(
                    f"{as_url}: does not advertise jwt-bearer grant "
                    f"(supported: {', '.join(supported)})"
                )
                continue

            as_meta = candidate
            break

        if not as_meta:
            raise Exception(
                f"XAA: no authorization server supports jwt-bearer. "
                f"Tried: {'; '.join(as_errors)}"
            )

        # Choose auth method from what the AS advertises.
        auth_methods = as_meta.token_endpoint_auth_methods_supported
        if (
            auth_methods
            and "client_secret_basic" not in auth_methods
            and "client_secret_post" in auth_methods
        ):
            auth_method = "client_secret_post"
        else:
            auth_method = "client_secret_basic"

        _log_mcp_debug(
            server_name,
            f"XAA: AS issuer={as_meta.issuer} "
            f"token_endpoint={as_meta.token_endpoint} "
            f"auth_method={auth_method}",
        )

        _log_mcp_debug(server_name, "XAA: exchanging id_token for ID-JAG at IdP")
        jag = await request_jwt_authorization_grant(
            token_endpoint=config.idp_token_endpoint,
            audience=as_meta.issuer,
            resource=prm.resource,
            id_token=config.idp_id_token,
            client_id=config.idp_client_id,
            client_secret=config.idp_client_secret,
            session=sess,
        )
        _log_mcp_debug(server_name, "XAA: ID-JAG obtained")

        _log_mcp_debug(server_name, "XAA: exchanging ID-JAG for access_token at AS")
        tokens = await exchange_jwt_auth_grant(
            token_endpoint=as_meta.token_endpoint,
            assertion=jag.jwt_auth_grant,
            client_id=config.client_id,
            client_secret=config.client_secret,
            auth_method=auth_method,
            session=sess,
        )
        _log_mcp_debug(server_name, "XAA: access_token obtained")

    return XaaResult(
        access_token=tokens.access_token,
        token_type=tokens.token_type,
        authorization_server_url=as_meta.issuer,
        expires_in=tokens.expires_in,
        scope=tokens.scope,
        refresh_token=tokens.refresh_token,
    )
