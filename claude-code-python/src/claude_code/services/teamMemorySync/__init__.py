"""
Team Memory Sync Service

Syncs team memory files between the local filesystem and the server API.
Team memory is scoped per-repo (identified by git remote hash) and shared
across all authenticated org members.

API contract:
  GET  /api/claude_code/team_memory?repo={owner/repo}             → TeamMemoryData (includes entryChecksums)
  GET  /api/claude_code/team_memory?repo={owner/repo}&view=hashes → metadata + entryChecksums only (no entry bodies)
  PUT  /api/claude_code/team_memory?repo={owner/repo}             → upload entries (upsert semantics)
  404 = no data exists yet

Sync semantics:
  - Pull overwrites local files with server content (server wins per-key).
  - Push uploads only keys whose content hash differs from server_checksums
    (delta upload). Server uses upsert: keys not in the PUT are preserved.
  - File deletions do NOT propagate: deleting a local file won't remove it
    from the server, and the next pull will restore it locally.

State management:
  All mutable state (ETag tracking, watcher suppression) lives in a
  SyncState object created by the caller and threaded through every call.
  This avoids module-level mutable state and gives tests natural isolation.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlencode, quote

import aiohttp

from claude_code.constants.oauth import (
    CLAUDE_AI_INFERENCE_SCOPE,
    CLAUDE_AI_PROFILE_SCOPE,
    get_oauth_config,
    OAUTH_BETA_HEADER,
)
from claude_code.memdir.team_mem_paths import (
    get_team_mem_path,
    PathTraversalError,
    validate_team_mem_key,
)
from claude_code.utils.array import count
from claude_code.utils.auth import (
    check_and_refresh_oauth_token_if_needed,
    get_claude_ai_oauth_tokens,
)
from claude_code.utils.debug import log_for_debugging
from claude_code.utils.errors import classify_request_error
from claude_code.utils.git import get_github_repo
from claude_code.utils.model.providers import (
    get_api_provider,
    is_first_party_anthropic_base_url,
)
from claude_code.utils.sleep import sleep
from claude_code.utils.slow_operations import json_stringify
from claude_code.utils.user_agent import get_claude_code_user_agent
from claude_code.services.analytics import log_event
from claude_code.services.api.with_retry import get_retry_delay
from claude_code.services.teamMemorySync.secret_scanner import scan_for_secrets
from claude_code.services.teamMemorySync.types import (
    SkippedSecretFile,
    TeamMemoryData,
    TeamMemoryHashesResult,
    TeamMemorySyncFetchResult,
    TeamMemorySyncPushResult,
    TeamMemorySyncUploadResult,
    parse_team_memory_data,
    parse_team_memory_too_many_entries,
)

TEAM_MEMORY_SYNC_TIMEOUT_S = 30.0
# Per-entry size cap — server default.
# Pre-filtering oversized entries saves bandwidth.
MAX_FILE_SIZE_BYTES = 250_000
# Gateway body-size cap. The API gateway rejects PUT bodies over ~256-512KB.
# 200KB leaves headroom under the observed threshold.
MAX_PUT_BODY_BYTES = 200_000
MAX_RETRIES = 3
MAX_CONFLICT_RETRIES = 2


# ─── Sync state ─────────────────────────────────────────────


@dataclass
class SyncState:
    """
    Mutable state for the team memory sync service.
    Created once per session by the watcher and passed to all sync functions.
    Tests create a fresh instance per test for isolation.
    """

    # Last known server checksum (ETag) for conditional requests.
    last_known_checksum: Optional[str] = None

    # Per-key content hash (`sha256:<hex>`) of what we believe the server
    # currently holds. Populated from server-provided entry_checksums on pull
    # and from local hashes on successful push.
    server_checksums: dict[str, str] = field(default_factory=dict)

    # Server-enforced max_entries cap, learned from a structured 413 response.
    # Stays None until a 413 is observed.
    server_max_entries: Optional[int] = None


def create_sync_state() -> SyncState:
    """Create a fresh SyncState with empty/null fields."""
    return SyncState()


def hash_content(content: str) -> str:
    """
    Compute `sha256:<hex>` over the UTF-8 bytes of the given content.
    Format matches the server's entry_checksums values so local-vs-server
    comparison works by direct string equality.
    """
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _is_errno_exception(e: BaseException) -> bool:
    """Check if an exception is an OS-level error with an errno."""
    return isinstance(e, OSError)


# ─── Auth & endpoint ─────────────────────────────────────────


def _is_using_oauth() -> bool:
    """Check if user is authenticated with first-party OAuth (required for team memory sync)."""
    if get_api_provider() != "firstParty" or not is_first_party_anthropic_base_url():
        return False
    tokens = get_claude_ai_oauth_tokens()
    if not tokens or not tokens.get("accessToken"):
        return False
    scopes = tokens.get("scopes", [])
    return (
        CLAUDE_AI_INFERENCE_SCOPE in scopes and CLAUDE_AI_PROFILE_SCOPE in scopes
    )


def _get_team_memory_sync_endpoint(repo_slug: str) -> str:
    base_url = os.environ.get("TEAM_MEMORY_SYNC_URL") or get_oauth_config()["BASE_API_URL"]
    return f"{base_url}/api/claude_code/team_memory?repo={quote(repo_slug, safe='')}"


def _get_auth_headers() -> dict[str, Any]:
    """Returns {'headers': {...}} or {'error': '...'}."""
    oauth_tokens = get_claude_ai_oauth_tokens()
    if oauth_tokens and oauth_tokens.get("accessToken"):
        return {
            "headers": {
                "Authorization": f"Bearer {oauth_tokens['accessToken']}",
                "anthropic-beta": OAUTH_BETA_HEADER,
                "User-Agent": get_claude_code_user_agent(),
            }
        }
    return {"error": "No OAuth token available for team memory sync"}


# ─── Fetch (pull) ────────────────────────────────────────────


async def _fetch_team_memory_once(
    state: SyncState,
    repo_slug: str,
    etag: Optional[str] = None,
) -> TeamMemorySyncFetchResult:
    try:
        await check_and_refresh_oauth_token_if_needed()

        auth = _get_auth_headers()
        if "error" in auth:
            return TeamMemorySyncFetchResult(
                success=False,
                error=auth["error"],
                skip_retry=True,
                error_type="auth",
            )

        headers: dict[str, str] = dict(auth["headers"])
        if etag:
            clean_etag = etag.replace('"', "")
            headers["If-None-Match"] = f'"{clean_etag}"'

        endpoint = _get_team_memory_sync_endpoint(repo_slug)

        async with aiohttp.ClientSession() as session:
            async with session.get(
                endpoint,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=TEAM_MEMORY_SYNC_TIMEOUT_S),
                allow_redirects=True,
            ) as response:
                status = response.status

                if status == 304:
                    log_for_debugging(
                        "team-memory-sync: not modified (304)", level="debug"
                    )
                    return TeamMemorySyncFetchResult(
                        success=True, not_modified=True, checksum=etag or None
                    )

                if status == 404:
                    log_for_debugging(
                        "team-memory-sync: no remote data (404)", level="debug"
                    )
                    state.last_known_checksum = None
                    return TeamMemorySyncFetchResult(success=True, is_empty=True)

                if status != 200:
                    body = await response.text()
                    log_for_debugging(
                        f"team-memory-sync: unexpected status {status}: {body}",
                        level="warn",
                    )
                    error_type = _http_status_to_error_type(status)
                    return TeamMemorySyncFetchResult(
                        success=False,
                        error=f"HTTP {status}",
                        error_type=error_type,
                        http_status=status,
                    )

                raw_data = await response.json()
                parsed = parse_team_memory_data(raw_data)
                if parsed is None:
                    log_for_debugging(
                        "team-memory-sync: invalid response format", level="warn"
                    )
                    return TeamMemorySyncFetchResult(
                        success=False,
                        error="Invalid team memory response format",
                        skip_retry=True,
                        error_type="parse",
                    )

                # Extract checksum from response data or ETag header
                etag_header = response.headers.get("etag", "").strip('"')
                response_checksum = parsed.get("checksum") or etag_header or None
                if response_checksum:
                    state.last_known_checksum = response_checksum

                log_for_debugging(
                    f"team-memory-sync: fetched successfully (checksum: {response_checksum or 'none'})",
                    level="debug",
                )
                return TeamMemorySyncFetchResult(
                    success=True,
                    data=parsed,
                    is_empty=False,
                    checksum=response_checksum,
                )

    except asyncio.TimeoutError:
        return TeamMemorySyncFetchResult(
            success=False,
            error="Team memory sync request timeout",
            error_type="timeout",
        )
    except aiohttp.ClientConnectionError:
        return TeamMemorySyncFetchResult(
            success=False,
            error="Cannot connect to server",
            error_type="network",
        )
    except Exception as e:
        kind, status, message = classify_request_error(e)
        return TeamMemorySyncFetchResult(
            success=False,
            error=message,
            error_type="unknown",
            http_status=status,
        )


async def _fetch_team_memory_hashes(
    state: SyncState,
    repo_slug: str,
) -> TeamMemoryHashesResult:
    """
    Fetch only per-key checksums + metadata (no entry bodies).
    Used for cheap server_checksums refresh during 412 conflict resolution.
    Requires view=hashes endpoint support.
    """
    try:
        await check_and_refresh_oauth_token_if_needed()
        auth = _get_auth_headers()
        if "error" in auth:
            return TeamMemoryHashesResult(
                success=False, error=auth["error"], error_type="auth"
            )

        endpoint = _get_team_memory_sync_endpoint(repo_slug) + "&view=hashes"

        async with aiohttp.ClientSession() as session:
            async with session.get(
                endpoint,
                headers=auth["headers"],
                timeout=aiohttp.ClientTimeout(total=TEAM_MEMORY_SYNC_TIMEOUT_S),
            ) as response:
                status = response.status

                if status == 404:
                    state.last_known_checksum = None
                    return TeamMemoryHashesResult(
                        success=True, entry_checksums={}
                    )

                if status != 200:
                    return TeamMemoryHashesResult(
                        success=False,
                        error=f"HTTP {status}",
                        error_type=_http_status_to_error_type(status),
                        http_status=status,
                    )

                raw_data = await response.json()
                etag_header = response.headers.get("etag", "").strip('"')
                checksum = raw_data.get("checksum") or etag_header or None
                entry_checksums = raw_data.get("entryChecksums")

                # Requires view=hashes support. If entry_checksums is missing,
                # treat as a probe failure.
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
                    version=raw_data.get("version"),
                    checksum=checksum,
                    entry_checksums=entry_checksums,
                )

    except asyncio.TimeoutError:
        return TeamMemoryHashesResult(
            success=False, error="Timeout", error_type="timeout"
        )
    except aiohttp.ClientConnectionError:
        return TeamMemoryHashesResult(
            success=False, error="Network error", error_type="network"
        )
    except Exception as e:
        _, status, message = classify_request_error(e)
        return TeamMemoryHashesResult(
            success=False,
            error=message,
            error_type="unknown",
            http_status=status,
        )


async def _fetch_team_memory(
    state: SyncState,
    repo_slug: str,
    etag: Optional[str] = None,
) -> TeamMemorySyncFetchResult:
    last_result: Optional[TeamMemorySyncFetchResult] = None

    for attempt in range(1, MAX_RETRIES + 2):
        last_result = await _fetch_team_memory_once(state, repo_slug, etag)
        if last_result.success or last_result.skip_retry:
            return last_result
        if attempt > MAX_RETRIES:
            return last_result
        delay_ms = get_retry_delay(attempt)
        log_for_debugging(
            f"team-memory-sync: retry {attempt}/{MAX_RETRIES}", level="debug"
        )
        await sleep(delay_ms)

    return last_result  # type: ignore[return-value]


# ─── Upload (push) ───────────────────────────────────────────


def batch_delta_by_bytes(
    delta: dict[str, str],
) -> list[dict[str, str]]:
    """
    Split a delta into PUT-sized batches under MAX_PUT_BODY_BYTES each.

    Greedy bin-packing over sorted keys — sorting gives deterministic batches
    across calls. The byte count is the full serialized body including JSON
    overhead.

    A single entry exceeding MAX_PUT_BODY_BYTES goes into its own solo batch.
    """
    keys = sorted(delta.keys())
    if not keys:
        return []

    EMPTY_BODY_BYTES = len('{"entries":{}}'.encode("utf-8"))

    def entry_bytes(k: str, v: str) -> int:
        return (
            len(json.dumps(k).encode("utf-8"))
            + len(json.dumps(v).encode("utf-8"))
            + 2  # colon + comma (over-counts last entry by 1; harmless)
        )

    batches: list[dict[str, str]] = []
    current: dict[str, str] = {}
    current_bytes = EMPTY_BODY_BYTES

    for key in keys:
        added = entry_bytes(key, delta[key])
        if current_bytes + added > MAX_PUT_BODY_BYTES and len(current) > 0:
            batches.append(current)
            current = {}
            current_bytes = EMPTY_BODY_BYTES
        current[key] = delta[key]
        current_bytes += added

    batches.append(current)
    return batches


async def _upload_team_memory(
    state: SyncState,
    repo_slug: str,
    entries: dict[str, str],
    if_match_checksum: Optional[str] = None,
) -> TeamMemorySyncUploadResult:
    try:
        await check_and_refresh_oauth_token_if_needed()

        auth = _get_auth_headers()
        if "error" in auth:
            return TeamMemorySyncUploadResult(
                success=False, error=auth["error"], error_type="auth"
            )

        headers: dict[str, str] = {
            **auth["headers"],
            "Content-Type": "application/json",
        }
        if if_match_checksum:
            clean = if_match_checksum.replace('"', "")
            headers["If-Match"] = f'"{clean}"'

        endpoint = _get_team_memory_sync_endpoint(repo_slug)
        payload = json.dumps({"entries": entries}).encode("utf-8")

        async with aiohttp.ClientSession() as session:
            async with session.put(
                endpoint,
                data=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=TEAM_MEMORY_SYNC_TIMEOUT_S),
            ) as response:
                status = response.status

                if status == 412:
                    log_for_debugging(
                        "team-memory-sync: conflict (412 Precondition Failed)",
                        level="info",
                    )
                    return TeamMemorySyncUploadResult(
                        success=False, conflict=True, error="ETag mismatch"
                    )

                if status == 413:
                    # Try to parse structured too-many-entries 413
                    try:
                        raw_data = await response.json(content_type=None)
                        parsed = parse_team_memory_too_many_entries(raw_data)
                    except Exception:
                        parsed = None

                    result = TeamMemorySyncUploadResult(
                        success=False,
                        error=f"HTTP 413",
                        error_type="unknown",
                        http_status=413,
                    )
                    if parsed:
                        details = parsed["error"]["details"]
                        result.server_error_code = details.get("error_code")
                        result.server_max_entries = details.get("max_entries")
                        result.server_received_entries = details.get(
                            "received_entries"
                        )
                    return result

                if status != 200:
                    body = await response.text()
                    log_for_debugging(
                        f"team-memory-sync: upload failed with status {status}: {body}",
                        level="warn",
                    )
                    return TeamMemorySyncUploadResult(
                        success=False,
                        error=f"HTTP {status}: {body}",
                        error_type=_http_status_to_error_type(status),
                        http_status=status,
                    )

                raw_data = await response.json()
                response_checksum = raw_data.get("checksum")
                if response_checksum:
                    state.last_known_checksum = response_checksum

                log_for_debugging(
                    f"team-memory-sync: uploaded {len(entries)} entries "
                    f"(checksum: {response_checksum or 'none'})",
                    level="debug",
                )
                return TeamMemorySyncUploadResult(
                    success=True,
                    checksum=response_checksum,
                    last_modified=raw_data.get("lastModified"),
                )

    except asyncio.TimeoutError:
        return TeamMemorySyncUploadResult(
            success=False,
            error="Team memory sync request timeout",
            error_type="timeout",
        )
    except aiohttp.ClientConnectionError:
        return TeamMemorySyncUploadResult(
            success=False, error="Cannot connect to server", error_type="network"
        )
    except Exception as e:
        log_for_debugging(
            f"team-memory-sync: upload failed: {e}", level="warn"
        )
        _, http_status, message = classify_request_error(e)
        return TeamMemorySyncUploadResult(
            success=False,
            error=message,
            error_type="unknown",
            http_status=http_status,
        )


# ─── Local file operations ───────────────────────────────────


async def _read_local_team_memory(
    max_entries: Optional[int],
) -> tuple[dict[str, str], list[SkippedSecretFile]]:
    """
    Read all team memory files from the local directory into a flat key-value map.
    Keys are relative paths from the team memory directory.
    Empty files are included (content will be empty string).

    Files containing secrets (detected via scan_for_secrets) are SKIPPED
    and collected in skipped_secrets so the caller can warn the user.

    Returns:
        (entries, skipped_secrets)
    """
    team_dir = get_team_mem_path()
    entries: dict[str, str] = {}
    skipped_secrets: list[SkippedSecretFile] = []

    async def walk_dir(dir_path: str) -> None:
        try:
            dir_entries = await asyncio.to_thread(os.scandir, dir_path)
        except OSError as e:
            if e.errno not in (
                2,  # ENOENT
                13,  # EACCES
                1,  # EPERM
            ):
                raise
            return

        tasks = []
        for entry in dir_entries:
            full_path = entry.path
            if entry.is_dir(follow_symlinks=False):
                tasks.append(walk_dir(full_path))
            elif entry.is_file(follow_symlinks=False):
                tasks.append(_read_file_entry(full_path, team_dir, entries, skipped_secrets))

        await asyncio.gather(*tasks)

    async def _read_file_entry(
        full_path: str,
        base_dir: str,
        out_entries: dict[str, str],
        out_skipped: list[SkippedSecretFile],
    ) -> None:
        try:
            stat_info = await asyncio.to_thread(os.stat, full_path)
            if stat_info.st_size > MAX_FILE_SIZE_BYTES:
                name = os.path.basename(full_path)
                log_for_debugging(
                    f"team-memory-sync: skipping oversized file {name} "
                    f"({stat_info.st_size} > {MAX_FILE_SIZE_BYTES} bytes)",
                    level="info",
                )
                return

            async with _open_async(full_path) as content:
                rel_path = os.path.relpath(full_path, base_dir).replace("\\", "/")

                # Scan for secrets BEFORE adding to the upload payload
                secret_matches = scan_for_secrets(content)
                if secret_matches:
                    first_match = secret_matches[0]
                    out_skipped.append(
                        SkippedSecretFile(
                            path=rel_path,
                            rule_id=first_match["ruleId"],
                            label=first_match["label"],
                        )
                    )
                    log_for_debugging(
                        f'team-memory-sync: skipping "{rel_path}" — '
                        f'detected {first_match["label"]}',
                        level="warn",
                    )
                    return

                out_entries[rel_path] = content
        except OSError:
            # Skip unreadable files
            pass

    await walk_dir(team_dir)

    # Deterministic truncation: sort before applying max_entries cap.
    # Without sorting, parallel walk produces different subsets each run,
    # causing the delta to balloon to near-full snapshot.
    keys = sorted(entries.keys())
    if max_entries is not None and len(keys) > max_entries:
        dropped = keys[max_entries:]
        log_for_debugging(
            f"team-memory-sync: {len(keys)} local entries exceeds server cap of "
            f"{max_entries}; {len(dropped)} file(s) will NOT sync: "
            f"{', '.join(dropped)}. Consider consolidating or removing some team memory files.",
            level="warn",
        )
        log_event(
            "tengu_team_mem_entries_capped",
            {
                "total_entries": len(keys),
                "dropped_count": len(dropped),
                "max_entries": max_entries,
            },
        )
        truncated = {k: entries[k] for k in keys[:max_entries]}
        return truncated, skipped_secrets

    return {k: entries[k] for k in keys}, skipped_secrets


class _open_async:
    """Async context manager for reading a file as UTF-8 text via thread pool."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._content: str = ""

    async def __aenter__(self) -> str:
        self._content = await asyncio.to_thread(
            lambda: open(self._path, encoding="utf-8").read()
        )
        return self._content

    async def __aexit__(self, *_: Any) -> None:
        pass


async def _write_remote_entries_to_local(
    entries: dict[str, str],
) -> int:
    """
    Write remote team memory entries to the local directory.
    Validates every path against the team memory directory boundary.
    Skips entries whose on-disk content already matches, so unchanged
    files keep their mtime and don't spuriously trigger watcher events.

    Returns the number of files actually written.
    """
    results = await asyncio.gather(
        *[_write_single_entry(rel_path, content) for rel_path, content in entries.items()],
        return_exceptions=False,
    )
    return count(results, bool)


async def _write_single_entry(rel_path: str, content: str) -> bool:
    """Validate, compare, and write a single remote entry to disk."""
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
        existing = await asyncio.to_thread(
            lambda: open(validated_path, encoding="utf-8").read()
        )
        if existing == content:
            return False
    except OSError as e:
        if e.errno not in (2, 20):  # ENOENT, ENOTDIR
            log_for_debugging(
                f'team-memory-sync: unexpected read error for "{rel_path}": {e.errno}',
                level="debug",
            )
        # Fall through to write for ENOENT/ENOTDIR

    try:
        parent_dir = os.path.dirname(validated_path)
        await asyncio.to_thread(
            lambda: os.makedirs(parent_dir, exist_ok=True)
        )
        await asyncio.to_thread(
            lambda: open(validated_path, "w", encoding="utf-8").write(content)
        )
        return True
    except OSError as e:
        log_for_debugging(
            f'team-memory-sync: failed to write "{rel_path}": {e}', level="warn"
        )
        return False


# ─── Public API ──────────────────────────────────────────────


def is_team_memory_sync_available() -> bool:
    """Check if team memory sync is available (requires first-party OAuth)."""
    return _is_using_oauth()


async def pull_team_memory(
    state: SyncState,
    skip_etag_cache: bool = False,
) -> dict[str, Any]:
    """
    Pull team memory from the server and write to local directory.
    Returns dict with: success, files_written, entry_count, not_modified, error.
    """
    start_time = _now_ms()

    if not _is_using_oauth():
        _log_pull(start_time, {"success": False, "error_type": "no_oauth"})
        return {
            "success": False,
            "files_written": 0,
            "entry_count": 0,
            "error": "OAuth not available",
        }

    repo_slug = await get_github_repo()
    if not repo_slug:
        _log_pull(start_time, {"success": False, "error_type": "no_repo"})
        return {
            "success": False,
            "files_written": 0,
            "entry_count": 0,
            "error": "No git remote found",
        }

    etag = None if skip_etag_cache else state.last_known_checksum
    result = await _fetch_team_memory(state, repo_slug, etag)

    if not result.success:
        _log_pull(
            start_time,
            {
                "success": False,
                "error_type": result.error_type,
                "status": result.http_status,
            },
        )
        return {
            "success": False,
            "files_written": 0,
            "entry_count": 0,
            "error": result.error,
        }

    if result.not_modified:
        _log_pull(start_time, {"success": True, "not_modified": True})
        return {
            "success": True,
            "files_written": 0,
            "entry_count": 0,
            "not_modified": True,
        }

    if result.is_empty or not result.data:
        # Server has no data — clear stale server_checksums
        state.server_checksums.clear()
        _log_pull(start_time, {"success": True})
        return {"success": True, "files_written": 0, "entry_count": 0}

    entries = result.data["content"]["entries"]
    response_checksums = result.data["content"].get("entryChecksums")

    # Refresh server_checksums from server-provided per-key hashes.
    state.server_checksums.clear()
    if response_checksums:
        state.server_checksums.update(response_checksums)
    else:
        log_for_debugging(
            "team-memory-sync: server response missing entryChecksums "
            "(pre-#283027 deploy) — next push will be full, not delta",
            level="debug",
        )

    files_written = await _write_remote_entries_to_local(entries)
    if files_written > 0:
        from claude_code.utils.claudemd import clear_memory_file_caches
        clear_memory_file_caches()

    log_for_debugging(
        f"team-memory-sync: pulled {files_written} files", level="info"
    )
    _log_pull(start_time, {"success": True, "files_written": files_written})

    return {
        "success": True,
        "files_written": files_written,
        "entry_count": len(entries),
    }


async def push_team_memory(state: SyncState) -> TeamMemorySyncPushResult:
    """
    Push local team memory files to the server with optimistic locking.

    Uses delta upload: only keys whose local content hash differs from
    server_checksums are included in the PUT. On 412 conflict, probes
    GET ?view=hashes to refresh server_checksums, recomputes the delta,
    and retries. No merge, no disk writes.

    Local-wins-on-conflict is intentional: push is triggered by a local edit,
    and that edit must not be silently discarded.
    """
    start_time = _now_ms()
    conflict_retries = 0

    if not _is_using_oauth():
        _log_push(start_time, {"success": False, "error_type": "no_oauth"})
        return TeamMemorySyncPushResult(
            success=False,
            files_uploaded=0,
            error="OAuth not available",
            error_type="no_oauth",
        )

    repo_slug = await get_github_repo()
    if not repo_slug:
        _log_push(start_time, {"success": False, "error_type": "no_repo"})
        return TeamMemorySyncPushResult(
            success=False,
            files_uploaded=0,
            error="No git remote found",
            error_type="no_repo",
        )

    # Read local entries once at the start. Conflict resolution does NOT re-read
    # from disk. Secret scanning happens here once.
    entries, skipped_secrets = await _read_local_team_memory(state.server_max_entries)
    if skipped_secrets:
        summary = ", ".join(f'"{s.path}" ({s.label})' for s in skipped_secrets)
        log_for_debugging(
            f"team-memory-sync: {len(skipped_secrets)} file(s) skipped due to detected secrets: "
            f"{summary}. Remove the secret(s) to enable sync for these files.",
            level="warn",
        )
        log_event(
            "tengu_team_mem_secret_skipped",
            {
                "file_count": len(skipped_secrets),
                "rule_ids": ",".join(s.rule_id for s in skipped_secrets),
            },
        )

    # Hash each local entry once.
    local_hashes: dict[str, str] = {
        key: hash_content(content) for key, content in entries.items()
    }

    saw_conflict = False

    for conflict_attempt in range(MAX_CONFLICT_RETRIES + 1):
        # Delta: only upload keys whose content hash differs from server's
        delta: dict[str, str] = {
            key: entries[key]
            for key, local_hash in local_hashes.items()
            if state.server_checksums.get(key) != local_hash
        }
        delta_count = len(delta)

        if delta_count == 0:
            _log_push(
                start_time,
                {
                    "success": True,
                    "conflict": saw_conflict,
                    "conflict_retries": conflict_retries,
                },
            )
            return TeamMemorySyncPushResult(
                success=True,
                files_uploaded=0,
                skipped_secrets=skipped_secrets if skipped_secrets else None,
            )

        # Split the delta into PUT-sized batches to stay under the gateway limit.
        batches = batch_delta_by_bytes(delta)
        files_uploaded = 0
        result: Optional[TeamMemorySyncUploadResult] = None

        for batch in batches:
            result = await _upload_team_memory(
                state, repo_slug, batch, state.last_known_checksum
            )
            if not result.success:
                break
            for key in batch:
                state.server_checksums[key] = local_hashes[key]
            files_uploaded += len(batch)

        # batches is non-empty (delta_count > 0), so result is always set
        assert result is not None

        if result.success:
            if len(batches) > 1:
                log_for_debugging(
                    f"team-memory-sync: pushed {files_uploaded} of "
                    f"{len(local_hashes)} files in {len(batches)} batches",
                    level="info",
                )
            else:
                log_for_debugging(
                    f"team-memory-sync: pushed {files_uploaded} of "
                    f"{len(local_hashes)} files (delta)",
                    level="info",
                )
            _log_push(
                start_time,
                {
                    "success": True,
                    "files_uploaded": files_uploaded,
                    "conflict": saw_conflict,
                    "conflict_retries": conflict_retries,
                    "put_batches": len(batches) if len(batches) > 1 else None,
                },
            )
            return TeamMemorySyncPushResult(
                success=True,
                files_uploaded=files_uploaded,
                checksum=result.checksum,
                skipped_secrets=skipped_secrets if skipped_secrets else None,
            )

        if not result.conflict:
            # Cache the server's max_entries from a structured 413
            if result.server_max_entries is not None:
                state.server_max_entries = result.server_max_entries
                log_for_debugging(
                    f"team-memory-sync: learned server max_entries="
                    f"{result.server_max_entries} from 413; next push will truncate to this",
                    level="warn",
                )
            _log_push(
                start_time,
                {
                    "success": False,
                    "files_uploaded": files_uploaded,
                    "conflict_retries": conflict_retries,
                    "put_batches": len(batches) if len(batches) > 1 else None,
                    "error_type": result.error_type,
                    "status": result.http_status,
                    "error_code": result.server_error_code,
                    "server_max_entries": result.server_max_entries,
                    "server_received_entries": result.server_received_entries,
                },
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
                start_time,
                {
                    "success": False,
                    "conflict": True,
                    "conflict_retries": conflict_retries,
                    "error_type": "conflict",
                },
            )
            return TeamMemorySyncPushResult(
                success=False,
                files_uploaded=0,
                conflict=True,
                error="Conflict resolution failed after retries",
            )

        conflict_retries += 1

        log_for_debugging(
            f"team-memory-sync: conflict (412), probing server hashes "
            f"(attempt {conflict_attempt + 1}/{MAX_CONFLICT_RETRIES})",
            level="info",
        )

        # Cheap probe: fetch only per-key checksums, no entry bodies.
        probe = await _fetch_team_memory_hashes(state, repo_slug)
        if not probe.success or not probe.entry_checksums:
            _log_push(
                start_time,
                {
                    "success": False,
                    "conflict": True,
                    "conflict_retries": conflict_retries,
                    "error_type": "conflict",
                },
            )
            return TeamMemorySyncPushResult(
                success=False,
                files_uploaded=0,
                conflict=True,
                error=f"Conflict resolution hashes probe failed: {probe.error}",
            )
        state.server_checksums.clear()
        state.server_checksums.update(probe.entry_checksums)

    _log_push(start_time, {"success": False, "conflict_retries": conflict_retries})
    return TeamMemorySyncPushResult(
        success=False,
        files_uploaded=0,
        error="Unexpected end of conflict resolution loop",
    )


async def sync_team_memory(state: SyncState) -> dict[str, Any]:
    """
    Bidirectional sync: pull from server, merge with local, push back.
    Server entries take precedence on conflict (last-write-wins by the server).
    Push uses conflict resolution (retries on 412) via push_team_memory.

    Returns dict with: success, files_pulled, files_pushed, error.
    """
    # 1. Pull remote → local (skip ETag cache for full sync)
    pull_result = await pull_team_memory(state, skip_etag_cache=True)
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
        f"team-memory-sync: synced "
        f"(pulled {pull_result['files_written']}, pushed {push_result.files_uploaded})",
        level="info",
    )
    return {
        "success": True,
        "files_pulled": pull_result["files_written"],
        "files_pushed": push_result.files_uploaded,
    }


# ─── Telemetry helpers ───────────────────────────────────────


def _now_ms() -> int:
    import time
    return int(time.time() * 1000)


def _log_pull(start_time: int, outcome: dict[str, Any]) -> None:
    log_event(
        "tengu_team_mem_sync_pull",
        {
            "success": outcome.get("success", False),
            "files_written": outcome.get("files_written", 0),
            "not_modified": outcome.get("not_modified", False),
            "duration_ms": _now_ms() - start_time,
            **(
                {"errorType": outcome["error_type"]}
                if outcome.get("error_type")
                else {}
            ),
            **({"status": outcome["status"]} if outcome.get("status") else {}),
        },
    )


def _log_push(start_time: int, outcome: dict[str, Any]) -> None:
    payload: dict[str, Any] = {
        "success": outcome.get("success", False),
        "files_uploaded": outcome.get("files_uploaded", 0),
        "conflict": outcome.get("conflict", False),
        "conflict_retries": outcome.get("conflict_retries", 0),
        "duration_ms": _now_ms() - start_time,
    }
    if outcome.get("error_type"):
        payload["errorType"] = outcome["error_type"]
    if outcome.get("status"):
        payload["status"] = outcome["status"]
    if outcome.get("put_batches"):
        payload["put_batches"] = outcome["put_batches"]
    if outcome.get("error_code"):
        payload["error_code"] = outcome["error_code"]
    if outcome.get("server_max_entries") is not None:
        payload["server_max_entries"] = outcome["server_max_entries"]
    if outcome.get("server_received_entries") is not None:
        payload["server_received_entries"] = outcome["server_received_entries"]
    log_event("tengu_team_mem_sync_push", payload)


def _http_status_to_error_type(status: int) -> str:
    if status in (401, 403):
        return "auth"
    return "unknown"
