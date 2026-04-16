"""
team_memory_sync/index.py — Team Memory Sync Service.
Ported from services/teamMemorySync/index.ts (1256 lines).

Syncs team memory files between local filesystem and server API.
Team memory is scoped per-repo (identified by git remote hash) and
shared across all authenticated org members.

API contract:
  GET  /api/claude_code/team_memory?repo={owner/repo}            → TeamMemoryData
  GET  /api/claude_code/team_memory?repo={owner/repo}&view=hashes → metadata + checksums only
  PUT  /api/claude_code/team_memory?repo={owner/repo}            → upload entries (upsert)
  404  = no data exists yet
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEAM_MEMORY_SYNC_TIMEOUT_S = 30
MAX_FILE_SIZE_BYTES = 250_000
MAX_PUT_BODY_BYTES = 200_000
MAX_RETRIES = 3
MAX_CONFLICT_RETRIES = 2


# ---------------------------------------------------------------------------
# SyncState
# ---------------------------------------------------------------------------

class SyncState:
    """
    Mutable state for the team memory sync service.
    Created once per session and threaded through all sync functions.
    """
    def __init__(self) -> None:
        self.last_known_checksum: Optional[str] = None
        self.server_checksums: Dict[str, str] = {}
        self.server_max_entries: Optional[int] = None


def create_sync_state() -> SyncState:
    """Create fresh SyncState (mirrors createSyncState())."""
    return SyncState()


# ---------------------------------------------------------------------------
# Hash helpers
# ---------------------------------------------------------------------------

def hash_content(content: str) -> str:
    """
    Compute sha256:<hex> over the UTF-8 bytes of content.
    Matches server's entryChecksums format.
    """
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


# ---------------------------------------------------------------------------
# Batch helpers
# ---------------------------------------------------------------------------

def batch_delta_by_bytes(
    delta: Dict[str, str],
) -> List[Dict[str, str]]:
    """
    Split a delta dict into batches, each <= MAX_PUT_BODY_BYTES.
    Mirrors batchDeltaByBytes() in index.ts.
    """
    keys = sorted(delta.keys())
    if not keys:
        return []

    EMPTY_BODY_BYTES = len('{"entries":{}}'.encode("utf-8"))

    def entry_bytes(k: str, v: str) -> int:
        return (
            len(json.dumps(k).encode("utf-8"))
            + len(json.dumps(v).encode("utf-8"))
            + 2  # colon + comma
        )

    batches: List[Dict[str, str]] = []
    current: Dict[str, str] = {}
    current_bytes = EMPTY_BODY_BYTES

    for key in keys:
        added = entry_bytes(key, delta[key])
        if current_bytes + added > MAX_PUT_BODY_BYTES and current:
            batches.append(current)
            current = {}
            current_bytes = EMPTY_BODY_BYTES
        current[key] = delta[key]
        current_bytes += added

    if current:
        batches.append(current)
    return batches


# ---------------------------------------------------------------------------
# Auth / endpoint helpers
# ---------------------------------------------------------------------------

def _is_using_oauth() -> bool:
    """Check if user is authenticated with first-party OAuth."""
    try:
        from claude_code.utils.auth import get_claude_ai_oauth_tokens
        from claude_code.utils.model.providers import get_api_provider, is_first_party_anthropic_base_url
        if get_api_provider() != "firstParty" or not is_first_party_anthropic_base_url():
            return False
        tokens = get_claude_ai_oauth_tokens()
        if not tokens:
            return False
        access_token = tokens.get("accessToken") if isinstance(tokens, dict) else getattr(tokens, "access_token", None)
        return bool(access_token)
    except Exception:
        return False


def is_team_memory_sync_available() -> bool:
    """Check if team memory sync is available (requires OAuth)."""
    return _is_using_oauth()


def _get_team_memory_sync_endpoint(repo_slug: str) -> str:
    base_url = os.environ.get(
        "TEAM_MEMORY_SYNC_URL",
        "https://api.claude.ai",
    )
    return f"{base_url}/api/claude_code/team_memory?repo={repo_slug}"


def _get_auth_headers() -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """Returns (headers, error)."""
    try:
        from claude_code.utils.auth import get_claude_ai_oauth_tokens
        from claude_code.utils.user_agent import get_claude_code_user_agent
        tokens = get_claude_ai_oauth_tokens()
        access_token = None
        if tokens:
            access_token = tokens.get("accessToken") if isinstance(tokens, dict) else getattr(tokens, "access_token", None)
        if access_token:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "User-Agent": get_claude_code_user_agent(),
            }
            return headers, None
    except Exception:
        pass
    return None, "No OAuth token available for team memory sync"


# ---------------------------------------------------------------------------
# Local filesystem helpers
# ---------------------------------------------------------------------------

def _get_team_mem_dir() -> Optional[str]:
    """Return the local team memory directory path."""
    try:
        from claude_code.utils.config import get_config_dir
        return os.path.join(get_config_dir(), "team_memory")
    except Exception:
        home = os.path.expanduser("~")
        return os.path.join(home, ".claude", "team_memory")


def _validate_team_mem_key(key: str) -> bool:
    """Validate a team memory key (prevent path traversal)."""
    if not key or ".." in key or key.startswith("/") or "\x00" in key:
        return False
    # Only allow safe characters
    import re
    return bool(re.match(r"^[a-zA-Z0-9._\-/]+$", key))


async def _read_local_team_memory(
    max_entries: Optional[int] = None,
) -> Dict[str, str]:
    """Read all local team memory files. Returns {key: content}."""
    team_mem_dir = _get_team_mem_dir()
    if not team_mem_dir or not os.path.isdir(team_mem_dir):
        return {}

    entries: Dict[str, str] = {}
    try:
        for root, dirs, files in os.walk(team_mem_dir):
            for fname in sorted(files):
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, team_mem_dir)
                key = rel.replace(os.sep, "/")
                if not _validate_team_mem_key(key):
                    continue
                try:
                    size = os.path.getsize(fpath)
                    if size > MAX_FILE_SIZE_BYTES:
                        logger.debug("team-memory-sync: skipping oversized file %s (%d bytes)", key, size)
                        continue
                    with open(fpath, "r", encoding="utf-8") as f:
                        entries[key] = f.read()
                    if max_entries and len(entries) >= max_entries:
                        break
                except Exception as e:
                    logger.debug("team-memory-sync: error reading %s: %s", key, e)
    except Exception as e:
        logger.debug("team-memory-sync: error reading local memory: %s", e)
    return entries


async def _write_remote_entries_to_local(entries: Dict[str, str]) -> int:
    """Write server entries to local disk. Returns count of files written."""
    team_mem_dir = _get_team_mem_dir()
    if not team_mem_dir:
        return 0

    os.makedirs(team_mem_dir, exist_ok=True)
    files_written = 0

    for key, content in entries.items():
        if not _validate_team_mem_key(key):
            logger.warning("team-memory-sync: skipping invalid key %s", key)
            continue
        fpath = os.path.join(team_mem_dir, key.replace("/", os.sep))
        try:
            os.makedirs(os.path.dirname(fpath), exist_ok=True)
            # Only write if content differs
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    existing = f.read()
                if existing == content:
                    continue
            except FileNotFoundError:
                pass
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)
            files_written += 1
        except Exception as e:
            logger.debug("team-memory-sync: error writing %s: %s", key, e)

    return files_written


# ---------------------------------------------------------------------------
# HTTP fetch helpers (sync with urllib, async-wrapped)
# ---------------------------------------------------------------------------

def _http_get(url: str, headers: Dict[str, str], timeout: int = 30) -> Tuple[int, Any]:
    """Synchronous HTTP GET. Returns (status_code, parsed_body_or_None)."""
    import urllib.request
    import urllib.error
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(body)
            except Exception:
                return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, body
    except Exception as e:
        raise


def _http_put(url: str, headers: Dict[str, str], body: Dict[str, Any], timeout: int = 30) -> Tuple[int, Any]:
    """Synchronous HTTP PUT. Returns (status_code, parsed_body_or_None)."""
    import urllib.request
    import urllib.error
    data = json.dumps(body).encode("utf-8")
    put_headers = {**headers, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=put_headers, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_body = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(resp_body)
            except Exception:
                return resp.status, resp_body
    except urllib.error.HTTPError as e:
        body_bytes = e.read().decode("utf-8") if e.fp else ""
        try:
            return e.code, json.loads(body_bytes)
        except Exception:
            return e.code, body_bytes
    except Exception as e:
        raise


async def _fetch_team_memory_once(
    state: SyncState,
    repo_slug: str,
    etag: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch team memory from server. Returns result dict."""
    endpoint = _get_team_memory_sync_endpoint(repo_slug)
    headers, err = _get_auth_headers()
    if err or not headers:
        return {"success": False, "error": err or "No auth headers", "error_type": "auth"}

    if etag:
        headers["If-None-Match"] = f'"{etag.strip(chr(34))}"'

    try:
        loop = asyncio.get_event_loop()
        status, body = await loop.run_in_executor(
            None, lambda: _http_get(endpoint, headers, TEAM_MEMORY_SYNC_TIMEOUT_S)
        )

        if status == 304:
            return {"success": True, "not_modified": True}
        if status == 404:
            return {"success": True, "is_empty": True}
        if status != 200:
            return {"success": False, "error": f"HTTP {status}", "http_status": status, "error_type": "http"}

        # Update ETag
        if isinstance(body, dict):
            checksum = body.get("checksum")
            if checksum:
                state.last_known_checksum = checksum

        return {"success": True, "data": body}

    except Exception as e:
        logger.debug("team-memory-sync: fetch failed: %s", e)
        return {"success": False, "error": str(e), "error_type": "network"}


async def _fetch_team_memory(
    state: SyncState,
    repo_slug: str,
    etag: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch with retry (up to MAX_RETRIES)."""
    last_result: Dict[str, Any] = {"success": False, "error": "max retries exceeded"}
    for attempt in range(MAX_RETRIES):
        result = await _fetch_team_memory_once(state, repo_slug, etag)
        if result.get("success") or result.get("error_type") in ("auth", "no_repo"):
            return result
        last_result = result
        if attempt < MAX_RETRIES - 1:
            delay = min(1.0 * (2 ** attempt), 30.0)
            await asyncio.sleep(delay)
    return last_result


async def _upload_team_memory(
    state: SyncState,
    repo_slug: str,
    entries: Dict[str, str],
    if_match_checksum: Optional[str] = None,
) -> Dict[str, Any]:
    """Upload entries to server. Returns result dict."""
    endpoint = _get_team_memory_sync_endpoint(repo_slug)
    headers, err = _get_auth_headers()
    if err or not headers:
        return {"success": False, "error": err or "No auth headers", "error_type": "auth"}

    if if_match_checksum:
        headers["If-Match"] = f'"{if_match_checksum.strip(chr(34))}"'

    try:
        loop = asyncio.get_event_loop()
        status, body = await loop.run_in_executor(
            None, lambda: _http_put(endpoint, headers, {"entries": entries}, TEAM_MEMORY_SYNC_TIMEOUT_S)
        )

        if status == 412:
            return {"success": False, "conflict": True, "error": "ETag mismatch"}

        if status == 413:
            max_entries = None
            if isinstance(body, dict):
                try:
                    max_entries = body["error"]["details"]["max_entries"]
                except (KeyError, TypeError):
                    pass
            return {
                "success": False,
                "error": f"HTTP 413",
                "error_type": "http",
                "http_status": 413,
                "server_error_code": "team_memory_too_many_entries",
                **({"server_max_entries": max_entries} if max_entries else {}),
            }

        if status != 200:
            return {"success": False, "error": f"HTTP {status}", "http_status": status, "error_type": "http"}

        # Update checksum from response
        if isinstance(body, dict):
            checksum = body.get("checksum")
            if checksum:
                state.last_known_checksum = checksum

        logger.debug("team-memory-sync: uploaded %d entries", len(entries))
        return {"success": True, "checksum": body.get("checksum") if isinstance(body, dict) else None}

    except Exception as e:
        logger.debug("team-memory-sync: upload failed: %s", e)
        return {"success": False, "error": str(e), "error_type": "network"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def pull_team_memory(
    state: SyncState,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Pull team memory from the server and write to local directory.
    Returns {success, files_written, entry_count, not_modified?, error?}.
    Mirrors pullTeamMemory() in index.ts.
    """
    skip_etag_cache = (options or {}).get("skip_etag_cache", False)
    start_time = time.time()

    if not _is_using_oauth():
        return {"success": False, "files_written": 0, "entry_count": 0, "error": "OAuth not available"}

    # Get repo slug from git remote
    repo_slug = None
    try:
        from claude_code.utils.git import get_github_repo
        repo_slug = await asyncio.get_event_loop().run_in_executor(None, get_github_repo)
    except Exception:
        pass

    if not repo_slug:
        return {"success": False, "files_written": 0, "entry_count": 0, "error": "No git remote found"}

    etag = None if skip_etag_cache else state.last_known_checksum
    result = await _fetch_team_memory(state, repo_slug, etag)

    if not result.get("success"):
        return {"success": False, "files_written": 0, "entry_count": 0, "error": result.get("error")}

    if result.get("not_modified"):
        return {"success": True, "files_written": 0, "entry_count": 0, "not_modified": True}

    if result.get("is_empty") or not result.get("data"):
        state.server_checksums.clear()
        return {"success": True, "files_written": 0, "entry_count": 0}

    data = result["data"]
    content = data.get("content", data)  # handle flat or nested response
    entries: Dict[str, str] = content.get("entries", {}) if isinstance(content, dict) else {}
    entry_checksums: Dict[str, str] = content.get("entryChecksums", {}) if isinstance(content, dict) else {}

    # Refresh server checksums
    state.server_checksums.clear()
    for key, chk in entry_checksums.items():
        state.server_checksums[key] = chk

    files_written = await _write_remote_entries_to_local(entries)
    logger.info("team-memory-sync: pulled %d files", files_written)

    return {
        "success": True,
        "files_written": files_written,
        "entry_count": len(entries),
    }


async def push_team_memory(
    state: SyncState,
) -> Dict[str, Any]:
    """
    Push local team memory files to the server with delta upload.
    Uses optimistic locking (ETag); retries on 412 conflict.
    Mirrors pushTeamMemory() in index.ts.
    """
    start_time = time.time()
    conflict_retries = 0

    if not _is_using_oauth():
        return {"success": False, "files_uploaded": 0, "error": "OAuth not available"}

    repo_slug = None
    try:
        from claude_code.utils.git import get_github_repo
        repo_slug = await asyncio.get_event_loop().run_in_executor(None, get_github_repo)
    except Exception:
        pass

    if not repo_slug:
        return {"success": False, "files_uploaded": 0, "error": "No git remote found"}

    while True:
        # Read local files
        local_entries = await _read_local_team_memory(state.server_max_entries)

        # Compute delta (only keys that differ from server checksums)
        delta: Dict[str, str] = {}
        for key, content in local_entries.items():
            local_hash = hash_content(content)
            server_hash = state.server_checksums.get(key)
            if local_hash != server_hash:
                delta[key] = content

        if not delta:
            logger.debug("team-memory-sync: no delta to push")
            return {"success": True, "files_uploaded": 0}

        # Split into batches
        batches = batch_delta_by_bytes(delta)
        total_uploaded = 0
        put_batches = 0

        for batch in batches:
            for attempt in range(MAX_RETRIES):
                upload_result = await _upload_team_memory(
                    state, repo_slug, batch, state.last_known_checksum
                )

                if upload_result.get("success"):
                    total_uploaded += len(batch)
                    put_batches += 1
                    # Update server checksums for successfully uploaded keys
                    for key, content in batch.items():
                        state.server_checksums[key] = hash_content(content)
                    break

                if upload_result.get("conflict"):
                    # 412: refresh server checksums and retry outer loop
                    conflict_retries += 1
                    if conflict_retries >= MAX_CONFLICT_RETRIES:
                        return {
                            "success": False,
                            "files_uploaded": total_uploaded,
                            "error": "Too many conflicts",
                            "error_type": "conflict",
                        }
                    # Probe GET ?view=hashes to refresh checksums
                    probe_url = _get_team_memory_sync_endpoint(repo_slug) + "&view=hashes"
                    headers, _ = _get_auth_headers()
                    if headers:
                        try:
                            loop = asyncio.get_event_loop()
                            status, body = await loop.run_in_executor(
                                None, lambda: _http_get(probe_url, headers, TEAM_MEMORY_SYNC_TIMEOUT_S)
                            )
                            if status == 200 and isinstance(body, dict):
                                content_data = body.get("content", body)
                                new_checksums = content_data.get("entryChecksums", {}) if isinstance(content_data, dict) else {}
                                state.server_checksums.clear()
                                state.server_checksums.update(new_checksums)
                                if body.get("checksum"):
                                    state.last_known_checksum = body["checksum"]
                        except Exception as e:
                            logger.debug("team-memory-sync: probe failed: %s", e)
                    break  # break inner retry, outer loop continues

                if upload_result.get("http_status") == 413:
                    max_ent = upload_result.get("server_max_entries")
                    if max_ent:
                        state.server_max_entries = max_ent
                    return {
                        "success": False,
                        "files_uploaded": total_uploaded,
                        "error": "Too many entries",
                        "error_type": "too_many_entries",
                    }

                # Other error: retry with backoff
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(min(1.0 * (2 ** attempt), 30.0))
                else:
                    return {
                        "success": False,
                        "files_uploaded": total_uploaded,
                        "error": upload_result.get("error", "Upload failed"),
                        "error_type": upload_result.get("error_type", "unknown"),
                    }
        else:
            # All batches succeeded
            logger.info("team-memory-sync: pushed %d files in %d batches", total_uploaded, put_batches)
            return {"success": True, "files_uploaded": total_uploaded, "put_batches": put_batches}

        # If we broke out due to conflict, loop again
        if conflict_retries > 0 and conflict_retries < MAX_CONFLICT_RETRIES:
            continue
        break

    return {"success": False, "files_uploaded": 0, "error": "Push failed after retries"}


async def sync_team_memory(state: SyncState) -> Dict[str, Any]:
    """
    Full sync: pull remote → local, then push local → remote.
    Mirrors syncTeamMemory() in index.ts.
    """
    # 1. Pull (skip ETag cache for full sync)
    pull_result = await pull_team_memory(state, {"skip_etag_cache": True})
    if not pull_result.get("success"):
        return {
            "success": False,
            "files_pulled": 0,
            "files_pushed": 0,
            "error": pull_result.get("error"),
        }

    # 2. Push
    push_result = await push_team_memory(state)
    if not push_result.get("success"):
        return {
            "success": False,
            "files_pulled": pull_result.get("files_written", 0),
            "files_pushed": 0,
            "error": push_result.get("error"),
        }

    logger.info(
        "team-memory-sync: synced (pulled %d, pushed %d)",
        pull_result.get("files_written", 0),
        push_result.get("files_uploaded", 0),
    )
    return {
        "success": True,
        "files_pulled": pull_result.get("files_written", 0),
        "files_pushed": push_result.get("files_uploaded", 0),
    }
