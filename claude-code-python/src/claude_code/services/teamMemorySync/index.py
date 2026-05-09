"""
Team Memory Sync Service

Syncs team memory files between the local filesystem and the server API.
Team memory is scoped per-repo (identified by git remote hash) and shared
across all authenticated org members.

API contract:
  GET  /api/claude_code/team_memory?repo={owner/repo}              → TeamMemoryData (includes entryChecksums)
  GET  /api/claude_code/team_memory?repo={owner/repo}&view=hashes  → metadata + entryChecksums only
  PUT  /api/claude_code/team_memory?repo={owner/repo}              → upload entries (upsert semantics)
  404 = no data exists yet

Sync semantics:
  - Pull overwrites local files with server content (server wins per-key).
  - Push uploads only keys whose content hash differs from server_checksums.
  - File deletions do NOT propagate.

State management:
  All mutable state lives in a SyncState object created by the caller.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ─── Internal import stubs with graceful fallback ─────────────────────────────

try:
    import aiohttp
    _AIOHTTP_AVAILABLE = True
except ImportError:
    _AIOHTTP_AVAILABLE = False

try:
    from claude_code.constants.oauth import (
        CLAUDE_AI_INFERENCE_SCOPE,
        CLAUDE_AI_PROFILE_SCOPE,
        OAUTH_BETA_HEADER,
        get_oauth_config,
    )
except ImportError:
    CLAUDE_AI_INFERENCE_SCOPE = "claude_ai_inference"
    CLAUDE_AI_PROFILE_SCOPE = "claude_ai_profile"
    OAUTH_BETA_HEADER = "oauth-2023-05-03"

    def get_oauth_config():
        return type("C", (), {"BASE_API_URL": "https://api.anthropic.com"})()

try:
    from claude_code.memdir.team_mem_paths import (
        get_team_mem_path,
        PathTraversalError,
        validate_team_mem_key,
    )
except ImportError:
    def get_team_mem_path() -> str:
        return os.path.join(os.path.expanduser("~"), ".claude", "team_memory")

    class PathTraversalError(Exception):
        pass

    async def validate_team_mem_key(rel_path: str) -> str:
        base = get_team_mem_path()
        full = os.path.realpath(os.path.join(base, rel_path))
        if not full.startswith(os.path.realpath(base)):
            raise PathTraversalError(f"Path traversal detected: {rel_path}")
        return full

try:
    from claude_code.utils.auth import (
        check_and_refresh_oauth_token_if_needed,
        get_claude_ai_oauth_tokens,
    )
except ImportError:
    async def check_and_refresh_oauth_token_if_needed():
        pass

    def get_claude_ai_oauth_tokens():
        return None

try:
    from claude_code.utils.debug import log_for_debugging
except ImportError:
    def log_for_debugging(msg: str, *, level: str = "debug"):
        if level in ("warn", "error"):
            print(f"[{level.upper()}] {msg}")

try:
    from claude_code.utils.git import get_github_repo
except ImportError:
    async def get_github_repo() -> Optional[str]:
        return None

try:
    from claude_code.utils.model.providers import (
        get_api_provider,
        is_first_party_anthropic_base_url,
    )
except ImportError:
    def get_api_provider() -> str:
        return "firstParty"

    def is_first_party_anthropic_base_url() -> bool:
        return True

try:
    from claude_code.utils.sleep import sleep
except ImportError:
    async def sleep(ms: int):
        await asyncio.sleep(ms / 1000.0)

try:
    from claude_code.utils.slow_operations import json_stringify
except ImportError:
    def json_stringify(obj: Any) -> str:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

try:
    from claude_code.utils.user_agent import get_claude_code_user_agent
except ImportError:
    def get_claude_code_user_agent() -> str:
        return "claude-code/python"

try:
    from claude_code.services.analytics import log_event
except ImportError:
    def log_event(event_name: str, properties: Dict[str, Any] = None):
        pass

try:
    from claude_code.services.api.with_retry import get_retry_delay
except ImportError:
    def get_retry_delay(attempt: int) -> int:
        return min(1000 * (2 ** (attempt - 1)), 30000)

try:
    from claude_code.services.teamMemorySync.secret_scanner import scan_for_secrets
except ImportError:
    def scan_for_secrets(content: str) -> List[Any]:
        return []

# Define types locally to avoid circular imports with package __init__.py
# The canonical types live in types.py; these are fallback dataclasses.

@dataclass
class SkippedSecretFile:
    path: str
    rule_id: str
    label: str


def TeamMemoryDataSchema():
    return None


@dataclass
class TeamMemoryHashesResult:
    success: bool
    error: Optional[str] = None
    error_type: Optional[str] = None
    http_status: Optional[int] = None
    version: Optional[str] = None
    checksum: Optional[str] = None
    entry_checksums: Optional[Dict[str, str]] = None


@dataclass
class TeamMemorySyncFetchResult:
    success: bool
    error: Optional[str] = None
    skip_retry: bool = False
    error_type: Optional[str] = None
    http_status: Optional[int] = None
    not_modified: bool = False
    is_empty: bool = False
    data: Optional[Any] = None
    checksum: Optional[str] = None


@dataclass
class TeamMemorySyncPushResult:
    success: bool
    files_uploaded: int = 0
    error: Optional[str] = None
    error_type: Optional[str] = None
    http_status: Optional[int] = None
    conflict: bool = False
    checksum: Optional[str] = None
    skipped_secrets: Optional[List[Any]] = None


@dataclass
class TeamMemorySyncUploadResult:
    success: bool
    error: Optional[str] = None
    error_type: Optional[str] = None
    http_status: Optional[int] = None
    conflict: bool = False
    checksum: Optional[str] = None
    last_modified: Optional[str] = None
    server_error_code: Optional[str] = None
    server_max_entries: Optional[int] = None
    server_received_entries: Optional[int] = None


def TeamMemoryTooManyEntriesSchema():
    return None

# Try to override with canonical types from types.py if available
try:
    import importlib.util as _ilu
    import os as _os
    _types_path = _os.path.join(_os.path.dirname(__file__), "types.py")
    if _os.path.exists(_types_path):
        _spec = _ilu.spec_from_file_location("_team_mem_types", _types_path)
        _types_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_types_mod)  # type: ignore[union-attr]
        SkippedSecretFile = getattr(_types_mod, "SkippedSecretFile", SkippedSecretFile)
        TeamMemoryDataSchema = getattr(_types_mod, "TeamMemoryDataSchema", TeamMemoryDataSchema)
        TeamMemoryHashesResult = getattr(_types_mod, "TeamMemoryHashesResult", TeamMemoryHashesResult)
        TeamMemorySyncFetchResult = getattr(_types_mod, "TeamMemorySyncFetchResult", TeamMemorySyncFetchResult)
        TeamMemorySyncPushResult = getattr(_types_mod, "TeamMemorySyncPushResult", TeamMemorySyncPushResult)
        TeamMemorySyncUploadResult = getattr(_types_mod, "TeamMemorySyncUploadResult", TeamMemorySyncUploadResult)
        TeamMemoryTooManyEntriesSchema = getattr(_types_mod, "TeamMemoryTooManyEntriesSchema", TeamMemoryTooManyEntriesSchema)
except Exception:
    pass


# ─── Constants ────────────────────────────────────────────────────────────────

TEAM_MEMORY_SYNC_TIMEOUT_MS = 30_000
MAX_FILE_SIZE_BYTES = 250_000
MAX_PUT_BODY_BYTES = 200_000
MAX_RETRIES = 3
MAX_CONFLICT_RETRIES = 2


# ─── Sync state ───────────────────────────────────────────────────────────────

@dataclass
class SyncState:
    """
    Mutable state for the team memory sync service.
    Created once per session by the watcher and passed to all sync functions.
    Tests create a fresh instance per test for isolation.
    """
    last_known_checksum: Optional[str] = None
    """Last known server checksum (ETag) for conditional requests."""

    server_checksums: Dict[str, str] = field(default_factory=dict)
    """
    Per-key content hash (sha256:<hex>) of what we believe the server currently holds.
    Populated from server-provided entry_checksums on pull and from local hashes on push.
    Used to compute the delta on push.
    """

    server_max_entries: Optional[int] = None
    """
    Server-enforced max_entries cap, learned from a structured 413 response.
    Stays None until a 413 is observed.
    """


def create_sync_state() -> SyncState:
    """Create a new, empty SyncState."""
    return SyncState()


# ─── Utility functions ────────────────────────────────────────────────────────

def hash_content(content: str) -> str:
    """
    Compute sha256:<hex> over the UTF-8 bytes of the given content.
    Format matches the server's entryChecksums values.
    """
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"sha256:{h}"


def _is_errno_exception(e: Exception) -> bool:
    return isinstance(e, OSError)


# ─── Auth & endpoint ──────────────────────────────────────────────────────────

def is_using_oauth() -> bool:
    """Check if user is authenticated with first-party OAuth (required for team memory sync)."""
    if get_api_provider() != "firstParty" or not is_first_party_anthropic_base_url():
        return False
    tokens = get_claude_ai_oauth_tokens()
    if not tokens:
        return False
    access_token = getattr(tokens, "access_token", None) or (tokens.get("accessToken") if isinstance(tokens, dict) else None)
    scopes = getattr(tokens, "scopes", None) or (tokens.get("scopes") if isinstance(tokens, dict) else None)
    return bool(
        access_token
        and scopes
        and CLAUDE_AI_INFERENCE_SCOPE in scopes
        and CLAUDE_AI_PROFILE_SCOPE in scopes
    )


def get_team_memory_sync_endpoint(repo_slug: str) -> str:
    base_url = os.environ.get("TEAM_MEMORY_SYNC_URL") or get_oauth_config().BASE_API_URL
    from urllib.parse import quote
    return f"{base_url}/api/claude_code/team_memory?repo={quote(repo_slug, safe='')}"


def get_auth_headers() -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """Returns (headers, error)."""
    tokens = get_claude_ai_oauth_tokens()
    if tokens:
        access_token = getattr(tokens, "access_token", None) or (tokens.get("accessToken") if isinstance(tokens, dict) else None)
        if access_token:
            return {
                "Authorization": f"Bearer {access_token}",
                "anthropic-beta": OAUTH_BETA_HEADER,
                "User-Agent": get_claude_code_user_agent(),
            }, None
    return None, "No OAuth token available for team memory sync"


# ─── HTTP helpers ─────────────────────────────────────────────────────────────

async def _do_get(
    url: str,
    headers: Dict[str, str],
    timeout_ms: int = TEAM_MEMORY_SYNC_TIMEOUT_MS,
    allowed_statuses: Tuple[int, ...] = (200,),
) -> Tuple[Optional[int], Optional[Dict[str, Any]], Optional[Dict[str, str]], Optional[str]]:
    """
    Perform an async GET request.
    Returns (status, json_data, resp_headers, error_message).
    """
    if not _AIOHTTP_AVAILABLE:
        return None, None, None, "aiohttp not available"
    try:
        timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000.0)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                status = resp.status
                resp_headers = dict(resp.headers)
                if status not in allowed_statuses:
                    text = await resp.text()
                    return status, None, resp_headers, f"HTTP {status}: {text[:200]}"
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = None
                return status, data, resp_headers, None
    except asyncio.TimeoutError:
        return None, None, None, "Timeout"
    except Exception as e:
        return None, None, None, str(e)


async def _do_put(
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    timeout_ms: int = TEAM_MEMORY_SYNC_TIMEOUT_MS,
    allowed_statuses: Tuple[int, ...] = (200,),
) -> Tuple[Optional[int], Optional[Dict[str, Any]], Optional[str]]:
    """
    Perform an async PUT request.
    Returns (status, json_data, error_message).
    """
    if not _AIOHTTP_AVAILABLE:
        return None, None, "aiohttp not available"
    try:
        timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000.0)
        put_headers = dict(headers)
        put_headers["Content-Type"] = "application/json"
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.put(url, headers=put_headers, json=payload) as resp:
                status = resp.status
                if status not in allowed_statuses:
                    text = await resp.text()
                    return status, None, f"HTTP {status}: {text[:200]}"
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = None
                return status, data, None
    except asyncio.TimeoutError:
        return None, None, "Timeout"
    except Exception as e:
        return None, None, str(e)


def _classify_http_error(status: Optional[int], error_msg: Optional[str]) -> str:
    """Classify an HTTP error into a category."""
    if status in (401, 403):
        return "auth"
    if error_msg and "timeout" in error_msg.lower():
        return "timeout"
    if error_msg and ("connect" in error_msg.lower() or "network" in error_msg.lower() or "name resolution" in error_msg.lower()):
        return "network"
    return "unknown"


# ─── Fetch (pull) ─────────────────────────────────────────────────────────────

async def fetch_team_memory_once(
    state: SyncState,
    repo_slug: str,
    etag: Optional[str] = None,
) -> TeamMemorySyncFetchResult:
    """Single fetch attempt without retry."""
    try:
        await check_and_refresh_oauth_token_if_needed()

        auth_headers, auth_error = get_auth_headers()
        if auth_error:
            return TeamMemorySyncFetchResult(
                success=False, error=auth_error, skip_retry=True, error_type="auth"
            )

        headers = dict(auth_headers)
        if etag:
            clean_etag = etag.strip('"')
            headers["If-None-Match"] = f'"{clean_etag}"'

        endpoint = get_team_memory_sync_endpoint(repo_slug)
        status, data, resp_headers, err = await _do_get(
            endpoint, headers, allowed_statuses=(200, 304, 404)
        )

        if err and status is None:
            error_type = _classify_http_error(status, err)
            return TeamMemorySyncFetchResult(success=False, error=err, error_type=error_type)

        if status == 304:
            log_for_debugging("team-memory-sync: not modified (304)", level="debug")
            return TeamMemorySyncFetchResult(success=True, not_modified=True, checksum=etag)

        if status == 404:
            log_for_debugging("team-memory-sync: no remote data (404)", level="debug")
            state.last_known_checksum = None
            return TeamMemorySyncFetchResult(success=True, is_empty=True)

        if status == 401 or status == 403:
            return TeamMemorySyncFetchResult(
                success=False,
                error=f"Not authorized for team memory sync",
                skip_retry=True,
                error_type="auth",
                http_status=status,
            )

        # Validate response format
        if not isinstance(data, dict) or "content" not in data:
            log_for_debugging("team-memory-sync: invalid response format", level="warn")
            return TeamMemorySyncFetchResult(
                success=False,
                error="Invalid team memory response format",
                skip_retry=True,
                error_type="parse",
            )

        # Extract checksum
        response_checksum = (
            data.get("checksum")
            or (resp_headers or {}).get("etag", "").strip('"')
            or None
        )
        if response_checksum:
            state.last_known_checksum = response_checksum

        log_for_debugging(
            f"team-memory-sync: fetched successfully (checksum: {response_checksum or 'none'})",
            level="debug",
        )
        return TeamMemorySyncFetchResult(
            success=True,
            data=data,
            is_empty=False,
            checksum=response_checksum,
        )

    except Exception as e:
        error_type = _classify_http_error(None, str(e))
        return TeamMemorySyncFetchResult(success=False, error=str(e), error_type=error_type)


async def fetch_team_memory_hashes(
    state: SyncState,
    repo_slug: str,
) -> TeamMemoryHashesResult:
    """
    Fetch only per-key checksums + metadata (no entry bodies).
    Used for cheap server_checksums refresh during 412 conflict resolution.
    """
    try:
        await check_and_refresh_oauth_token_if_needed()
        auth_headers, auth_error = get_auth_headers()
        if auth_error:
            return TeamMemoryHashesResult(success=False, error=auth_error, error_type="auth")

        endpoint = get_team_memory_sync_endpoint(repo_slug) + "&view=hashes"
        status, data, resp_headers, err = await _do_get(
            endpoint, auth_headers, allowed_statuses=(200, 404)
        )

        if err and status is None:
            error_type = _classify_http_error(status, err)
            return TeamMemoryHashesResult(success=False, error=err, error_type=error_type)

        if status == 404:
            state.last_known_checksum = None
            return TeamMemoryHashesResult(success=True, entry_checksums={})

        if status in (401, 403):
            return TeamMemoryHashesResult(
                success=False, error="Not authorized", error_type="auth", http_status=status
            )

        checksum = (
            (data or {}).get("checksum")
            or (resp_headers or {}).get("etag", "").strip('"')
            or None
        )
        entry_checksums = (data or {}).get("entryChecksums")

        if not entry_checksums or not isinstance(entry_checksums, dict):
            return TeamMemoryHashesResult(
                success=False,
                error="Server did not return entryChecksums (?view=hashes unsupported)",
                error_type="parse",
            )

        if checksum:
            state.last_known_checksum = checksum

        return TeamMemoryHashesResult(
            success=True,
            version=(data or {}).get("version"),
            checksum=checksum,
            entry_checksums=entry_checksums,
        )

    except Exception as e:
        error_type = _classify_http_error(None, str(e))
        return TeamMemoryHashesResult(success=False, error=str(e), error_type=error_type)


async def fetch_team_memory(
    state: SyncState,
    repo_slug: str,
    etag: Optional[str] = None,
) -> TeamMemorySyncFetchResult:
    """Fetch team memory with retry logic."""
    last_result: Optional[TeamMemorySyncFetchResult] = None

    for attempt in range(1, MAX_RETRIES + 2):
        last_result = await fetch_team_memory_once(state, repo_slug, etag)
        if last_result.success or last_result.skip_retry:
            return last_result
        if attempt > MAX_RETRIES:
            return last_result
        delay_ms = get_retry_delay(attempt)
        log_for_debugging(f"team-memory-sync: retry {attempt}/{MAX_RETRIES}", level="debug")
        await sleep(delay_ms)

    return last_result  # type: ignore[return-value]


# ─── Upload (push) ────────────────────────────────────────────────────────────

def batch_delta_by_bytes(delta: Dict[str, str]) -> List[Dict[str, str]]:
    """
    Split a delta into PUT-sized batches under MAX_PUT_BODY_BYTES each.
    Greedy bin-packing over sorted keys for deterministic batches.
    """
    keys = sorted(delta.keys())
    if not keys:
        return []

    empty_body_bytes = len('{"entries":{}}'.encode("utf-8"))

    def entry_bytes(k: str, v: str) -> int:
        return (
            len(json_stringify(k).encode("utf-8"))
            + len(json_stringify(v).encode("utf-8"))
            + 2  # colon + comma (over-counts last by 1; harmless slack)
        )

    batches: List[Dict[str, str]] = []
    current: Dict[str, str] = {}
    current_bytes = empty_body_bytes

    for key in keys:
        added = entry_bytes(key, delta[key])
        if current_bytes + added > MAX_PUT_BODY_BYTES and current:
            batches.append(current)
            current = {}
            current_bytes = empty_body_bytes
        current[key] = delta[key]
        current_bytes += added

    batches.append(current)
    return batches


async def upload_team_memory(
    state: SyncState,
    repo_slug: str,
    entries: Dict[str, str],
    if_match_checksum: Optional[str] = None,
) -> TeamMemorySyncUploadResult:
    """Upload team memory entries to the server."""
    try:
        await check_and_refresh_oauth_token_if_needed()

        auth_headers, auth_error = get_auth_headers()
        if auth_error:
            return TeamMemorySyncUploadResult(success=False, error=auth_error, error_type="auth")

        headers = dict(auth_headers)
        if if_match_checksum:
            clean = if_match_checksum.strip('"')
            headers["If-Match"] = f'"{clean}"'

        endpoint = get_team_memory_sync_endpoint(repo_slug)
        status, data, err = await _do_put(
            endpoint, headers, {"entries": entries}, allowed_statuses=(200, 412)
        )

        if status == 412:
            log_for_debugging("team-memory-sync: conflict (412 Precondition Failed)", level="info")
            return TeamMemorySyncUploadResult(success=False, conflict=True, error="ETag mismatch")

        if err and status is None:
            error_type = _classify_http_error(status, err)
            return TeamMemorySyncUploadResult(success=False, error=err, error_type=error_type)

        if status in (401, 403):
            return TeamMemorySyncUploadResult(
                success=False, error="Not authorized", error_type="auth", http_status=status
            )

        # Parse structured 413
        if status == 413:
            server_error_code = None
            server_max_entries = None
            server_received_entries = None
            if isinstance(data, dict):
                error_obj = data.get("error", {})
                details = error_obj.get("details", {}) if isinstance(error_obj, dict) else {}
                server_error_code = details.get("error_code")
                server_max_entries = details.get("max_entries")
                server_received_entries = details.get("received_entries")
            return TeamMemorySyncUploadResult(
                success=False,
                error=err or f"HTTP {status}",
                error_type="unknown",
                http_status=status,
                server_error_code=server_error_code,
                server_max_entries=server_max_entries,
                server_received_entries=server_received_entries,
            )

        if err:
            error_type = _classify_http_error(status, err)
            return TeamMemorySyncUploadResult(
                success=False, error=err, error_type=error_type, http_status=status
            )

        response_checksum = (data or {}).get("checksum")
        if response_checksum:
            state.last_known_checksum = response_checksum

        log_for_debugging(
            f"team-memory-sync: uploaded {len(entries)} entries (checksum: {response_checksum or 'none'})",
            level="debug",
        )
        return TeamMemorySyncUploadResult(
            success=True,
            checksum=response_checksum,
            last_modified=(data or {}).get("lastModified"),
        )

    except Exception as e:
        error_type = _classify_http_error(None, str(e))
        log_for_debugging(f"team-memory-sync: upload failed: {e}", level="warn")
        return TeamMemorySyncUploadResult(success=False, error=str(e), error_type=error_type)


# ─── Local file operations ─────────────────────────────────────────────────────

async def read_local_team_memory(
    max_entries: Optional[int],
) -> Tuple[Dict[str, str], List[Any]]:
    """
    Read all team memory files from the local directory into a flat key-value map.
    Returns (entries, skipped_secrets).

    Files containing detected secrets are skipped.
    Files exceeding MAX_FILE_SIZE_BYTES are skipped.
    """
    team_dir = get_team_mem_path()
    entries: Dict[str, str] = {}
    skipped_secrets: List[Any] = []

    async def walk_dir(dir_path: str) -> None:
        try:
            with os.scandir(dir_path) as it:
                dir_entries = list(it)
        except OSError as e:
            if e.errno not in (2, 13):  # ENOENT, EACCES
                raise
            return

        tasks = []
        for entry in dir_entries:
            full_path = os.path.join(dir_path, entry.name)
            if entry.is_dir(follow_symlinks=False):
                tasks.append(walk_dir(full_path))
            elif entry.is_file(follow_symlinks=False):
                tasks.append(read_file_entry(full_path))

        await asyncio.gather(*tasks)

    async def read_file_entry(full_path: str) -> None:
        try:
            stat_result = await asyncio.get_event_loop().run_in_executor(
                None, os.stat, full_path
            )
            if stat_result.st_size > MAX_FILE_SIZE_BYTES:
                log_for_debugging(
                    f"team-memory-sync: skipping oversized file {full_path} ({stat_result.st_size} > {MAX_FILE_SIZE_BYTES} bytes)",
                    level="info",
                )
                return

            content = await asyncio.get_event_loop().run_in_executor(
                None, lambda: Path(full_path).read_text(encoding="utf-8")
            )
            rel_path = os.path.relpath(full_path, team_dir).replace("\\", "/")

            # Scan for secrets before adding to upload payload
            secret_matches = scan_for_secrets(content)
            if secret_matches:
                first_match = secret_matches[0]
                rule_id = getattr(first_match, "rule_id", getattr(first_match, "ruleId", "unknown"))
                label = getattr(first_match, "label", "secret")
                sf = SkippedSecretFile(path=rel_path, rule_id=rule_id, label=label)
                skipped_secrets.append(sf)
                log_for_debugging(
                    f'team-memory-sync: skipping "{rel_path}" — detected {label}',
                    level="warn",
                )
                return

            entries[rel_path] = content

        except OSError:
            # Skip unreadable files
            pass

    await walk_dir(team_dir)

    # Truncate if we've learned a server cap
    all_keys = sorted(entries.keys())
    if max_entries is not None and len(all_keys) > max_entries:
        dropped = all_keys[max_entries:]
        log_for_debugging(
            f"team-memory-sync: {len(all_keys)} local entries exceeds server cap of {max_entries}; "
            f"{len(dropped)} file(s) will NOT sync: {', '.join(dropped)}. "
            "Consider consolidating or removing some team memory files.",
            level="warn",
        )
        log_event("tengu_team_mem_entries_capped", {
            "total_entries": len(all_keys),
            "dropped_count": len(dropped),
            "max_entries": max_entries,
        })
        truncated = {k: entries[k] for k in all_keys[:max_entries]}
        return truncated, skipped_secrets

    return entries, skipped_secrets


async def write_remote_entries_to_local(
    entries: Dict[str, str],
) -> int:
    """
    Write remote team memory entries to the local directory.
    Validates every path against the team memory directory boundary.
    Skips entries whose on-disk content already matches.

    Returns the number of files actually written.
    """
    results = await asyncio.gather(*[
        _write_single_entry(rel_path, content)
        for rel_path, content in entries.items()
    ])
    return sum(1 for r in results if r)


async def _write_single_entry(rel_path: str, content: str) -> bool:
    """Write a single remote entry to disk. Returns True if written."""
    try:
        validated_path = await validate_team_mem_key(rel_path)
    except PathTraversalError as e:
        log_for_debugging(f"team-memory-sync: {e}", level="warn")
        return False

    size_bytes = len(content.encode("utf-8"))
    if size_bytes > MAX_FILE_SIZE_BYTES:
        log_for_debugging(
            f'team-memory-sync: skipping oversized remote entry "{rel_path}"',
            level="info",
        )
        return False

    # Skip if on-disk content already matches
    try:
        existing = Path(validated_path).read_text(encoding="utf-8")
        if existing == content:
            return False
    except OSError as e:
        if e.errno not in (2, 20):  # ENOENT, ENOTDIR
            log_for_debugging(
                f'team-memory-sync: unexpected read error for "{rel_path}": {e.errno}',
                level="debug",
            )
        # Fall through to write

    try:
        parent_dir = str(Path(validated_path).parent)
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: os.makedirs(parent_dir, exist_ok=True)
        )
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: Path(validated_path).write_text(content, encoding="utf-8")
        )
        return True
    except OSError as e:
        log_for_debugging(f'team-memory-sync: failed to write "{rel_path}": {e}', level="warn")
        return False


# ─── Public API ───────────────────────────────────────────────────────────────

def is_team_memory_sync_available() -> bool:
    """Check if team memory sync is available (requires first-party OAuth)."""
    return is_using_oauth()


async def pull_team_memory(
    state: SyncState,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Pull team memory from the server and write to local directory.
    Returns dict with success, files_written, entry_count, and optionally error/not_modified.
    """
    skip_etag_cache = (options or {}).get("skip_etag_cache", False)
    start_time = _now_ms()

    if not is_using_oauth():
        _log_pull(start_time, success=False, error_type="no_oauth")
        return {"success": False, "files_written": 0, "entry_count": 0, "error": "OAuth not available"}

    repo_slug = await get_github_repo()
    if not repo_slug:
        _log_pull(start_time, success=False, error_type="no_repo")
        return {"success": False, "files_written": 0, "entry_count": 0, "error": "No git remote found"}

    etag = None if skip_etag_cache else state.last_known_checksum
    result = await fetch_team_memory(state, repo_slug, etag)

    if not result.success:
        _log_pull(start_time, success=False, error_type=result.error_type, status=result.http_status)
        return {"success": False, "files_written": 0, "entry_count": 0, "error": result.error}

    if result.not_modified:
        _log_pull(start_time, success=True, not_modified=True)
        return {"success": True, "files_written": 0, "entry_count": 0, "not_modified": True}

    if result.is_empty or not result.data:
        state.server_checksums.clear()
        _log_pull(start_time, success=True)
        return {"success": True, "files_written": 0, "entry_count": 0}

    content = result.data.get("content", {})
    remote_entries = content.get("entries", {})
    response_checksums = content.get("entryChecksums")

    # Refresh server_checksums from server-provided per-key hashes
    state.server_checksums.clear()
    if response_checksums:
        for key, hash_val in response_checksums.items():
            state.server_checksums[key] = hash_val
    else:
        log_for_debugging(
            "team-memory-sync: server response missing entryChecksums — next push will be full, not delta",
            level="debug",
        )

    files_written = await write_remote_entries_to_local(remote_entries)
    if files_written > 0:
        try:
            from claude_code.utils.claudemd import clear_memory_file_caches
            clear_memory_file_caches()
        except ImportError:
            pass

    log_for_debugging(f"team-memory-sync: pulled {files_written} files", level="info")
    _log_pull(start_time, success=True, files_written=files_written)

    return {
        "success": True,
        "files_written": files_written,
        "entry_count": len(remote_entries),
    }


async def push_team_memory(state: SyncState) -> TeamMemorySyncPushResult:
    """
    Push local team memory files to the server with optimistic locking.

    Uses delta upload: only keys whose local content hash differs from
    server_checksums are included in the PUT. On 412 conflict, probes
    GET ?view=hashes to refresh server_checksums and retries.
    """
    start_time = _now_ms()
    conflict_retries = 0

    if not is_using_oauth():
        _log_push(start_time, success=False, error_type="no_oauth")
        return TeamMemorySyncPushResult(
            success=False, files_uploaded=0, error="OAuth not available", error_type="no_oauth"
        )

    repo_slug = await get_github_repo()
    if not repo_slug:
        _log_push(start_time, success=False, error_type="no_repo")
        return TeamMemorySyncPushResult(
            success=False, files_uploaded=0, error="No git remote found", error_type="no_repo"
        )

    # Read local entries once at the start
    entries, skipped_secrets = await read_local_team_memory(state.server_max_entries)
    if skipped_secrets:
        summary = ", ".join(f'"{s.path}" ({s.label})' for s in skipped_secrets)
        log_for_debugging(
            f"team-memory-sync: {len(skipped_secrets)} file(s) skipped due to detected secrets: {summary}. "
            "Remove the secret(s) to enable sync for these files.",
            level="warn",
        )
        log_event("tengu_team_mem_secret_skipped", {
            "file_count": len(skipped_secrets),
            "rule_ids": ",".join(s.rule_id for s in skipped_secrets),
        })

    # Hash each local entry once
    local_hashes: Dict[str, str] = {key: hash_content(content) for key, content in entries.items()}

    saw_conflict = False

    for conflict_attempt in range(MAX_CONFLICT_RETRIES + 1):
        # Delta: only upload keys whose content hash differs from server state
        delta = {
            key: entries[key]
            for key, local_hash in local_hashes.items()
            if state.server_checksums.get(key) != local_hash
        }
        delta_count = len(delta)

        if delta_count == 0:
            _log_push(start_time, success=True, conflict=saw_conflict, conflict_retries=conflict_retries)
            return TeamMemorySyncPushResult(
                success=True,
                files_uploaded=0,
                skipped_secrets=skipped_secrets if skipped_secrets else None,
            )

        # Split delta into PUT-sized batches
        batches = batch_delta_by_bytes(delta)
        files_uploaded = 0
        last_result: Optional[TeamMemorySyncUploadResult] = None

        for batch in batches:
            last_result = await upload_team_memory(
                state, repo_slug, batch, state.last_known_checksum
            )
            if not last_result.success:
                break
            # Update server_checksums for successfully uploaded keys
            for key in batch:
                state.server_checksums[key] = local_hashes[key]
            files_uploaded += len(batch)

        # Should always be set since batches is non-empty
        result = last_result  # type: ignore[assignment]

        if result.success:
            log_for_debugging(
                (
                    f"team-memory-sync: pushed {files_uploaded} of {len(local_hashes)} files "
                    f"in {len(batches)} batches"
                    if len(batches) > 1
                    else f"team-memory-sync: pushed {files_uploaded} of {len(local_hashes)} files (delta)"
                ),
                level="info",
            )
            _log_push(
                start_time,
                success=True,
                files_uploaded=files_uploaded,
                conflict=saw_conflict,
                conflict_retries=conflict_retries,
                put_batches=len(batches) if len(batches) > 1 else None,
            )
            return TeamMemorySyncPushResult(
                success=True,
                files_uploaded=files_uploaded,
                checksum=result.checksum,
                skipped_secrets=skipped_secrets if skipped_secrets else None,
            )

        if not result.conflict:
            # Cache learned server max_entries from structured 413
            if result.server_max_entries is not None:
                state.server_max_entries = result.server_max_entries
                log_for_debugging(
                    f"team-memory-sync: learned server max_entries={result.server_max_entries} from 413; next push will truncate to this",
                    level="warn",
                )
            _log_push(
                start_time,
                success=False,
                files_uploaded=files_uploaded,
                conflict_retries=conflict_retries,
                put_batches=len(batches) if len(batches) > 1 else None,
                error_type=result.error_type,
                status=result.http_status,
                error_code=result.server_error_code,
                server_max_entries=result.server_max_entries,
                server_received_entries=result.server_received_entries,
            )
            return TeamMemorySyncPushResult(
                success=False,
                files_uploaded=files_uploaded,
                error=result.error,
                error_type=result.error_type,
                http_status=result.http_status,
            )

        # 412 conflict — refresh server_checksums and retry
        saw_conflict = True
        if conflict_attempt >= MAX_CONFLICT_RETRIES:
            log_for_debugging(
                f"team-memory-sync: giving up after {MAX_CONFLICT_RETRIES} conflict retries",
                level="warn",
            )
            _log_push(
                start_time, success=False, conflict=True,
                conflict_retries=conflict_retries, error_type="conflict"
            )
            return TeamMemorySyncPushResult(
                success=False,
                files_uploaded=0,
                conflict=True,
                error="Conflict resolution failed after retries",
            )

        conflict_retries += 1
        log_for_debugging(
            f"team-memory-sync: conflict (412), probing server hashes (attempt {conflict_attempt + 1}/{MAX_CONFLICT_RETRIES})",
            level="info",
        )

        # Cheap probe: fetch only per-key checksums
        probe = await fetch_team_memory_hashes(state, repo_slug)
        if not probe.success or not probe.entry_checksums:
            _log_push(
                start_time, success=False, conflict=True,
                conflict_retries=conflict_retries, error_type="conflict"
            )
            return TeamMemorySyncPushResult(
                success=False,
                files_uploaded=0,
                conflict=True,
                error=f"Conflict resolution hashes probe failed: {probe.error}",
            )

        state.server_checksums.clear()
        for key, hash_val in probe.entry_checksums.items():
            state.server_checksums[key] = hash_val

    _log_push(start_time, success=False, conflict_retries=conflict_retries)
    return TeamMemorySyncPushResult(
        success=False,
        files_uploaded=0,
        error="Unexpected end of conflict resolution loop",
    )


async def sync_team_memory(state: SyncState) -> Dict[str, Any]:
    """
    Bidirectional sync: pull from server, merge with local, push back.
    Server entries take precedence on conflict (last-write-wins by the server).
    """
    # 1. Pull remote → local (skip ETag cache for full sync)
    pull_result = await pull_team_memory(state, {"skip_etag_cache": True})
    if not pull_result["success"]:
        return {
            "success": False,
            "files_pulled": 0,
            "files_pushed": 0,
            "error": pull_result.get("error"),
        }

    # 2. Push local → remote (with conflict resolution)
    push_result = await push_team_memory(state)
    if not push_result.success:
        return {
            "success": False,
            "files_pulled": pull_result["files_written"],
            "files_pushed": 0,
            "error": push_result.error,
        }

    log_for_debugging(
        f"team-memory-sync: synced (pulled {pull_result['files_written']}, pushed {push_result.files_uploaded})",
        level="info",
    )
    return {
        "success": True,
        "files_pulled": pull_result["files_written"],
        "files_pushed": push_result.files_uploaded,
    }


# ─── Telemetry helpers ────────────────────────────────────────────────────────

def _now_ms() -> int:
    import time
    return int(time.time() * 1000)


def _log_pull(
    start_time: int,
    *,
    success: bool,
    files_written: int = 0,
    not_modified: bool = False,
    error_type: Optional[str] = None,
    status: Optional[int] = None,
) -> None:
    props: Dict[str, Any] = {
        "success": success,
        "files_written": files_written,
        "not_modified": not_modified,
        "duration_ms": _now_ms() - start_time,
    }
    if error_type:
        props["errorType"] = error_type
    if status:
        props["status"] = status
    log_event("tengu_team_mem_sync_pull", props)


def _log_push(
    start_time: int,
    *,
    success: bool,
    files_uploaded: int = 0,
    conflict: bool = False,
    conflict_retries: int = 0,
    error_type: Optional[str] = None,
    status: Optional[int] = None,
    put_batches: Optional[int] = None,
    error_code: Optional[str] = None,
    server_max_entries: Optional[int] = None,
    server_received_entries: Optional[int] = None,
) -> None:
    props: Dict[str, Any] = {
        "success": success,
        "files_uploaded": files_uploaded,
        "conflict": conflict,
        "conflict_retries": conflict_retries,
        "duration_ms": _now_ms() - start_time,
    }
    if error_type:
        props["errorType"] = error_type
    if status:
        props["status"] = status
    if put_batches:
        props["put_batches"] = put_batches
    if error_code:
        props["error_code"] = error_code
    if server_max_entries is not None:
        props["server_max_entries"] = server_max_entries
    if server_received_entries is not None:
        props["server_received_entries"] = server_received_entries
    log_event("tengu_team_mem_sync_push", props)


# ─── Public exports ───────────────────────────────────────────────────────────

__all__ = [
    "SyncState",
    "SkippedSecretFile",
    "TeamMemoryHashesResult",
    "TeamMemorySyncFetchResult",
    "TeamMemorySyncPushResult",
    "TeamMemorySyncUploadResult",
    "batch_delta_by_bytes",
    "create_sync_state",
    "fetch_team_memory",
    "fetch_team_memory_hashes",
    "fetch_team_memory_once",
    "hash_content",
    "is_team_memory_sync_available",
    "pull_team_memory",
    "push_team_memory",
    "read_local_team_memory",
    "sync_team_memory",
    "upload_team_memory",
    "write_remote_entries_to_local",
]
