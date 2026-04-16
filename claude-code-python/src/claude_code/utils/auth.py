"""auth.py — Authentication utilities.

Python port of utils/auth.ts (2007 lines).

Platform-specific stubs:
- macOS Keychain: subprocess `security` CLI (TODO: full impl)
- AWS STS: stub (TODO)
- GCP credentials: stub (TODO)
- OAuth token refresh: stub (interface preserved)
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, Literal, Optional, Tuple, TypedDict, Union

# ---------------------------------------------------------------------------
# Local imports — use what actually exists in the project
# ---------------------------------------------------------------------------
from claude_code.utils.config import get_config_value, set_config_value, get_all_config
from claude_code.utils.env_utils import (
    get_claude_config_home_dir,
    is_bare_mode,
    is_env_truthy,
)
from claude_code.utils.errors import error_message
from claude_code.utils.debug import debug_log
from claude_code.utils.log import log_error
from claude_code.bootstrap.state import (
    get_is_non_interactive_session,
    prefer_third_party_authentication,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_API_KEY_HELPER_TTL = 5 * 60 * 1000  # 5 minutes in ms
DEFAULT_AWS_STS_TTL = 60 * 60 * 1000  # 1 hour in ms
DEFAULT_GCP_CREDENTIAL_TTL = 60 * 60 * 1000  # 1 hour in ms
GCP_CREDENTIALS_CHECK_TIMEOUT_MS = 5_000  # 5 seconds
AWS_AUTH_REFRESH_TIMEOUT_MS = 3 * 60  # seconds (subprocess timeout)
GCP_AUTH_REFRESH_TIMEOUT_MS = 3 * 60  # seconds
DEFAULT_OTEL_HEADERS_DEBOUNCE_MS = 29 * 60 * 1000  # 29 minutes in ms
CLAUDE_AI_PROFILE_SCOPE = "user:profile"

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

ApiKeySource = Literal[
    "ANTHROPIC_API_KEY",
    "apiKeyHelper",
    "/login managed key",
    "none",
]


@dataclass
class OAuthTokens:
    access_token: str
    refresh_token: Optional[str]
    expires_at: Optional[int]  # Unix timestamp ms
    scopes: list[str]
    subscription_type: Optional[str]
    rate_limit_tier: Optional[str]


@dataclass
class AccountInfo:
    organization_name: Optional[str] = None
    email_address: Optional[str] = None
    billing_type: Optional[str] = None


SubscriptionType = Optional[Literal["max", "pro", "team", "enterprise"]]


class OrgValidationResult(TypedDict, total=False):
    valid: bool
    message: str


class UserAccountInfo(TypedDict, total=False):
    subscription: str
    token_source: str
    api_key_source: str
    organization: str
    email: str


# ---------------------------------------------------------------------------
# Helpers: stub analytics log_event
# ---------------------------------------------------------------------------

def _log_event(event_name: str, metadata: dict) -> None:
    """Stub for analytics logEvent — no-op in Python port."""
    debug_log(f"[analytics] {event_name}", **metadata)


# ---------------------------------------------------------------------------
# Helpers: stub settings access
# ---------------------------------------------------------------------------

def _get_settings_deprecated() -> dict:
    """Stub for getSettings_DEPRECATED — reads global config."""
    try:
        cfg = get_all_config()
        # settings may be nested under 'settings' key or flat
        return cfg.get("settings", cfg)
    except Exception:
        return {}


def _get_settings_for_source(source: str) -> Optional[dict]:
    """Stub for getSettingsForSource."""
    try:
        cfg = get_all_config()
        return cfg.get(source)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helpers: global config abstraction
# ---------------------------------------------------------------------------

def _get_global_config() -> dict:
    """Read the full global config dict."""
    return get_all_config()


def _save_global_config(updater: Callable[[dict], dict]) -> None:
    """Apply updater function to config and save."""
    from claude_code.utils.config import _load, _save
    data = _load()
    new_data = updater(data)
    _save(new_data)


def _check_has_trust_dialog_accepted() -> bool:
    """Check if trust dialog has been accepted."""
    cfg = _get_global_config()
    return bool(cfg.get("trustDialogAccepted", False))


# ---------------------------------------------------------------------------
# Helpers: stub for file descriptor token reads
# ---------------------------------------------------------------------------

def _get_api_key_from_file_descriptor() -> Optional[str]:
    """Stub: getApiKeyFromFileDescriptor. TODO: implement real FD read."""
    key_fd = os.environ.get("CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR")
    if not key_fd:
        state_key = None
        try:
            from claude_code.bootstrap.state import get_api_key_from_fd
            state_key = get_api_key_from_fd()
        except Exception:
            pass
        return state_key
    # Try reading from the FD number
    try:
        fd = int(key_fd)
        with os.fdopen(os.dup(fd), "r") as f:
            return f.read().strip() or None
    except Exception:
        return None


def _get_oauth_token_from_file_descriptor() -> Optional[str]:
    """Stub: getOAuthTokenFromFileDescriptor. TODO: implement real FD read."""
    try:
        from claude_code.bootstrap.state import get_oauth_token_from_fd
        token = get_oauth_token_from_fd()
        if token:
            return token
    except Exception:
        pass
    token_fd = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR")
    if not token_fd:
        return None
    try:
        fd = int(token_fd)
        with os.fdopen(os.dup(fd), "r") as f:
            return f.read().strip() or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helpers: stub for macOS Keychain / secure storage
# ---------------------------------------------------------------------------

def _get_mac_os_keychain_storage_service_name() -> str:
    """Stub: getMacOsKeychainStorageServiceName."""
    return os.environ.get("CLAUDE_KEYCHAIN_SERVICE", "claude-code")


def _get_username() -> str:
    """Get current username."""
    return os.environ.get("USER", os.environ.get("USERNAME", "user"))


def _get_legacy_api_key_prefetch_result() -> Optional[str]:
    """Stub: getLegacyApiKeyPrefetchResult — always None in Python port."""
    return None


def _clear_legacy_api_key_prefetch() -> None:
    """Stub: clearLegacyApiKeyPrefetch."""
    pass


def _clear_keychain_cache() -> None:
    """Stub: clearKeychainCache."""
    # Invalidate the memoized keychain reader
    get_api_key_from_config_or_macos_keychain.cache_clear()


def _maybe_remove_api_key_from_macos_keychain_throws() -> None:
    """Stub: maybeRemoveApiKeyFromMacOSKeychainThrows. TODO: real impl."""
    if sys.platform != "darwin":
        return
    service = _get_mac_os_keychain_storage_service_name()
    username = _get_username()
    try:
        subprocess.run(
            ["security", "delete-generic-password", "-a", username, "-s", service],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass


def _normalize_api_key_for_config(api_key: str) -> str:
    """Stub: normalizeApiKeyForConfig — return first 8 chars as identifier."""
    return api_key[:8] if len(api_key) >= 8 else api_key


# ---------------------------------------------------------------------------
# Helpers: stub for betas / tool schema cache
# ---------------------------------------------------------------------------

def _clear_betas_caches() -> None:
    """Stub: clearBetasCaches."""
    pass


def _clear_tool_schema_cache() -> None:
    """Stub: clearToolSchemaCache."""
    pass


# ---------------------------------------------------------------------------
# Helpers: stub for getAPIProvider
# ---------------------------------------------------------------------------

def _get_api_provider() -> str:
    """Stub: getAPIProvider."""
    if is_env_truthy(os.environ.get("CLAUDE_CODE_USE_BEDROCK")):
        return "bedrock"
    if is_env_truthy(os.environ.get("CLAUDE_CODE_USE_VERTEX")):
        return "vertex"
    if is_env_truthy(os.environ.get("CLAUDE_CODE_USE_FOUNDRY")):
        return "foundry"
    return "firstParty"


# ---------------------------------------------------------------------------
# Helpers: stub for mock subscription
# ---------------------------------------------------------------------------

def _should_use_mock_subscription() -> bool:
    """Stub: shouldUseMockSubscription."""
    return False


def _get_mock_subscription_type() -> Optional[str]:
    """Stub: getMockSubscriptionType."""
    return None


# ---------------------------------------------------------------------------
# Helpers: stub lockfile
# ---------------------------------------------------------------------------

class _LockfileLock:
    """Simple file-based lock context manager."""

    def __init__(self, lock_path: str):
        self._lock_path = lock_path
        self._acquired = False

    async def __aenter__(self):
        # simple spin-lock with timeout
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
                self._acquired = True
                return self
            except FileExistsError:
                await asyncio.sleep(0.1)
        err = OSError("ELOCKED")
        err.strerror = "ELOCKED"
        raise err

    async def __aexit__(self, *_):
        if self._acquired:
            try:
                os.unlink(self._lock_path)
            except OSError:
                pass


async def _acquire_lock(directory: str):
    """Acquire a filesystem lock on the given directory."""
    lock_path = os.path.join(directory, ".lock")
    lock = _LockfileLock(lock_path)
    ctx = await lock.__aenter__()

    async def release():
        await lock.__aexit__(None, None, None)

    return release


# ---------------------------------------------------------------------------
# OAuth helpers stubs
# ---------------------------------------------------------------------------

def _is_oauth_token_expired(expires_at: Optional[int]) -> bool:
    """Check if OAuth token is expired. expires_at is Unix ms."""
    if expires_at is None:
        return False
    # consider expired if within 60s of expiry
    return time.time() * 1000 >= (expires_at - 60_000)


def _should_use_claude_ai_auth(scopes: Optional[list]) -> bool:
    """Check if scopes indicate claude.ai auth."""
    if not scopes:
        return False
    return any(s in scopes for s in ("user:inference", "user:profile", "user:file_upload"))


async def _refresh_oauth_token_stub(
    refresh_token: str,
    opts: Optional[dict] = None,
) -> OAuthTokens:
    """Stub: refreshOAuthToken. TODO: real OAuth refresh."""
    raise NotImplementedError("OAuth token refresh not yet implemented")


async def _get_oauth_profile_from_oauth_token(
    access_token: str,
) -> Optional[dict]:
    """Stub: getOauthProfileFromOauthToken. TODO: real profile fetch."""
    return None


# ---------------------------------------------------------------------------
# Helpers: stub for AWS STS
# ---------------------------------------------------------------------------

async def _check_sts_caller_identity() -> None:
    """Stub: checkStsCallerIdentity. TODO: real AWS STS call."""
    raise NotImplementedError("AWS STS not yet implemented")


async def _clear_aws_ini_cache() -> None:
    """Stub: clearAwsIniCache."""
    pass


def _is_valid_aws_sts_output(data: Any) -> bool:
    """Stub: isValidAwsStsOutput."""
    if not isinstance(data, dict):
        return False
    creds = data.get("Credentials", {})
    return all(k in creds for k in ("AccessKeyId", "SecretAccessKey", "SessionToken"))


# ---------------------------------------------------------------------------
# Helpers: execSyncWithDefaults
# ---------------------------------------------------------------------------

def _exec_sync_with_defaults(cmd: str, timeout: int = 10000) -> Optional[str]:
    """Synchronous shell command, returns stdout or None."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout / 1000,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helpers: stub secure storage
# ---------------------------------------------------------------------------

def _get_secure_storage() -> dict:
    """Stub: getSecureStorage — returns a dict with name and read/update/readAsync."""
    cred_file = Path(get_claude_config_home_dir()) / ".credentials.json"

    def read() -> Optional[dict]:
        try:
            return json.loads(cred_file.read_text())
        except Exception:
            return None

    async def read_async() -> Optional[dict]:
        return read()

    def update(data: dict) -> dict:
        try:
            cred_file.parent.mkdir(parents=True, exist_ok=True)
            cred_file.write_text(json.dumps(data, indent=2))
            return {"success": True}
        except Exception as e:
            return {"success": False, "warning": str(e)}

    return {
        "name": "file",
        "read": read,
        "read_async": read_async,
        "update": update,
    }


# ---------------------------------------------------------------------------
# isManagedOAuthContext
# ---------------------------------------------------------------------------

def _is_managed_oauth_context() -> bool:
    return (
        is_env_truthy(os.environ.get("CLAUDE_CODE_REMOTE"))
        or os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "claude-desktop"
    )


# ---------------------------------------------------------------------------
# isAnthropicAuthEnabled
# ---------------------------------------------------------------------------

def is_anthropic_auth_enabled() -> bool:
    """Whether we support direct 1P auth. Port of isAnthropicAuthEnabled."""
    # Hunyuan mode: skip Anthropic OAuth
    if os.environ.get("HUNYUAN_API_KEY"):
        return False

    # --bare: API-key-only, never OAuth
    if is_bare_mode():
        return False

    # UNIX socket tunnel
    if os.environ.get("ANTHROPIC_UNIX_SOCKET"):
        return bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))

    is_3p = (
        is_env_truthy(os.environ.get("CLAUDE_CODE_USE_BEDROCK"))
        or is_env_truthy(os.environ.get("CLAUDE_CODE_USE_VERTEX"))
        or is_env_truthy(os.environ.get("CLAUDE_CODE_USE_FOUNDRY"))
    )

    settings = _get_settings_deprecated()
    api_key_helper = settings.get("apiKeyHelper")
    has_external_auth_token = (
        os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or api_key_helper
        or os.environ.get("CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR")
    )

    result = get_anthropic_api_key_with_source(skip_retrieving_key_from_api_key_helper=True)
    api_key_source = result["source"]
    has_external_api_key = api_key_source in ("ANTHROPIC_API_KEY", "apiKeyHelper")

    should_disable = (
        is_3p
        or (has_external_auth_token and not _is_managed_oauth_context())
        or (has_external_api_key and not _is_managed_oauth_context())
    )

    return not should_disable


# ---------------------------------------------------------------------------
# getAuthTokenSource
# ---------------------------------------------------------------------------

def get_auth_token_source() -> dict:
    """Where the auth token is being sourced from. Port of getAuthTokenSource."""
    if is_bare_mode():
        if get_configured_api_key_helper():
            return {"source": "apiKeyHelper", "has_token": True}
        return {"source": "none", "has_token": False}

    if os.environ.get("ANTHROPIC_AUTH_TOKEN") and not _is_managed_oauth_context():
        return {"source": "ANTHROPIC_AUTH_TOKEN", "has_token": True}

    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return {"source": "CLAUDE_CODE_OAUTH_TOKEN", "has_token": True}

    oauth_token_from_fd = _get_oauth_token_from_file_descriptor()
    if oauth_token_from_fd:
        if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR"):
            return {"source": "CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR", "has_token": True}
        return {"source": "CCR_OAUTH_TOKEN_FILE", "has_token": True}

    api_key_helper = get_configured_api_key_helper()
    if api_key_helper and not _is_managed_oauth_context():
        return {"source": "apiKeyHelper", "has_token": True}

    oauth_tokens = get_claude_ai_oauth_tokens()
    if _should_use_claude_ai_auth(oauth_tokens.scopes if oauth_tokens else None) and (
        oauth_tokens and oauth_tokens.access_token
    ):
        return {"source": "claude.ai", "has_token": True}

    return {"source": "none", "has_token": False}


# ---------------------------------------------------------------------------
# getAnthropicApiKey
# ---------------------------------------------------------------------------

def get_anthropic_api_key() -> Optional[str]:
    """Return Anthropic API key. Port of getAnthropicApiKey."""
    if os.environ.get("HUNYUAN_API_KEY"):
        return os.environ["HUNYUAN_API_KEY"]
    result = get_anthropic_api_key_with_source()
    return result["key"]


def has_anthropic_api_key_auth() -> bool:
    """Port of hasAnthropicApiKeyAuth."""
    result = get_anthropic_api_key_with_source(skip_retrieving_key_from_api_key_helper=True)
    return result["key"] is not None and result["source"] != "none"


def _is_running_on_homespace() -> bool:
    """Check if running on homespace."""
    try:
        from claude_code.utils.env_utils import is_running_on_homespace
        return is_running_on_homespace()
    except (ImportError, AttributeError):
        return False


def get_anthropic_api_key_with_source(
    skip_retrieving_key_from_api_key_helper: bool = False,
) -> dict:
    """Return {key, source}. Port of getAnthropicApiKeyWithSource."""
    if is_bare_mode():
        if os.environ.get("ANTHROPIC_API_KEY"):
            return {"key": os.environ["ANTHROPIC_API_KEY"], "source": "ANTHROPIC_API_KEY"}
        if get_configured_api_key_helper():
            return {
                "key": None if skip_retrieving_key_from_api_key_helper else get_api_key_from_api_key_helper_cached(),
                "source": "apiKeyHelper",
            }
        return {"key": None, "source": "none"}

    api_key_env = None if _is_running_on_homespace() else os.environ.get("ANTHROPIC_API_KEY")

    if prefer_third_party_authentication() and api_key_env:
        return {"key": api_key_env, "source": "ANTHROPIC_API_KEY"}

    if is_env_truthy(os.environ.get("CI")) or os.environ.get("NODE_ENV") == "test":
        api_key_from_fd = _get_api_key_from_file_descriptor()
        if api_key_from_fd:
            return {"key": api_key_from_fd, "source": "ANTHROPIC_API_KEY"}

        if (
            not api_key_env
            and not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
            and not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR")
        ):
            raise RuntimeError(
                "ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN env var is required"
            )

        if api_key_env:
            return {"key": api_key_env, "source": "ANTHROPIC_API_KEY"}

        return {"key": None, "source": "none"}

    # Check env key against approved list
    if api_key_env:
        cfg = _get_global_config()
        approved = cfg.get("customApiKeyResponses", {}).get("approved", [])
        if _normalize_api_key_for_config(api_key_env) in approved:
            return {"key": api_key_env, "source": "ANTHROPIC_API_KEY"}

    # Check FD
    api_key_from_fd = _get_api_key_from_file_descriptor()
    if api_key_from_fd:
        return {"key": api_key_from_fd, "source": "ANTHROPIC_API_KEY"}

    # apiKeyHelper
    api_key_helper_cmd = get_configured_api_key_helper()
    if api_key_helper_cmd:
        if skip_retrieving_key_from_api_key_helper:
            return {"key": None, "source": "apiKeyHelper"}
        return {"key": get_api_key_from_api_key_helper_cached(), "source": "apiKeyHelper"}

    # Keychain / config
    from_keychain = get_api_key_from_config_or_macos_keychain()
    if from_keychain:
        return from_keychain

    return {"key": None, "source": "none"}


# ---------------------------------------------------------------------------
# getConfiguredApiKeyHelper
# ---------------------------------------------------------------------------

def get_configured_api_key_helper() -> Optional[str]:
    """Port of getConfiguredApiKeyHelper."""
    if is_bare_mode():
        s = _get_settings_for_source("flagSettings")
        return s.get("apiKeyHelper") if s else None
    merged = _get_settings_deprecated()
    return merged.get("apiKeyHelper")


def _is_api_key_helper_from_project_or_local_settings() -> bool:
    """Port of isApiKeyHelperFromProjectOrLocalSettings."""
    api_key_helper = get_configured_api_key_helper()
    if not api_key_helper:
        return False
    project = _get_settings_for_source("projectSettings")
    local = _get_settings_for_source("localSettings")
    return (project and project.get("apiKeyHelper") == api_key_helper) or (
        local and local.get("apiKeyHelper") == api_key_helper
    )


def _get_configured_aws_auth_refresh() -> Optional[str]:
    merged = _get_settings_deprecated()
    return merged.get("awsAuthRefresh")


def is_aws_auth_refresh_from_project_settings() -> bool:
    """Port of isAwsAuthRefreshFromProjectSettings."""
    aws_auth_refresh = _get_configured_aws_auth_refresh()
    if not aws_auth_refresh:
        return False
    project = _get_settings_for_source("projectSettings")
    local = _get_settings_for_source("localSettings")
    return (project and project.get("awsAuthRefresh") == aws_auth_refresh) or (
        local and local.get("awsAuthRefresh") == aws_auth_refresh
    )


def _get_configured_aws_credential_export() -> Optional[str]:
    merged = _get_settings_deprecated()
    return merged.get("awsCredentialExport")


def is_aws_credential_export_from_project_settings() -> bool:
    """Port of isAwsCredentialExportFromProjectSettings."""
    aws_cred_export = _get_configured_aws_credential_export()
    if not aws_cred_export:
        return False
    project = _get_settings_for_source("projectSettings")
    local = _get_settings_for_source("localSettings")
    return (project and project.get("awsCredentialExport") == aws_cred_export) or (
        local and local.get("awsCredentialExport") == aws_cred_export
    )


# ---------------------------------------------------------------------------
# calculateApiKeyHelperTTL
# ---------------------------------------------------------------------------

def calculate_api_key_helper_ttl() -> int:
    """Port of calculateApiKeyHelperTTL. Returns ms."""
    env_ttl = os.environ.get("CLAUDE_CODE_API_KEY_HELPER_TTL_MS")
    if env_ttl:
        try:
            parsed = int(env_ttl)
            if parsed >= 0:
                return parsed
        except ValueError:
            debug_log(
                f"CLAUDE_CODE_API_KEY_HELPER_TTL_MS is not a valid number: {env_ttl}"
            )
    return DEFAULT_API_KEY_HELPER_TTL


# ---------------------------------------------------------------------------
# API Key Helper async cache
# ---------------------------------------------------------------------------

_api_key_helper_cache: Optional[dict] = None  # {value: str, timestamp: int}
_api_key_helper_inflight: Optional[dict] = None  # {task, started_at}
_api_key_helper_epoch: int = 0


def get_api_key_helper_elapsed_ms() -> int:
    """Port of getApiKeyHelperElapsedMs."""
    if _api_key_helper_inflight and _api_key_helper_inflight.get("started_at"):
        return int(time.time() * 1000) - _api_key_helper_inflight["started_at"]
    return 0


async def get_api_key_from_api_key_helper(
    is_non_interactive_session: bool,
) -> Optional[str]:
    """Port of getApiKeyFromApiKeyHelper (async)."""
    global _api_key_helper_inflight

    if not get_configured_api_key_helper():
        return None

    ttl = calculate_api_key_helper_ttl()
    now_ms = int(time.time() * 1000)

    if _api_key_helper_cache:
        if now_ms - _api_key_helper_cache["timestamp"] < ttl:
            return _api_key_helper_cache["value"]
        # Stale — SWR: return stale, refresh in background
        if not _api_key_helper_inflight:
            epoch = _api_key_helper_epoch
            task = asyncio.create_task(
                _run_and_cache(is_non_interactive_session, False, epoch)
            )
            _api_key_helper_inflight = {"task": task, "started_at": None}
        return _api_key_helper_cache["value"]

    # Cold cache
    if _api_key_helper_inflight:
        return await _api_key_helper_inflight["task"]

    epoch = _api_key_helper_epoch
    task = asyncio.create_task(
        _run_and_cache(is_non_interactive_session, True, epoch)
    )
    _api_key_helper_inflight = {"task": task, "started_at": now_ms}
    return await task


async def _run_and_cache(
    is_non_interactive_session: bool,
    is_cold: bool,
    epoch: int,
) -> Optional[str]:
    global _api_key_helper_cache, _api_key_helper_inflight
    try:
        value = await _execute_api_key_helper(is_non_interactive_session)
        if epoch != _api_key_helper_epoch:
            return value
        if value is not None:
            _api_key_helper_cache = {"value": value, "timestamp": int(time.time() * 1000)}
        return value
    except Exception as e:
        if epoch != _api_key_helper_epoch:
            return " "
        detail = str(e)
        print(f"\033[31mapiKeyHelper failed: {detail}\033[0m", file=sys.stderr)
        debug_log(f"Error getting API key from apiKeyHelper: {detail}")
        # SWR path: keep stale value on transient failure
        if not is_cold and _api_key_helper_cache and _api_key_helper_cache["value"] != " ":
            _api_key_helper_cache = {
                **_api_key_helper_cache,
                "timestamp": int(time.time() * 1000),
            }
            return _api_key_helper_cache["value"]
        # Cold or prior error — sentinel
        _api_key_helper_cache = {"value": " ", "timestamp": int(time.time() * 1000)}
        return " "
    finally:
        if epoch == _api_key_helper_epoch:
            _api_key_helper_inflight = None


async def _execute_api_key_helper(
    is_non_interactive_session: bool,
) -> Optional[str]:
    """Port of _executeApiKeyHelper."""
    api_key_helper = get_configured_api_key_helper()
    if not api_key_helper:
        return None

    if _is_api_key_helper_from_project_or_local_settings():
        has_trust = _check_has_trust_dialog_accepted()
        if not has_trust and not is_non_interactive_session:
            err = RuntimeError(
                "Security: apiKeyHelper executed before workspace trust is confirmed."
            )
            log_error(err)
            _log_event("tengu_apiKeyHelper_missing_trust11", {})
            return None

    proc = await asyncio.create_subprocess_shell(
        api_key_helper,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=10 * 60
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("timed out")

    if proc.returncode != 0:
        why = f"exited {proc.returncode}"
        stderr_text = stderr.decode().strip() if stderr else ""
        raise RuntimeError(f"{why}: {stderr_text}" if stderr_text else why)

    stdout_text = stdout.decode().strip() if stdout else ""
    if not stdout_text:
        raise RuntimeError("did not return a value")
    return stdout_text


def get_api_key_from_api_key_helper_cached() -> Optional[str]:
    """Sync cache reader — port of getApiKeyFromApiKeyHelperCached."""
    return _api_key_helper_cache["value"] if _api_key_helper_cache else None


def clear_api_key_helper_cache() -> None:
    """Port of clearApiKeyHelperCache."""
    global _api_key_helper_epoch, _api_key_helper_cache, _api_key_helper_inflight
    _api_key_helper_epoch += 1
    _api_key_helper_cache = None
    _api_key_helper_inflight = None


def prefetch_api_key_from_api_key_helper_if_safe(
    is_non_interactive_session: bool,
) -> None:
    """Port of prefetchApiKeyFromApiKeyHelperIfSafe."""
    if (
        _is_api_key_helper_from_project_or_local_settings()
        and not _check_has_trust_dialog_accepted()
    ):
        return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(
                get_api_key_from_api_key_helper(is_non_interactive_session)
            )
    except RuntimeError:
        pass


# ---------------------------------------------------------------------------
# AWS auth refresh
# ---------------------------------------------------------------------------

async def _run_aws_auth_refresh() -> bool:
    """Port of runAwsAuthRefresh (internal)."""
    aws_auth_refresh = _get_configured_aws_auth_refresh()
    if not aws_auth_refresh:
        return False

    if is_aws_auth_refresh_from_project_settings():
        has_trust = _check_has_trust_dialog_accepted()
        if not has_trust and not get_is_non_interactive_session():
            err = RuntimeError(
                "Security: awsAuthRefresh executed before workspace trust is confirmed."
            )
            log_error(err)
            _log_event("tengu_awsAuthRefresh_missing_trust", {})
            return False

    try:
        debug_log("Fetching AWS caller identity for AWS auth refresh command")
        await _check_sts_caller_identity()
        debug_log("Fetched AWS caller identity, skipping AWS auth refresh command")
        return False
    except NotImplementedError:
        # STS stub — proceed with refresh
        return await refresh_aws_auth(aws_auth_refresh)
    except Exception:
        return await refresh_aws_auth(aws_auth_refresh)


async def refresh_aws_auth(aws_auth_refresh: str) -> bool:
    """Port of refreshAwsAuth. Streams output in real-time."""
    debug_log("Running AWS auth refresh command")
    try:
        proc = await asyncio.create_subprocess_shell(
            aws_auth_refresh,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=AWS_AUTH_REFRESH_TIMEOUT_MS
            )
        except asyncio.TimeoutError:
            proc.kill()
            print(
                "\033[31mAWS auth refresh timed out after 3 minutes.\033[0m",
                file=sys.stderr,
            )
            return False

        if proc.returncode == 0:
            debug_log("AWS auth refresh completed successfully")
            return True
        else:
            print(
                "\033[31mError running awsAuthRefresh (in settings or ~/.claude.json)\033[0m",
                file=sys.stderr,
            )
            return False
    except Exception as e:
        log_error(e)
        return False


# ---------------------------------------------------------------------------
# AWS credential export
# ---------------------------------------------------------------------------

async def _get_aws_creds_from_credential_export() -> Optional[dict]:
    """Port of getAwsCredsFromCredentialExport."""
    aws_credential_export = _get_configured_aws_credential_export()
    if not aws_credential_export:
        return None

    if is_aws_credential_export_from_project_settings():
        has_trust = _check_has_trust_dialog_accepted()
        if not has_trust and not get_is_non_interactive_session():
            err = RuntimeError(
                "Security: awsCredentialExport executed before workspace trust is confirmed."
            )
            log_error(err)
            _log_event("tengu_awsCredentialExport_missing_trust", {})
            return None

    try:
        debug_log("Fetching AWS caller identity for credential export command")
        await _check_sts_caller_identity()
        debug_log("Fetched AWS caller identity, skipping AWS credential export command")
        return None
    except (NotImplementedError, Exception):
        pass

    try:
        debug_log("Running AWS credential export command")
        proc = await asyncio.create_subprocess_shell(
            aws_credential_export,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0 or not stdout:
            raise RuntimeError("awsCredentialExport did not return a valid value")

        aws_output = json.loads(stdout.decode().strip())
        if not _is_valid_aws_sts_output(aws_output):
            raise RuntimeError(
                "awsCredentialExport did not return valid AWS STS output structure"
            )

        debug_log("AWS credentials retrieved from awsCredentialExport")
        return {
            "access_key_id": aws_output["Credentials"]["AccessKeyId"],
            "secret_access_key": aws_output["Credentials"]["SecretAccessKey"],
            "session_token": aws_output["Credentials"]["SessionToken"],
        }
    except Exception as e:
        print(
            f"\033[31mError getting AWS credentials from awsCredentialExport: {e}\033[0m",
            file=sys.stderr,
        )
        return None


# ---------------------------------------------------------------------------
# refreshAndGetAwsCredentials (memoized with TTL)
# ---------------------------------------------------------------------------

class _MemoizeWithTTL:
    """Simple async function memoizer with TTL."""

    def __init__(self, fn: Callable, ttl_ms: int):
        self._fn = fn
        self._ttl_ms = ttl_ms
        self._cache: Optional[Any] = None
        self._timestamp: int = 0
        self._inflight: Optional[asyncio.Task] = None

    async def __call__(self, *args, **kwargs):
        now = int(time.time() * 1000)
        if self._cache is not None and now - self._timestamp < self._ttl_ms:
            return self._cache
        if self._inflight is not None:
            return await self._inflight
        self._inflight = asyncio.create_task(self._fn(*args, **kwargs))
        try:
            result = await self._inflight
            self._cache = result
            self._timestamp = int(time.time() * 1000)
            return result
        finally:
            self._inflight = None

    def clear_cache(self):
        self._cache = None
        self._timestamp = 0
        self._inflight = None


async def _refresh_and_get_aws_credentials_impl() -> Optional[dict]:
    refreshed = await _run_aws_auth_refresh()
    credentials = await _get_aws_creds_from_credential_export()
    if refreshed or credentials:
        await _clear_aws_ini_cache()
    return credentials


refresh_and_get_aws_credentials = _MemoizeWithTTL(
    _refresh_and_get_aws_credentials_impl,
    DEFAULT_AWS_STS_TTL,
)


def clear_aws_credentials_cache() -> None:
    """Port of clearAwsCredentialsCache."""
    refresh_and_get_aws_credentials.clear_cache()


# ---------------------------------------------------------------------------
# GCP auth helpers
# ---------------------------------------------------------------------------

def _get_configured_gcp_auth_refresh() -> Optional[str]:
    merged = _get_settings_deprecated()
    return merged.get("gcpAuthRefresh")


def is_gcp_auth_refresh_from_project_settings() -> bool:
    """Port of isGcpAuthRefreshFromProjectSettings."""
    gcp_auth_refresh = _get_configured_gcp_auth_refresh()
    if not gcp_auth_refresh:
        return False
    project = _get_settings_for_source("projectSettings")
    local = _get_settings_for_source("localSettings")
    return (project and project.get("gcpAuthRefresh") == gcp_auth_refresh) or (
        local and local.get("gcpAuthRefresh") == gcp_auth_refresh
    )


async def check_gcp_credentials_valid() -> bool:
    """Port of checkGcpCredentialsValid. TODO: real GCP check."""
    try:
        # Try to import and use google-auth-library equivalent
        import importlib.util
        if importlib.util.find_spec("google.auth") is None:
            return False
        from google.auth import default as _gauth_default  # type: ignore
        from google.auth.transport.requests import Request as _GAuthRequest  # type: ignore
        credentials, _ = _gauth_default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(_GAuthRequest())
        return True
    except Exception:
        return False


async def _run_gcp_auth_refresh() -> bool:
    """Port of runGcpAuthRefresh (internal)."""
    gcp_auth_refresh = _get_configured_gcp_auth_refresh()
    if not gcp_auth_refresh:
        return False

    if is_gcp_auth_refresh_from_project_settings():
        has_trust = _check_has_trust_dialog_accepted()
        if not has_trust and not get_is_non_interactive_session():
            err = RuntimeError(
                "Security: gcpAuthRefresh executed before workspace trust is confirmed."
            )
            log_error(err)
            _log_event("tengu_gcpAuthRefresh_missing_trust", {})
            return False

    try:
        debug_log("Checking GCP credentials validity for auth refresh")
        is_valid = await check_gcp_credentials_valid()
        if is_valid:
            debug_log("GCP credentials are valid, skipping auth refresh command")
            return False
    except Exception:
        pass

    return await refresh_gcp_auth(gcp_auth_refresh)


async def refresh_gcp_auth(gcp_auth_refresh: str) -> bool:
    """Port of refreshGcpAuth."""
    debug_log("Running GCP auth refresh command")
    try:
        proc = await asyncio.create_subprocess_shell(
            gcp_auth_refresh,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=GCP_AUTH_REFRESH_TIMEOUT_MS
            )
        except asyncio.TimeoutError:
            proc.kill()
            print(
                "\033[31mGCP auth refresh timed out after 3 minutes.\033[0m",
                file=sys.stderr,
            )
            return False

        if proc.returncode == 0:
            debug_log("GCP auth refresh completed successfully")
            return True
        else:
            print(
                "\033[31mError running gcpAuthRefresh (in settings or ~/.claude.json)\033[0m",
                file=sys.stderr,
            )
            return False
    except Exception as e:
        log_error(e)
        return False


async def _refresh_gcp_credentials_if_needed_impl() -> bool:
    return await _run_gcp_auth_refresh()


refresh_gcp_credentials_if_needed = _MemoizeWithTTL(
    _refresh_gcp_credentials_if_needed_impl,
    DEFAULT_GCP_CREDENTIAL_TTL,
)


def clear_gcp_credentials_cache() -> None:
    """Port of clearGcpCredentialsCache."""
    refresh_gcp_credentials_if_needed.clear_cache()


def prefetch_gcp_credentials_if_safe() -> None:
    """Port of prefetchGcpCredentialsIfSafe."""
    gcp_auth_refresh = _get_configured_gcp_auth_refresh()
    if not gcp_auth_refresh:
        return
    if is_gcp_auth_refresh_from_project_settings():
        has_trust = _check_has_trust_dialog_accepted()
        if not has_trust and not get_is_non_interactive_session():
            return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(refresh_gcp_credentials_if_needed())
    except RuntimeError:
        pass


def prefetch_aws_credentials_and_bed_rock_info_if_safe() -> None:
    """Port of prefetchAwsCredentialsAndBedRockInfoIfSafe."""
    aws_auth_refresh = _get_configured_aws_auth_refresh()
    aws_credential_export = _get_configured_aws_credential_export()
    if not aws_auth_refresh and not aws_credential_export:
        return
    if (
        is_aws_auth_refresh_from_project_settings()
        or is_aws_credential_export_from_project_settings()
    ):
        has_trust = _check_has_trust_dialog_accepted()
        if not has_trust and not get_is_non_interactive_session():
            return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(refresh_and_get_aws_credentials())
    except RuntimeError:
        pass


# ---------------------------------------------------------------------------
# getApiKeyFromConfigOrMacOSKeychain (memoized)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_api_key_from_config_or_macos_keychain() -> Optional[dict]:
    """Port of getApiKeyFromConfigOrMacOSKeychain (memoized). Returns {key, source} or None."""
    if is_bare_mode():
        return None

    if sys.platform == "darwin":
        prefetch = _get_legacy_api_key_prefetch_result()
        if prefetch is not None:
            if prefetch:
                return {"key": prefetch, "source": "/login managed key"}
            # prefetch completed with no key — fall through to config
        else:
            service_name = _get_mac_os_keychain_storage_service_name()
            try:
                result = _exec_sync_with_defaults(
                    f'security find-generic-password -a $USER -w -s "{service_name}"'
                )
                if result:
                    return {"key": result, "source": "/login managed key"}
            except Exception as e:
                log_error(e)

    config = _get_global_config()
    primary_key = config.get("primaryApiKey")
    if not primary_key:
        return None

    return {"key": primary_key, "source": "/login managed key"}


def _is_valid_api_key(api_key: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9\-_]+$", api_key))


async def save_api_key(api_key: str) -> None:
    """Port of saveApiKey."""
    if not _is_valid_api_key(api_key):
        raise ValueError(
            "Invalid API key format. API key must contain only alphanumeric characters, dashes, and underscores."
        )

    await _maybe_remove_api_key_from_macos_keychain()
    saved_to_keychain = False

    if sys.platform == "darwin":
        try:
            service_name = _get_mac_os_keychain_storage_service_name()
            username = _get_username()
            hex_value = api_key.encode("utf-8").hex()
            command = f'add-generic-password -U -a "{username}" -s "{service_name}" -X "{hex_value}"\n'

            proc = await asyncio.create_subprocess_exec(
                "security",
                "-i",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate(input=command.encode())
            _log_event("tengu_api_key_saved_to_keychain", {})
            saved_to_keychain = True
        except Exception as e:
            log_error(e)
            _log_event("tengu_api_key_saved_to_config", {})
    else:
        _log_event("tengu_api_key_saved_to_config", {})

    normalized_key = _normalize_api_key_for_config(api_key)

    def _updater(current: dict) -> dict:
        approved = current.get("customApiKeyResponses", {}).get("approved", [])
        return {
            **current,
            "primaryApiKey": current.get("primaryApiKey") if saved_to_keychain else api_key,
            "customApiKeyResponses": {
                **current.get("customApiKeyResponses", {}),
                "approved": approved if normalized_key in approved else [*approved, normalized_key],
                "rejected": current.get("customApiKeyResponses", {}).get("rejected", []),
            },
        }

    _save_global_config(_updater)
    get_api_key_from_config_or_macos_keychain.cache_clear()
    _clear_legacy_api_key_prefetch()


def is_custom_api_key_approved(api_key: str) -> bool:
    """Port of isCustomApiKeyApproved."""
    config = _get_global_config()
    normalized_key = _normalize_api_key_for_config(api_key)
    return normalized_key in config.get("customApiKeyResponses", {}).get("approved", [])


async def remove_api_key() -> None:
    """Port of removeApiKey."""
    await _maybe_remove_api_key_from_macos_keychain()

    def _updater(current: dict) -> dict:
        c = dict(current)
        c.pop("primaryApiKey", None)
        return c

    _save_global_config(_updater)
    get_api_key_from_config_or_macos_keychain.cache_clear()
    _clear_legacy_api_key_prefetch()


async def _maybe_remove_api_key_from_macos_keychain() -> None:
    """Port of maybeRemoveApiKeyFromMacOSKeychain."""
    try:
        _maybe_remove_api_key_from_macos_keychain_throws()
    except Exception as e:
        log_error(e)


# ---------------------------------------------------------------------------
# saveOAuthTokensIfNeeded
# ---------------------------------------------------------------------------

def save_oauth_tokens_if_needed(tokens: OAuthTokens) -> dict:
    """Port of saveOAuthTokensIfNeeded. Returns {success, warning?}."""
    if not _should_use_claude_ai_auth(tokens.scopes):
        _log_event("tengu_oauth_tokens_not_claude_ai", {})
        return {"success": True}

    # Skip inference-only tokens
    if not tokens.refresh_token or not tokens.expires_at:
        _log_event("tengu_oauth_tokens_inference_only", {})
        return {"success": True}

    secure_storage = _get_secure_storage()
    storage_backend = secure_storage["name"]

    try:
        storage_data = secure_storage["read"]() or {}
        existing_oauth = storage_data.get("claudeAiOauth")

        storage_data["claudeAiOauth"] = {
            "accessToken": tokens.access_token,
            "refreshToken": tokens.refresh_token,
            "expiresAt": tokens.expires_at,
            "scopes": tokens.scopes,
            "subscriptionType": (
                tokens.subscription_type
                or (existing_oauth.get("subscriptionType") if existing_oauth else None)
            ),
            "rateLimitTier": (
                tokens.rate_limit_tier
                or (existing_oauth.get("rateLimitTier") if existing_oauth else None)
            ),
        }

        update_status = secure_storage["update"](storage_data)
        if update_status.get("success"):
            _log_event("tengu_oauth_tokens_saved", {"storageBackend": storage_backend})
        else:
            _log_event("tengu_oauth_tokens_save_failed", {"storageBackend": storage_backend})

        get_claude_ai_oauth_tokens.cache_clear()
        _clear_betas_caches()
        _clear_tool_schema_cache()
        return update_status
    except Exception as e:
        log_error(e)
        _log_event("tengu_oauth_tokens_save_exception", {"storageBackend": storage_backend})
        return {"success": False, "warning": "Failed to save OAuth tokens"}


# ---------------------------------------------------------------------------
# getClaudeAIOAuthTokens (memoized)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_claude_ai_oauth_tokens() -> Optional[OAuthTokens]:
    """Port of getClaudeAIOAuthTokens (sync, memoized)."""
    if is_bare_mode():
        return None

    env_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if env_token:
        return OAuthTokens(
            access_token=env_token,
            refresh_token=None,
            expires_at=None,
            scopes=["user:inference"],
            subscription_type=None,
            rate_limit_tier=None,
        )

    oauth_token_from_fd = _get_oauth_token_from_file_descriptor()
    if oauth_token_from_fd:
        return OAuthTokens(
            access_token=oauth_token_from_fd,
            refresh_token=None,
            expires_at=None,
            scopes=["user:inference"],
            subscription_type=None,
            rate_limit_tier=None,
        )

    try:
        secure_storage = _get_secure_storage()
        storage_data = secure_storage["read"]()
        oauth_data = storage_data.get("claudeAiOauth") if storage_data else None
        if not oauth_data or not oauth_data.get("accessToken"):
            return None
        return OAuthTokens(
            access_token=oauth_data["accessToken"],
            refresh_token=oauth_data.get("refreshToken"),
            expires_at=oauth_data.get("expiresAt"),
            scopes=oauth_data.get("scopes", []),
            subscription_type=oauth_data.get("subscriptionType"),
            rate_limit_tier=oauth_data.get("rateLimitTier"),
        )
    except Exception as e:
        log_error(e)
        return None


def clear_oauth_token_cache() -> None:
    """Port of clearOAuthTokenCache."""
    get_claude_ai_oauth_tokens.cache_clear()
    _clear_keychain_cache()


# _lastCredentialsMtimeMs tracks cross-process staleness
_last_credentials_mtime_ms: int = 0


async def _invalidate_oauth_cache_if_disk_changed() -> None:
    """Port of invalidateOAuthCacheIfDiskChanged."""
    global _last_credentials_mtime_ms
    try:
        cred_path = Path(get_claude_config_home_dir()) / ".credentials.json"
        mtime_ms = int(cred_path.stat().st_mtime * 1000)
        if mtime_ms != _last_credentials_mtime_ms:
            _last_credentials_mtime_ms = mtime_ms
            clear_oauth_token_cache()
    except FileNotFoundError:
        get_claude_ai_oauth_tokens.cache_clear()
    except Exception:
        pass


# In-flight dedup for 401 handlers
_pending_401_handlers: dict = {}


async def handle_oauth_401_error(failed_access_token: str) -> bool:
    """Port of handleOAuth401Error."""
    if failed_access_token in _pending_401_handlers:
        return await _pending_401_handlers[failed_access_token]

    async def _task():
        try:
            return await _handle_oauth_401_error_impl(failed_access_token)
        finally:
            _pending_401_handlers.pop(failed_access_token, None)

    fut = asyncio.ensure_future(_task())
    _pending_401_handlers[failed_access_token] = fut
    return await fut


async def _handle_oauth_401_error_impl(failed_access_token: str) -> bool:
    """Port of handleOAuth401ErrorImpl."""
    clear_oauth_token_cache()
    current_tokens = await get_claude_ai_oauth_tokens_async()

    if not current_tokens or not current_tokens.refresh_token:
        return False

    if current_tokens.access_token != failed_access_token:
        _log_event("tengu_oauth_401_recovered_from_keychain", {})
        return True

    return await check_and_refresh_oauth_token_if_needed(0, force=True)


async def get_claude_ai_oauth_tokens_async() -> Optional[OAuthTokens]:
    """Port of getClaudeAIOAuthTokensAsync."""
    if is_bare_mode():
        return None

    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or _get_oauth_token_from_file_descriptor():
        return get_claude_ai_oauth_tokens()

    try:
        secure_storage = _get_secure_storage()
        storage_data = await secure_storage["read_async"]()
        oauth_data = storage_data.get("claudeAiOauth") if storage_data else None
        if not oauth_data or not oauth_data.get("accessToken"):
            return None
        return OAuthTokens(
            access_token=oauth_data["accessToken"],
            refresh_token=oauth_data.get("refreshToken"),
            expires_at=oauth_data.get("expiresAt"),
            scopes=oauth_data.get("scopes", []),
            subscription_type=oauth_data.get("subscriptionType"),
            rate_limit_tier=oauth_data.get("rateLimitTier"),
        )
    except Exception as e:
        log_error(e)
        return None


# In-flight dedup for concurrent refresh checks
_pending_refresh_check: Optional[asyncio.Task] = None


def check_and_refresh_oauth_token_if_needed(
    retry_count: int = 0,
    force: bool = False,
) -> "asyncio.Future[bool]":
    """Port of checkAndRefreshOAuthTokenIfNeeded."""
    global _pending_refresh_check

    if retry_count == 0 and not force:
        if _pending_refresh_check is not None and not _pending_refresh_check.done():
            return _pending_refresh_check

        async def _wrapped():
            global _pending_refresh_check
            try:
                return await _check_and_refresh_oauth_token_if_needed_impl(retry_count, force)
            finally:
                _pending_refresh_check = None

        try:
            _pending_refresh_check = asyncio.ensure_future(_wrapped())
        except RuntimeError:
            # No running event loop — create a coroutine-based future
            import asyncio as _aio
            _pending_refresh_check = _aio.create_task(_wrapped())
        return _pending_refresh_check

    return asyncio.ensure_future(
        _check_and_refresh_oauth_token_if_needed_impl(retry_count, force)
    )


async def _check_and_refresh_oauth_token_if_needed_impl(
    retry_count: int,
    force: bool,
) -> bool:
    """Port of checkAndRefreshOAuthTokenIfNeededImpl."""
    MAX_RETRIES = 5

    await _invalidate_oauth_cache_if_disk_changed()

    tokens = get_claude_ai_oauth_tokens()
    if not force:
        if not tokens or not tokens.refresh_token or not _is_oauth_token_expired(tokens.expires_at):
            return False

    if not tokens or not tokens.refresh_token:
        return False

    if not _should_use_claude_ai_auth(tokens.scopes):
        return False

    # Re-read async to check if still expired
    get_claude_ai_oauth_tokens.cache_clear()
    _clear_keychain_cache()
    fresh_tokens = await get_claude_ai_oauth_tokens_async()
    if not fresh_tokens or not fresh_tokens.refresh_token or not _is_oauth_token_expired(fresh_tokens.expires_at):
        return False

    # Acquire lock and refresh
    claude_dir = get_claude_config_home_dir()
    Path(claude_dir).mkdir(parents=True, exist_ok=True)

    release = None
    try:
        _log_event("tengu_oauth_token_refresh_lock_acquiring", {})
        release = await _acquire_lock(claude_dir)
        _log_event("tengu_oauth_token_refresh_lock_acquired", {})
    except OSError as err:
        if "ELOCKED" in str(err):
            if retry_count < MAX_RETRIES:
                _log_event("tengu_oauth_token_refresh_lock_retry", {"retryCount": retry_count + 1})
                await asyncio.sleep(1 + (time.time() % 1))
                return await _check_and_refresh_oauth_token_if_needed_impl(retry_count + 1, force)
            _log_event("tengu_oauth_token_refresh_lock_retry_limit_reached", {"maxRetries": MAX_RETRIES})
            return False
        log_error(err)
        _log_event("tengu_oauth_token_refresh_lock_error", {})
        return False

    try:
        # Double-check after lock
        get_claude_ai_oauth_tokens.cache_clear()
        _clear_keychain_cache()
        locked_tokens = await get_claude_ai_oauth_tokens_async()
        if not locked_tokens or not locked_tokens.refresh_token or not _is_oauth_token_expired(locked_tokens.expires_at):
            _log_event("tengu_oauth_token_refresh_race_resolved", {})
            return False

        _log_event("tengu_oauth_token_refresh_starting", {})
        refreshed_tokens = await _refresh_oauth_token_stub(
            locked_tokens.refresh_token,
            opts={"scopes": None} if _should_use_claude_ai_auth(locked_tokens.scopes) else {"scopes": locked_tokens.scopes},
        )
        save_oauth_tokens_if_needed(refreshed_tokens)

        get_claude_ai_oauth_tokens.cache_clear()
        _clear_keychain_cache()
        return True
    except Exception as e:
        log_error(e)
        get_claude_ai_oauth_tokens.cache_clear()
        _clear_keychain_cache()
        current_tokens = await get_claude_ai_oauth_tokens_async()
        if current_tokens and not _is_oauth_token_expired(current_tokens.expires_at):
            _log_event("tengu_oauth_token_refresh_race_recovered", {})
            return True
        return False
    finally:
        _log_event("tengu_oauth_token_refresh_lock_releasing", {})
        if release:
            await release()
        _log_event("tengu_oauth_token_refresh_lock_released", {})


# ---------------------------------------------------------------------------
# Subscription / plan helpers
# ---------------------------------------------------------------------------

def is_claude_ai_subscriber() -> bool:
    """Port of isClaudeAISubscriber."""
    if not is_anthropic_auth_enabled():
        return False
    return _should_use_claude_ai_auth(get_claude_ai_oauth_tokens().scopes if get_claude_ai_oauth_tokens() else None)


def has_profile_scope() -> bool:
    """Port of hasProfileScope."""
    tokens = get_claude_ai_oauth_tokens()
    return CLAUDE_AI_PROFILE_SCOPE in (tokens.scopes or []) if tokens else False


def is_1p_api_customer() -> bool:
    """Port of is1PApiCustomer."""
    if (
        is_env_truthy(os.environ.get("CLAUDE_CODE_USE_BEDROCK"))
        or is_env_truthy(os.environ.get("CLAUDE_CODE_USE_VERTEX"))
        or is_env_truthy(os.environ.get("CLAUDE_CODE_USE_FOUNDRY"))
    ):
        return False
    if is_claude_ai_subscriber():
        return False
    return True


def get_oauth_account_info() -> Optional[dict]:
    """Port of getOauthAccountInfo."""
    if not is_anthropic_auth_enabled():
        return None
    return _get_global_config().get("oauthAccount")


def is_overage_provisioning_allowed() -> bool:
    """Port of isOverageProvisioningAllowed."""
    account_info = get_oauth_account_info()
    billing_type = account_info.get("billingType") if account_info else None

    if not is_claude_ai_subscriber() or not billing_type:
        return False

    return billing_type in (
        "stripe_subscription",
        "stripe_subscription_contracted",
        "apple_subscription",
        "google_play_subscription",
    )


def has_opus_access() -> bool:
    """Port of hasOpusAccess."""
    subscription_type = get_subscription_type()
    return subscription_type in ("max", "enterprise", "team", "pro", None)


def get_subscription_type() -> Optional[str]:
    """Port of getSubscriptionType."""
    if _should_use_mock_subscription():
        return _get_mock_subscription_type()
    if not is_anthropic_auth_enabled():
        return None
    tokens = get_claude_ai_oauth_tokens()
    if not tokens:
        return None
    return tokens.subscription_type


def is_max_subscriber() -> bool:
    return get_subscription_type() == "max"


def is_team_subscriber() -> bool:
    return get_subscription_type() == "team"


def is_team_premium_subscriber() -> bool:
    return get_subscription_type() == "team" and get_rate_limit_tier() == "default_claude_max_5x"


def is_enterprise_subscriber() -> bool:
    return get_subscription_type() == "enterprise"


def is_pro_subscriber() -> bool:
    return get_subscription_type() == "pro"


def get_rate_limit_tier() -> Optional[str]:
    """Port of getRateLimitTier."""
    if not is_anthropic_auth_enabled():
        return None
    tokens = get_claude_ai_oauth_tokens()
    if not tokens:
        return None
    return tokens.rate_limit_tier


def get_subscription_name() -> str:
    """Port of getSubscriptionName."""
    subscription_type = get_subscription_type()
    names = {
        "enterprise": "Claude Enterprise",
        "team": "Claude Team",
        "max": "Claude Max",
        "pro": "Claude Pro",
    }
    return names.get(subscription_type, "Claude API")


def is_using_3p_services() -> bool:
    """Port of isUsing3PServices."""
    return bool(
        is_env_truthy(os.environ.get("CLAUDE_CODE_USE_BEDROCK"))
        or is_env_truthy(os.environ.get("CLAUDE_CODE_USE_VERTEX"))
        or is_env_truthy(os.environ.get("CLAUDE_CODE_USE_FOUNDRY"))
    )


def is_consumer_subscriber() -> bool:
    """Port of isConsumerSubscriber."""
    subscription_type = get_subscription_type()
    return (
        is_claude_ai_subscriber()
        and subscription_type is not None
        and subscription_type in ("max", "pro")
    )


# ---------------------------------------------------------------------------
# OtelHeadersHelper
# ---------------------------------------------------------------------------

def _get_configured_otel_headers_helper() -> Optional[str]:
    merged = _get_settings_deprecated()
    return merged.get("otelHeadersHelper")


def is_otel_headers_helper_from_project_or_local_settings() -> bool:
    """Port of isOtelHeadersHelperFromProjectOrLocalSettings."""
    otel_helper = _get_configured_otel_headers_helper()
    if not otel_helper:
        return False
    project = _get_settings_for_source("projectSettings")
    local = _get_settings_for_source("localSettings")
    return (project and project.get("otelHeadersHelper") == otel_helper) or (
        local and local.get("otelHeadersHelper") == otel_helper
    )


_cached_otel_headers: Optional[dict] = None
_cached_otel_headers_timestamp: int = 0


def get_otel_headers_from_helper() -> dict:
    """Port of getOtelHeadersFromHelper."""
    global _cached_otel_headers, _cached_otel_headers_timestamp

    otel_helper = _get_configured_otel_headers_helper()
    if not otel_helper:
        return {}

    debounce_ms = DEFAULT_OTEL_HEADERS_DEBOUNCE_MS
    raw_debounce = os.environ.get("CLAUDE_CODE_OTEL_HEADERS_HELPER_DEBOUNCE_MS")
    if raw_debounce:
        try:
            debounce_ms = int(raw_debounce)
        except ValueError:
            pass

    now_ms = int(time.time() * 1000)
    if _cached_otel_headers is not None and now_ms - _cached_otel_headers_timestamp < debounce_ms:
        return _cached_otel_headers

    if is_otel_headers_helper_from_project_or_local_settings():
        has_trust = _check_has_trust_dialog_accepted()
        if not has_trust:
            return {}

    try:
        result = _exec_sync_with_defaults(otel_helper, timeout=30000)
        if not result:
            raise RuntimeError("otelHeadersHelper did not return a valid value")

        headers = json.loads(result)
        if not isinstance(headers, dict) or isinstance(headers, list):
            raise RuntimeError(
                "otelHeadersHelper must return a JSON object with string key-value pairs"
            )

        for key, value in headers.items():
            if not isinstance(value, str):
                raise RuntimeError(
                    f'otelHeadersHelper returned non-string value for key "{key}": {type(value).__name__}'
                )

        _cached_otel_headers = headers
        _cached_otel_headers_timestamp = now_ms
        return _cached_otel_headers
    except Exception as e:
        log_error(
            RuntimeError(
                f"Error getting OpenTelemetry headers from otelHeadersHelper (in settings): {error_message(e)}"
            )
        )
        raise


# ---------------------------------------------------------------------------
# getAccountInformation
# ---------------------------------------------------------------------------

def get_account_information() -> Optional[UserAccountInfo]:
    """Port of getAccountInformation."""
    api_provider = _get_api_provider()
    if api_provider != "firstParty":
        return None

    auth_token_source_result = get_auth_token_source()
    auth_token_source = auth_token_source_result["source"]
    account_info: UserAccountInfo = {}

    if auth_token_source in (
        "CLAUDE_CODE_OAUTH_TOKEN",
        "CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR",
    ):
        account_info["token_source"] = auth_token_source
    elif is_claude_ai_subscriber():
        account_info["subscription"] = get_subscription_name()
    else:
        account_info["token_source"] = auth_token_source

    key_result = get_anthropic_api_key_with_source()
    api_key = key_result["key"]
    api_key_source = key_result["source"]
    if api_key:
        account_info["api_key_source"] = api_key_source

    if auth_token_source == "claude.ai" or api_key_source == "/login managed key":
        oauth_acct = get_oauth_account_info()
        if oauth_acct:
            org_name = oauth_acct.get("organizationName")
            if org_name:
                account_info["organization"] = org_name

    if (auth_token_source == "claude.ai" or api_key_source == "/login managed key"):
        oauth_acct = get_oauth_account_info()
        if oauth_acct:
            email = oauth_acct.get("emailAddress")
            if email:
                account_info["email"] = email

    return account_info


# ---------------------------------------------------------------------------
# validateForceLoginOrg
# ---------------------------------------------------------------------------

async def validate_force_login_org() -> OrgValidationResult:
    """Port of validateForceLoginOrg."""
    if os.environ.get("ANTHROPIC_UNIX_SOCKET"):
        return {"valid": True}

    if not is_anthropic_auth_enabled():
        return {"valid": True}

    required_org_uuid = None
    policy_settings = _get_settings_for_source("policySettings")
    if policy_settings:
        required_org_uuid = policy_settings.get("forceLoginOrgUUID")

    if not required_org_uuid:
        return {"valid": True}

    await check_and_refresh_oauth_token_if_needed()

    tokens = get_claude_ai_oauth_tokens()
    if not tokens:
        return {"valid": True}

    source_result = get_auth_token_source()
    source = source_result["source"]
    is_env_var_token = source in (
        "CLAUDE_CODE_OAUTH_TOKEN",
        "CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR",
    )

    profile = await _get_oauth_profile_from_oauth_token(tokens.access_token)
    if not profile:
        return {
            "valid": False,
            "message": (
                f"Unable to verify organization for the current authentication token.\n"
                f"This machine requires organization {required_org_uuid} but the profile could not be fetched.\n"
                f"This may be a network error, or the token may lack the user:profile scope required for\n"
                f"verification (tokens from 'claude setup-token' do not include this scope).\n"
                f"Try again, or obtain a full-scope token via 'claude auth login'."
            ),
        }

    token_org_uuid = profile.get("organization", {}).get("uuid", "")
    if token_org_uuid == required_org_uuid:
        return {"valid": True}

    if is_env_var_token:
        env_var_name = (
            "CLAUDE_CODE_OAUTH_TOKEN"
            if source == "CLAUDE_CODE_OAUTH_TOKEN"
            else "CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR"
        )
        return {
            "valid": False,
            "message": (
                f"The {env_var_name} environment variable provides a token for a\n"
                f"different organization than required by this machine's managed settings.\n\n"
                f"Required organization: {required_org_uuid}\n"
                f"Token organization:   {token_org_uuid}\n\n"
                f"Remove the environment variable or obtain a token for the correct organization."
            ),
        }

    return {
        "valid": False,
        "message": (
            f"Your authentication token belongs to organization {token_org_uuid},\n"
            f"but this machine requires organization {required_org_uuid}.\n\n"
            f"Please log in with the correct organization: claude auth login"
        ),
    }


# ---------------------------------------------------------------------------
# GcpCredentialsTimeoutError
# ---------------------------------------------------------------------------

class GcpCredentialsTimeoutError(Exception):
    """Port of GcpCredentialsTimeoutError."""
    pass


# ---------------------------------------------------------------------------
# __all__ — explicit public API
# ---------------------------------------------------------------------------

__all__ = [
    # Core auth functions
    "is_anthropic_auth_enabled",
    "get_auth_token_source",
    "get_anthropic_api_key",
    "has_anthropic_api_key_auth",
    "get_anthropic_api_key_with_source",
    # API key helper
    "get_configured_api_key_helper",
    "calculate_api_key_helper_ttl",
    "get_api_key_from_api_key_helper",
    "get_api_key_from_api_key_helper_cached",
    "get_api_key_helper_elapsed_ms",
    "clear_api_key_helper_cache",
    "prefetch_api_key_from_api_key_helper_if_safe",
    # API key storage
    "get_api_key_from_config_or_macos_keychain",
    "save_api_key",
    "remove_api_key",
    "is_custom_api_key_approved",
    # OAuth tokens
    "get_claude_ai_oauth_tokens",
    "get_claude_ai_oauth_tokens_async",
    "save_oauth_tokens_if_needed",
    "clear_oauth_token_cache",
    "handle_oauth_401_error",
    "check_and_refresh_oauth_token_if_needed",
    # AWS helpers
    "refresh_aws_auth",
    "refresh_and_get_aws_credentials",
    "clear_aws_credentials_cache",
    "is_aws_auth_refresh_from_project_settings",
    "is_aws_credential_export_from_project_settings",
    "prefetch_aws_credentials_and_bed_rock_info_if_safe",
    # GCP helpers
    "check_gcp_credentials_valid",
    "refresh_gcp_auth",
    "refresh_gcp_credentials_if_needed",
    "clear_gcp_credentials_cache",
    "is_gcp_auth_refresh_from_project_settings",
    "prefetch_gcp_credentials_if_safe",
    # Subscription / account
    "is_claude_ai_subscriber",
    "has_profile_scope",
    "is_1p_api_customer",
    "get_oauth_account_info",
    "is_overage_provisioning_allowed",
    "has_opus_access",
    "get_subscription_type",
    "get_subscription_name",
    "get_rate_limit_tier",
    "is_max_subscriber",
    "is_team_subscriber",
    "is_team_premium_subscriber",
    "is_enterprise_subscriber",
    "is_pro_subscriber",
    "is_using_3p_services",
    "is_consumer_subscriber",
    # OTel
    "get_otel_headers_from_helper",
    "is_otel_headers_helper_from_project_or_local_settings",
    # Account info
    "get_account_information",
    "validate_force_login_org",
    # Types
    "OAuthTokens",
    "AccountInfo",
    "ApiKeySource",
    "OrgValidationResult",
    "UserAccountInfo",
    "GcpCredentialsTimeoutError",
]
