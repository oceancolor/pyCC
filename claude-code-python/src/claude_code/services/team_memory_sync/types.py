"""
team_memory_sync/types.py — Team Memory Sync Types.
Ported from services/teamMemorySync/types.ts (156 lines).

Zod schemas and types for the repo-scoped team memory sync API.
"""
from __future__ import annotations

from typing import Dict, Literal, Optional, Union
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# TeamMemoryContent
# ---------------------------------------------------------------------------

@dataclass
class TeamMemoryContent:
    """
    Content portion of team memory data — flat key-value storage.
    Keys are file paths relative to the team memory directory.
    Values are UTF-8 string content (typically Markdown).
    entryChecksums: per-key SHA-256 (`sha256:<hex>`). Optional for forward-compat.
    """
    entries: Dict[str, str] = field(default_factory=dict)
    entry_checksums: Optional[Dict[str, str]] = None

    @classmethod
    def from_dict(cls, d: dict) -> "TeamMemoryContent":
        return cls(
            entries=d.get("entries", {}),
            entry_checksums=d.get("entryChecksums"),
        )

    def to_dict(self) -> dict:
        result: dict = {"entries": self.entries}
        if self.entry_checksums is not None:
            result["entryChecksums"] = self.entry_checksums
        return result


# ---------------------------------------------------------------------------
# TeamMemoryData
# ---------------------------------------------------------------------------

@dataclass
class TeamMemoryData:
    """Full response from GET /api/claude_code/team_memory."""
    organization_id: str
    repo: str
    version: int
    last_modified: str   # ISO 8601 timestamp
    checksum: str        # SHA256 with 'sha256:' prefix
    content: TeamMemoryContent

    @classmethod
    def from_dict(cls, d: dict) -> "TeamMemoryData":
        return cls(
            organization_id=d.get("organizationId", ""),
            repo=d.get("repo", ""),
            version=d.get("version", 0),
            last_modified=d.get("lastModified", ""),
            checksum=d.get("checksum", ""),
            content=TeamMemoryContent.from_dict(d.get("content", {})),
        )

    def to_dict(self) -> dict:
        return {
            "organizationId": self.organization_id,
            "repo": self.repo,
            "version": self.version,
            "lastModified": self.last_modified,
            "checksum": self.checksum,
            "content": self.content.to_dict(),
        }


# ---------------------------------------------------------------------------
# TeamMemoryTooManyEntries error body
# ---------------------------------------------------------------------------

@dataclass
class TooManyEntriesDetails:
    error_code: Literal["team_memory_too_many_entries"]
    max_entries: int
    received_entries: int


@dataclass
class TooManyEntriesError:
    details: TooManyEntriesDetails

    @classmethod
    def from_dict(cls, d: dict) -> Optional["TooManyEntriesError"]:
        """Parse a 413 error body. Returns None if not a too-many-entries error."""
        try:
            error = d.get("error", {})
            details = error.get("details", {})
            if details.get("error_code") != "team_memory_too_many_entries":
                return None
            return cls(
                details=TooManyEntriesDetails(
                    error_code="team_memory_too_many_entries",
                    max_entries=int(details["max_entries"]),
                    received_entries=int(details["received_entries"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            return None


# ---------------------------------------------------------------------------
# SkippedSecretFile
# ---------------------------------------------------------------------------

@dataclass
class SkippedSecretFile:
    """
    A file skipped during push because it contains a detected secret.
    Only the matched gitleaks rule ID is recorded — never the secret value.
    """
    path: str
    rule_id: str   # Gitleaks rule ID (e.g., "github-pat", "aws-access-token")
    label: str     # Human-readable label derived from rule ID


# ---------------------------------------------------------------------------
# TeamMemorySyncFetchResult
# ---------------------------------------------------------------------------

@dataclass
class TeamMemorySyncFetchResult:
    """Result from fetching team memory."""
    success: bool
    data: Optional[TeamMemoryData] = None
    is_empty: Optional[bool] = None      # true if 404 (no data exists)
    not_modified: Optional[bool] = None  # true if 304 (ETag matched)
    checksum: Optional[str] = None       # ETag from response header
    error: Optional[str] = None
    skip_retry: Optional[bool] = None
    error_type: Optional[str] = None     # 'auth'|'timeout'|'network'|'parse'|'unknown'
    http_status: Optional[int] = None


# ---------------------------------------------------------------------------
# TeamMemoryHashesResult
# ---------------------------------------------------------------------------

@dataclass
class TeamMemoryHashesResult:
    """
    Lightweight metadata-only probe result (GET ?view=hashes).
    Contains per-key checksums without entry bodies.
    """
    success: bool
    version: Optional[int] = None
    checksum: Optional[str] = None
    entry_checksums: Optional[Dict[str, str]] = None
    error: Optional[str] = None
    error_type: Optional[str] = None  # 'auth'|'timeout'|'network'|'parse'|'unknown'
    http_status: Optional[int] = None


# ---------------------------------------------------------------------------
# TeamMemorySyncPushResult
# ---------------------------------------------------------------------------

@dataclass
class TeamMemorySyncPushResult:
    """Result from uploading team memory with conflict info."""
    success: bool
    files_uploaded: int
    checksum: Optional[str] = None
    conflict: Optional[bool] = None           # true if 412 Precondition Failed
    error: Optional[str] = None
    skipped_secrets: Optional[list] = None    # List[SkippedSecretFile]
    error_type: Optional[str] = None
    # 'auth'|'timeout'|'network'|'conflict'|'unknown'|'no_oauth'|'no_repo'
    http_status: Optional[int] = None


# ---------------------------------------------------------------------------
# TeamMemorySyncUploadResult
# ---------------------------------------------------------------------------

@dataclass
class TeamMemorySyncUploadResult:
    """Result from uploading team memory."""
    success: bool
    checksum: Optional[str] = None
    last_modified: Optional[str] = None
    conflict: Optional[bool] = None           # true if 412 Precondition Failed
    error: Optional[str] = None
    error_type: Optional[str] = None          # 'auth'|'timeout'|'network'|'unknown'
    http_status: Optional[int] = None
    server_error_code: Optional[str] = None   # 'team_memory_too_many_entries'
    server_max_entries: Optional[int] = None
    server_received_entries: Optional[int] = None
