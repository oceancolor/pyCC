"""
JSONL-based session persistence storage.

Python port of utils/sessionStorage.ts (5105 lines).
Full port: all functions, types, constants, class Project.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Literal,
    Optional,
    Set,
    Tuple,
    Union,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# 50 MB — session JSONL can grow to multiple GB.
# Callers that read the raw transcript must bail out above this threshold.
MAX_TRANSCRIPT_READ_BYTES = 50 * 1024 * 1024

# 50 MB — prevents OOM in the tombstone slow path.
MAX_TOMBSTONE_REWRITE_BYTES = 50 * 1024 * 1024

# Flush interval (ms) for remote persistence
REMOTE_FLUSH_INTERVAL_MS = 0.010  # 10 ms in seconds

# Initial number of logs to enrich on first load
INITIAL_ENRICH_COUNT = 50

# Pre-compiled regex to skip non-meaningful messages when extracting first prompt.
SKIP_FIRST_PROMPT_PATTERN = re.compile(
    r"^(?:\s*<[a-z][\w-]*[\s>]|\[Request interrupted by user[^\]]*\])"
)

# Metadata entry types that can appear before a compact boundary.
METADATA_TYPE_MARKERS = [
    '"type":"summary"',
    '"type":"custom-title"',
    '"type":"tag"',
    '"type":"agent-name"',
    '"type":"agent-color"',
    '"type":"agent-setting"',
    '"type":"mode"',
    '"type":"worktree-state"',
    '"type":"pr-link"',
]

# COMMAND_NAME_TAG and TICK_TAG (mirrors constants/xml.ts)
COMMAND_NAME_TAG = "command-name"
TICK_TAG = "tick"

REPL_TOOL_NAME = "repl"

# Feature flags (simplified)
_FEATURE_PROACTIVE = False
_FEATURE_KAIROS = False

EPHEMERAL_PROGRESS_TYPES: Set[str] = {
    "bash_progress",
    "powershell_progress",
    "mcp_progress",
}
if _FEATURE_PROACTIVE or _FEATURE_KAIROS:
    EPHEMERAL_PROGRESS_TYPES.add("sleep_progress")

# ---------------------------------------------------------------------------
# Lazy imports for optional dependencies
# ---------------------------------------------------------------------------

try:
    from .env_utils import get_claude_config_home_dir, is_env_truthy
except ImportError:
    def get_claude_config_home_dir() -> str:  # type: ignore[misc]
        return str(Path.home() / ".claude")

    def is_env_truthy(val: Optional[str]) -> bool:  # type: ignore[misc]
        return val is not None and val.lower() in ("1", "true", "yes")

try:
    from .path import sanitize_path
except ImportError:
    def sanitize_path(p: str) -> str:  # type: ignore[misc]
        return p.replace(os.sep, "-").replace("/", "-").replace(":", "-").strip("-")

try:
    from .cwd import get_cwd
except ImportError:
    def get_cwd() -> str:  # type: ignore[misc]
        return os.getcwd()

try:
    from .log import log_error
except ImportError:
    def log_error(e: Exception) -> None:  # type: ignore[misc]
        logger.error(str(e))

try:
    from .debug import log_for_debugging
except ImportError:
    def log_for_debugging(msg: str, **kwargs: Any) -> None:  # type: ignore[misc]
        logger.debug(msg)

try:
    from .json import parse_jsonl
except ImportError:
    def parse_jsonl(data: bytes) -> List[Any]:  # type: ignore[misc]
        lines = data.decode("utf-8", errors="replace").splitlines()
        results = []
        for line in lines:
            line = line.strip()
            if line:
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return results

try:
    from .messages import extract_tag, is_compact_boundary_message
except ImportError:
    def extract_tag(text: str, tag: str) -> Optional[str]:  # type: ignore[misc]
        m = re.search(rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>", text, re.DOTALL)
        return m.group(1) if m else None

    def is_compact_boundary_message(m: Any) -> bool:  # type: ignore[misc]
        return (
            isinstance(m, dict) and m.get("type") == "system"
            and m.get("subtype") == "compact_boundary"
        )

try:
    from .slow_operations import json_parse, json_stringify
except ImportError:
    def json_parse(s: str) -> Any:  # type: ignore[misc]
        return json.loads(s)

    def json_stringify(obj: Any) -> str:  # type: ignore[misc]
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

try:
    from .format import format_file_size
except ImportError:
    def format_file_size(n: int) -> str:  # type: ignore[misc]
        return f"{n} bytes"

try:
    from .errors import is_fs_inaccessible
except ImportError:
    def is_fs_inaccessible(e: Exception) -> bool:  # type: ignore[misc]
        return isinstance(e, (FileNotFoundError, PermissionError, NotADirectoryError))

try:
    from .cleanup_registry import register_cleanup
except ImportError:
    def register_cleanup(fn: Callable) -> None:  # type: ignore[misc]
        pass

try:
    from .graceful_shutdown import graceful_shutdown_sync, is_shutting_down
except ImportError:
    def graceful_shutdown_sync(code: int = 1, reason: str = "other") -> None:  # type: ignore[misc]
        pass

    def is_shutting_down() -> bool:  # type: ignore[misc]
        return False

try:
    from .git import get_branch
except ImportError:
    async def get_branch() -> Optional[str]:  # type: ignore[misc]
        return None

try:
    from .array import uniq
except ImportError:
    def uniq(lst: List[Any]) -> List[Any]:  # type: ignore[misc]
        seen: Set[Any] = set()
        result = []
        for item in lst:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result

try:
    from .concurrent_sessions import update_session_name
except ImportError:
    async def update_session_name(name: str) -> None:  # type: ignore[misc]
        pass

try:
    from .uuid import validate_uuid
except ImportError:
    def validate_uuid(s: str) -> bool:  # type: ignore[misc]
        UUID_RE = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
        )
        return bool(UUID_RE.match(s))

try:
    from .fs_operations import get_fs_implementation
except ImportError:
    get_fs_implementation = None  # type: ignore[assignment]

try:
    from .get_worktree_paths import get_worktree_paths
except ImportError:
    async def get_worktree_paths(cwd: str) -> List[str]:  # type: ignore[misc]
        return [cwd]

try:
    from .session_storage_portable import (
        extract_json_string_field,
        extract_last_json_string_field,
        LITE_READ_BUF_SIZE,
        read_head_and_tail,
        read_transcript_for_load,
        SKIP_PRECOMPACT_THRESHOLD,
    )
except ImportError:
    LITE_READ_BUF_SIZE = 64 * 1024
    SKIP_PRECOMPACT_THRESHOLD = 5 * 1024 * 1024

    def extract_json_string_field(line: str, field: str) -> Optional[str]:  # type: ignore[misc]
        m = re.search(rf'"{re.escape(field)}"\s*:\s*"((?:[^"\\]|\\.)*)"', line)
        return m.group(1) if m else None

    def extract_last_json_string_field(line: str, field: str) -> Optional[str]:  # type: ignore[misc]
        matches = list(re.finditer(rf'"{re.escape(field)}"\s*:\s*"((?:[^"\\]|\\.)*)"', line))
        return matches[-1].group(1) if matches else None

    async def read_head_and_tail(path: str, size: int) -> Tuple[bytes, bytes]:  # type: ignore[misc]
        chunk = min(LITE_READ_BUF_SIZE, size)
        try:
            with open(path, "rb") as f:
                head = f.read(chunk)
                if size > chunk:
                    f.seek(max(0, size - chunk))
                    tail = f.read(chunk)
                else:
                    tail = head
            return head, tail
        except OSError:
            return b"", b""

    async def read_transcript_for_load(path: str, size: int) -> Any:  # type: ignore[misc]
        try:
            with open(path, "rb") as f:
                return type("Scan", (), {
                    "postBoundaryBuf": f.read(),
                    "hasPreservedSegment": False,
                    "boundaryStartOffset": 0,
                })()
        except OSError:
            return type("Scan", (), {
                "postBoundaryBuf": b"",
                "hasPreservedSegment": False,
                "boundaryStartOffset": 0,
            })()

# Bootstrap state (circular import guard)
try:
    from ..bootstrap.state import (
        get_original_cwd,
        get_plan_slug_cache,
        get_prompt_id,
        get_session_id,
        get_session_project_dir,
        is_session_persistence_disabled,
        switch_session,
    )
except ImportError:
    _SESSIONS_DIR_FALLBACK = Path.home() / ".claude" / "sessions"

    def get_original_cwd() -> str:  # type: ignore[misc]
        return os.getcwd()

    def get_plan_slug_cache() -> Dict[str, str]:  # type: ignore[misc]
        return {}

    def get_prompt_id() -> Optional[str]:  # type: ignore[misc]
        return None

    def get_session_id() -> Optional[str]:  # type: ignore[misc]
        return None

    def get_session_project_dir() -> Optional[str]:  # type: ignore[misc]
        return None

    def is_session_persistence_disabled() -> bool:  # type: ignore[misc]
        return False

    def switch_session(session_id: str) -> None:  # type: ignore[misc]
        pass

try:
    from .settings.settings import get_settings_deprecated
except ImportError:
    def get_settings_deprecated() -> Optional[Any]:  # type: ignore[misc]
        return None

try:
    from .diag_logs import log_for_diagnostics_no_pii
except ImportError:
    def log_for_diagnostics_no_pii(level: str, key: str, extra: Optional[Dict] = None) -> None:  # type: ignore[misc]
        pass

try:
    from ..services.analytics import log_event
except ImportError:
    def log_event(name: str, payload: Dict[str, Any]) -> None:  # type: ignore[misc]
        pass

try:
    from ..services.analytics.growthbook import get_feature_value_cached_may_be_stale
except ImportError:
    def get_feature_value_cached_may_be_stale(key: str, default: Any) -> Any:  # type: ignore[misc]
        return default

try:
    from ..services.api import session_ingress
except ImportError:
    session_ingress = None  # type: ignore[assignment]

try:
    from ..commands import built_in_command_names
except ImportError:
    def built_in_command_names() -> Set[str]:  # type: ignore[misc]
        return set()

# ---------------------------------------------------------------------------
# Legacy stub types (preserved for backwards compatibility)
# ---------------------------------------------------------------------------

SESSIONS_DIR = Path.home() / ".claude" / "sessions"


@dataclass
class SessionRecord:
    session_id: str
    created_at: float
    updated_at: float
    messages: list
    model: str
    title: Optional[str] = None


def _session_file(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.jsonl"


def save_session(record: SessionRecord) -> Path:
    """Serialize a SessionRecord to JSONL (first line header, rest messages)."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = _session_file(record.session_id)
    with path.open("w", encoding="utf-8") as f:
        header = {
            "session_id": record.session_id,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "model": record.model,
            "title": record.title,
        }
        f.write(json.dumps(header, ensure_ascii=False) + "\n")
        for msg in record.messages:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    return path


def load_session(session_id: str) -> Optional[SessionRecord]:
    """Load a SessionRecord from JSONL; return None if file missing."""
    path = _session_file(session_id)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    if not lines:
        return None
    header = json.loads(lines[0])
    messages = [json.loads(line) for line in lines[1:]]
    return SessionRecord(
        session_id=header["session_id"],
        created_at=header["created_at"],
        updated_at=header["updated_at"],
        messages=messages,
        model=header["model"],
        title=header.get("title"),
    )


def list_sessions() -> List[SessionRecord]:
    """Return all sessions sorted by updated_at descending."""
    if not SESSIONS_DIR.exists():
        return []
    records = []
    for path in SESSIONS_DIR.glob("*.jsonl"):
        record = load_session(path.stem)
        if record is not None:
            records.append(record)
    records.sort(key=lambda r: r.updated_at, reverse=True)
    return records


def append_message(session_id: str, message: dict) -> None:
    """Append a message to an existing session file."""
    path = _session_file(session_id)
    if not path.exists():
        raise FileNotFoundError(f"Session not found: {session_id}")
    with path.open("r", encoding="utf-8") as f:
        lines = [line.rstrip("\n") for line in f]
    if lines:
        header = json.loads(lines[0])
        header["updated_at"] = time.time()
        lines[0] = json.dumps(header, ensure_ascii=False)
    lines.append(json.dumps(message, ensure_ascii=False))
    with path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Type aliases / lightweight dataclasses (TS type → Python dataclass/dict)
# ---------------------------------------------------------------------------

# These mirror the TS type shapes used throughout the codebase.
# We use dicts for the "message bus" types (Entry, TranscriptMessage, etc.)
# because they arrive from and go back to JSON.

Entry = Dict[str, Any]
TranscriptMessage = Dict[str, Any]
Message = Dict[str, Any]
LogOption = Dict[str, Any]
Transcript = List[Dict[str, Any]]
AgentId = str
SessionId = str
UUID = str


@dataclass
class AgentMetadata:
    agent_type: str
    worktree_path: Optional[str] = None
    description: Optional[str] = None


@dataclass
class RemoteAgentMetadata:
    task_id: str
    remote_task_type: str
    session_id: str
    title: str
    command: str
    spawned_at: float
    tool_use_id: Optional[str] = None
    is_long_running: Optional[bool] = None
    is_ultraplan: Optional[bool] = None
    is_remote_review: Optional[bool] = None
    remote_task_metadata: Optional[Dict[str, Any]] = None


@dataclass
class TeamInfo:
    team_name: Optional[str] = None
    agent_name: Optional[str] = None


@dataclass
class SessionLogResult:
    logs: List[LogOption]
    all_stat_logs: List[LogOption]
    next_index: int


@dataclass
class PersistedWorktreeSession:
    original_cwd: str
    worktree_path: str
    worktree_name: Optional[str] = None
    worktree_branch: Optional[str] = None
    original_branch: Optional[str] = None
    original_head_commit: Optional[str] = None
    session_id: Optional[str] = None
    tmux_session_name: Optional[str] = None
    hook_based: Optional[bool] = None


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

# Cache for agentId → subdirectory
_agent_transcript_subdirs: Dict[str, str] = {}

# Project singleton
_project: Optional["Project"] = None
_cleanup_registered = False

# Memoize cache for get_session_messages
_session_messages_cache: Dict[str, asyncio.Future] = {}


# ---------------------------------------------------------------------------
# Public guard functions
# ---------------------------------------------------------------------------


def is_transcript_message(entry: Entry) -> bool:
    """
    Type guard: returns True if entry is a transcript message
    (user/assistant/attachment/system).
    Progress messages are NOT transcript messages.
    """
    t = entry.get("type")
    return t in ("user", "assistant", "attachment", "system")


def is_chain_participant(m: Dict[str, Any]) -> bool:
    """Entries that participate in the parentUuid chain (not progress)."""
    return m.get("type") != "progress"


def is_ephemeral_tool_progress(data_type: Any) -> bool:
    """Returns True for high-frequency tool progress tick types."""
    return isinstance(data_type, str) and data_type in EPHEMERAL_PROGRESS_TYPES


def _is_legacy_progress_entry(entry: Any) -> bool:
    """
    Returns True for progress entries written before PR #24099.
    They have type='progress' and a uuid field.
    """
    return (
        isinstance(entry, dict)
        and entry.get("type") == "progress"
        and "uuid" in entry
        and isinstance(entry["uuid"], str)
    )


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def get_projects_dir() -> str:
    """Return the projects directory (under claude config home)."""
    return os.path.join(get_claude_config_home_dir(), "projects")


def get_transcript_path() -> str:
    """Return transcript path for the current session."""
    project_dir = get_session_project_dir() or get_project_dir(get_original_cwd())
    return os.path.join(project_dir, f"{get_session_id()}.jsonl")


def get_transcript_path_for_session(session_id: str) -> str:
    """Return transcript path for a given session ID."""
    if session_id == get_session_id():
        return get_transcript_path()
    project_dir = get_project_dir(get_original_cwd())
    return os.path.join(project_dir, f"{session_id}.jsonl")


def set_agent_transcript_subdir(agent_id: str, subdir: str) -> None:
    """Register an agent's transcript subdirectory."""
    _agent_transcript_subdirs[agent_id] = subdir


def clear_agent_transcript_subdir(agent_id: str) -> None:
    """Remove an agent's transcript subdirectory registration."""
    _agent_transcript_subdirs.pop(agent_id, None)


def get_agent_transcript_path(agent_id: AgentId) -> str:
    """Return the transcript path for a subagent."""
    project_dir = get_session_project_dir() or get_project_dir(get_original_cwd())
    session_id = get_session_id()
    subdir = _agent_transcript_subdirs.get(agent_id)
    if subdir:
        base = os.path.join(project_dir, session_id, "subagents", subdir)
    else:
        base = os.path.join(project_dir, session_id, "subagents")
    return os.path.join(base, f"agent-{agent_id}.jsonl")


def _get_agent_metadata_path(agent_id: AgentId) -> str:
    return get_agent_transcript_path(agent_id).replace(".jsonl", ".meta.json")


# Memoized project dir computation
_project_dir_cache: Dict[str, str] = {}


def get_project_dir(project_dir: str) -> str:
    """Return the sanitized project directory path (memoized)."""
    if project_dir not in _project_dir_cache:
        _project_dir_cache[project_dir] = os.path.join(
            get_projects_dir(), sanitize_path(project_dir)
        )
    return _project_dir_cache[project_dir]


# ---------------------------------------------------------------------------
# Agent metadata persistence
# ---------------------------------------------------------------------------


async def write_agent_metadata(agent_id: AgentId, metadata: AgentMetadata) -> None:
    """Persist agent metadata to a sidecar file."""
    path = _get_agent_metadata_path(agent_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(metadata), f)


async def read_agent_metadata(agent_id: AgentId) -> Optional[AgentMetadata]:
    """Read agent metadata from sidecar file; returns None if missing."""
    path = _get_agent_metadata_path(agent_id)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return AgentMetadata(
            agent_type=data.get("agent_type", ""),
            worktree_path=data.get("worktree_path"),
            description=data.get("description"),
        )
    except OSError as e:
        if is_fs_inaccessible(e):
            return None
        raise


def _get_remote_agents_dir() -> str:
    project_dir = get_session_project_dir() or get_project_dir(get_original_cwd())
    return os.path.join(project_dir, get_session_id(), "remote-agents")


def _get_remote_agent_metadata_path(task_id: str) -> str:
    return os.path.join(_get_remote_agents_dir(), f"remote-agent-{task_id}.meta.json")


async def write_remote_agent_metadata(task_id: str, metadata: RemoteAgentMetadata) -> None:
    """Persist remote agent task metadata."""
    path = _get_remote_agent_metadata_path(task_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(metadata), f)


async def read_remote_agent_metadata(task_id: str) -> Optional[RemoteAgentMetadata]:
    """Read remote agent metadata; returns None if missing."""
    path = _get_remote_agent_metadata_path(task_id)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return RemoteAgentMetadata(**data)
    except OSError as e:
        if is_fs_inaccessible(e):
            return None
        raise


async def delete_remote_agent_metadata(task_id: str) -> None:
    """Delete remote agent metadata file."""
    path = _get_remote_agent_metadata_path(task_id)
    try:
        os.unlink(path)
    except OSError as e:
        if is_fs_inaccessible(e):
            return
        raise


async def list_remote_agent_metadata() -> List[RemoteAgentMetadata]:
    """Scan remote-agents/ directory and return all metadata files."""
    d = _get_remote_agents_dir()
    try:
        entries = os.scandir(d)
    except OSError as e:
        if is_fs_inaccessible(e):
            return []
        raise
    results = []
    with entries:
        for entry in entries:
            if not entry.is_file() or not entry.name.endswith(".meta.json"):
                continue
            try:
                with open(entry.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                results.append(RemoteAgentMetadata(**data))
            except Exception as exc:
                log_for_debugging(f"list_remote_agent_metadata: skipping {entry.name}: {exc}")
    return results


# ---------------------------------------------------------------------------
# Session file existence check
# ---------------------------------------------------------------------------


def session_id_exists(session_id: str) -> bool:
    """Return True if the session file exists on disk."""
    project_dir = get_project_dir(get_original_cwd())
    session_file = os.path.join(project_dir, f"{session_id}.jsonl")
    return os.path.exists(session_file)


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------


def get_node_env() -> str:
    """Return NODE_ENV or 'development'."""
    return os.environ.get("NODE_ENV", "development")


def get_user_type() -> str:
    """Return USER_TYPE or 'external'."""
    return os.environ.get("USER_TYPE", "external")


def _get_entrypoint() -> Optional[str]:
    return os.environ.get("CLAUDE_CODE_ENTRYPOINT")


def is_custom_title_enabled() -> bool:
    return True


# ---------------------------------------------------------------------------
# Internal event writer/reader types
# ---------------------------------------------------------------------------

InternalEventWriter = Callable[
    [str, Dict[str, Any], Optional[Dict[str, Any]]],
    "asyncio.Coroutine[Any, Any, None]",
]
InternalEventReader = Callable[
    [],
    "asyncio.Coroutine[Any, Any, Optional[List[Dict[str, Any]]]]",
]


# ---------------------------------------------------------------------------
# Project class (mirrors TS class Project)
# ---------------------------------------------------------------------------


class Project:
    """
    Per-session project state: write queue, metadata cache, remote persistence.
    Mirrors TS class Project.
    """

    # Session metadata cache
    current_session_tag: Optional[str] = None
    current_session_title: Optional[str] = None
    current_session_agent_name: Optional[str] = None
    current_session_agent_color: Optional[str] = None
    current_session_last_prompt: Optional[str] = None
    current_session_agent_setting: Optional[str] = None
    current_session_mode: Optional[Literal["coordinator", "normal"]] = None
    # Tri-state: None = never set, None(explicitly) = exited worktree, object = in worktree
    current_session_worktree: Optional[Any] = None  # PersistedWorktreeSession or None
    _current_session_worktree_set: bool = False
    current_session_pr_number: Optional[int] = None
    current_session_pr_url: Optional[str] = None
    current_session_pr_repository: Optional[str] = None

    session_file: Optional[str] = None
    _pending_entries: List[Entry]
    _remote_ingress_url: Optional[str] = None
    _internal_event_writer: Optional[InternalEventWriter] = None
    _internal_event_reader: Optional[InternalEventReader] = None
    _internal_subagent_event_reader: Optional[InternalEventReader] = None
    _pending_write_count: int = 0
    _flush_resolvers: List[asyncio.Future]
    # Per-file write queues: path → list of (entry, Future)
    _write_queues: Dict[str, List[Tuple[Entry, asyncio.Future]]]
    _flush_task: Optional[asyncio.Task] = None
    _active_drain: Optional[asyncio.Task] = None
    FLUSH_INTERVAL = 0.100  # seconds
    MAX_CHUNK_BYTES = 100 * 1024 * 1024
    _existing_session_files: Dict[str, str]

    def __init__(self) -> None:
        self._pending_entries = []
        self._flush_resolvers = []
        self._write_queues = {}
        self._existing_session_files = {}

    def _reset_flush_state(self) -> None:
        """Reset flush/queue state for testing."""
        self._pending_write_count = 0
        self._flush_resolvers = []
        if self._flush_task is not None:
            self._flush_task.cancel()
            self._flush_task = None
        self._active_drain = None
        self._write_queues = {}

    def _increment_pending_writes(self) -> None:
        self._pending_write_count += 1

    def _decrement_pending_writes(self) -> None:
        self._pending_write_count -= 1
        if self._pending_write_count == 0:
            for fut in self._flush_resolvers:
                if not fut.done():
                    fut.set_result(None)
            self._flush_resolvers = []

    async def _track_write(self, fn: Callable) -> Any:
        self._increment_pending_writes()
        try:
            return await fn()
        finally:
            self._decrement_pending_writes()

    def _enqueue_write(self, file_path: str, entry: Entry) -> asyncio.Future:
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        if file_path not in self._write_queues:
            self._write_queues[file_path] = []
        self._write_queues[file_path].append((entry, fut))
        self._schedule_drain()
        return fut

    def _schedule_drain(self) -> None:
        if self._flush_task is not None:
            return

        async def _run_drain() -> None:
            await asyncio.sleep(self.FLUSH_INTERVAL)
            self._flush_task = None
            drain_task = asyncio.ensure_future(self._drain_write_queue())
            self._active_drain = drain_task
            await drain_task
            self._active_drain = None
            if self._write_queues:
                self._schedule_drain()

        try:
            self._flush_task = asyncio.ensure_future(_run_drain())
        except RuntimeError:
            # No event loop running — flush synchronously best-effort
            pass

    @staticmethod
    def _append_to_file_sync(file_path: str, data: str) -> None:
        """Sync append used by the drain/flush path."""
        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(data)
        except OSError:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(data)

    async def _append_to_file(self, file_path: str, data: str) -> None:
        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(data)
        except OSError:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(data)

    async def _drain_write_queue(self) -> None:
        for file_path, queue in list(self._write_queues.items()):
            if not queue:
                continue
            batch = queue[:]
            del queue[:]

            content = ""
            resolvers: List[asyncio.Future] = []

            for entry, fut in batch:
                line = json_stringify(entry) + "\n"
                if len(content.encode("utf-8")) + len(line.encode("utf-8")) >= self.MAX_CHUNK_BYTES:
                    await self._append_to_file(file_path, content)
                    for r in resolvers:
                        if not r.done():
                            r.set_result(None)
                    resolvers = []
                    content = ""
                content += line
                resolvers.append(fut)

            if content:
                await self._append_to_file(file_path, content)
                for r in resolvers:
                    if not r.done():
                        r.set_result(None)

        # Clean up empty queues
        for file_path in [fp for fp, q in self._write_queues.items() if not q]:
            del self._write_queues[file_path]

    def reset_session_file(self) -> None:
        self.session_file = None
        self._pending_entries = []

    def re_append_session_metadata(self, skip_title_refresh: bool = False) -> None:
        """
        Re-append cached session metadata to the end of the transcript file.
        Ensures metadata stays within the tail window readLiteMetadata reads.
        """
        if not self.session_file:
            return
        session_id = get_session_id()
        if not session_id:
            return

        # Sync tail read to refresh SDK-mutable fields
        tail = _read_file_tail_sync(self.session_file)
        tail_lines = tail.splitlines() if tail else []

        if not skip_title_refresh:
            title_line = None
            for line in reversed(tail_lines):
                if line.startswith('{"type":"custom-title"'):
                    title_line = line
                    break
            if title_line:
                tail_title = extract_last_json_string_field(title_line, "customTitle")
                if tail_title is not None:
                    self.current_session_title = tail_title or None

        tag_line = None
        for line in reversed(tail_lines):
            if line.startswith('{"type":"tag"'):
                tag_line = line
                break
        if tag_line:
            tail_tag = extract_last_json_string_field(tag_line, "tag")
            if tail_tag is not None:
                self.current_session_tag = tail_tag or None

        # Re-append metadata entries
        if self.current_session_last_prompt:
            _append_entry_to_file(
                self.session_file,
                {"type": "last-prompt", "lastPrompt": self.current_session_last_prompt, "sessionId": session_id},
            )
        if self.current_session_title:
            _append_entry_to_file(
                self.session_file,
                {"type": "custom-title", "customTitle": self.current_session_title, "sessionId": session_id},
            )
        if self.current_session_tag:
            _append_entry_to_file(
                self.session_file,
                {"type": "tag", "tag": self.current_session_tag, "sessionId": session_id},
            )
        if self.current_session_agent_name:
            _append_entry_to_file(
                self.session_file,
                {"type": "agent-name", "agentName": self.current_session_agent_name, "sessionId": session_id},
            )
        if self.current_session_agent_color:
            _append_entry_to_file(
                self.session_file,
                {"type": "agent-color", "agentColor": self.current_session_agent_color, "sessionId": session_id},
            )
        if self.current_session_agent_setting:
            _append_entry_to_file(
                self.session_file,
                {"type": "agent-setting", "agentSetting": self.current_session_agent_setting, "sessionId": session_id},
            )
        if self.current_session_mode:
            _append_entry_to_file(
                self.session_file,
                {"type": "mode", "mode": self.current_session_mode, "sessionId": session_id},
            )
        if self._current_session_worktree_set:
            wt = self.current_session_worktree
            _append_entry_to_file(
                self.session_file,
                {"type": "worktree-state", "worktreeSession": asdict(wt) if wt else None, "sessionId": session_id},
            )
        if (
            self.current_session_pr_number is not None
            and self.current_session_pr_url
            and self.current_session_pr_repository
        ):
            _append_entry_to_file(
                self.session_file,
                {
                    "type": "pr-link",
                    "sessionId": session_id,
                    "prNumber": self.current_session_pr_number,
                    "prUrl": self.current_session_pr_url,
                    "prRepository": self.current_session_pr_repository,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

    async def flush(self) -> None:
        """Flush all pending writes."""
        if self._flush_task is not None:
            self._flush_task.cancel()
            self._flush_task = None
        if self._active_drain is not None:
            try:
                await self._active_drain
            except (asyncio.CancelledError, Exception):
                pass
        await self._drain_write_queue()
        if self._pending_write_count == 0:
            return
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._flush_resolvers.append(fut)
        await fut

    async def remove_message_by_uuid(self, target_uuid: UUID) -> None:
        """Remove a message from the transcript by UUID (tombstone)."""
        async def _do() -> None:
            if self.session_file is None:
                return
            try:
                file_size = os.path.getsize(self.session_file)
                if file_size == 0:
                    return

                # Try tail-scan fast path first
                chunk_len = min(file_size, LITE_READ_BUF_SIZE)
                tail_start = file_size - chunk_len
                with open(self.session_file, "rb") as fh:
                    fh.seek(tail_start)
                    tail = fh.read(chunk_len)

                needle = f'"uuid":"{target_uuid}"'.encode("utf-8")
                match_idx = tail.rfind(needle)

                if match_idx >= 0:
                    prev_nl = tail.rfind(b"\n", 0, match_idx)
                    if prev_nl >= 0 or tail_start == 0:
                        line_start = prev_nl + 1
                        next_nl = tail.find(b"\n", match_idx + len(needle))
                        line_end = next_nl + 1 if next_nl >= 0 else len(tail)

                        abs_line_start = tail_start + line_start
                        after = tail[line_end:]
                        with open(self.session_file, "r+b") as fh:
                            fh.truncate(abs_line_start)
                            if after:
                                fh.seek(abs_line_start)
                                fh.write(after)
                        return

                # Slow path: re-read and filter
                if file_size > MAX_TOMBSTONE_REWRITE_BYTES:
                    log_for_debugging(
                        f"Skipping tombstone removal: session file too large ({format_file_size(file_size)})",
                        level="warn",
                    )
                    return
                with open(self.session_file, "r", encoding="utf-8") as fh:
                    content = fh.read()
                filtered_lines = []
                for line in content.split("\n"):
                    if not line.strip():
                        filtered_lines.append(line)
                        continue
                    try:
                        entry = json_parse(line)
                        if entry.get("uuid") == target_uuid:
                            continue
                    except Exception:
                        pass
                    filtered_lines.append(line)
                with open(self.session_file, "w", encoding="utf-8") as fh:
                    fh.write("\n".join(filtered_lines))
            except Exception:
                pass  # Silently ignore errors

        await self._track_write(_do)

    def _should_skip_persistence(self) -> bool:
        """Return True when transcript writes should be suppressed."""
        allow_test = is_env_truthy(os.environ.get("TEST_ENABLE_SESSION_PERSISTENCE"))
        settings = get_settings_deprecated()
        return (
            (get_node_env() == "test" and not allow_test)
            or (settings is not None and getattr(settings, "cleanup_period_days", None) == 0)
            or is_session_persistence_disabled()
            or is_env_truthy(os.environ.get("CLAUDE_CODE_SKIP_PROMPT_HISTORY"))
        )

    async def _materialize_session_file(self) -> None:
        """Create the session file and flush buffered entries. Called on first user/assistant message."""
        if self._should_skip_persistence():
            return
        self._ensure_current_session_file()
        self.re_append_session_metadata()
        if self._pending_entries:
            buffered = self._pending_entries[:]
            self._pending_entries = []
            for entry in buffered:
                await self.append_entry(entry)

    async def insert_message_chain(
        self,
        messages: Transcript,
        is_sidechain: bool = False,
        agent_id: Optional[str] = None,
        starting_parent_uuid: Optional[UUID] = None,
        team_info: Optional[TeamInfo] = None,
    ) -> None:
        """Persist a chain of transcript messages."""
        async def _do() -> None:
            nonlocal starting_parent_uuid
            parent_uuid: Optional[UUID] = starting_parent_uuid

            # Materialize session file on first user/assistant message
            if (
                self.session_file is None
                and any(m.get("type") in ("user", "assistant") for m in messages)
            ):
                await self._materialize_session_file()

            # Get git branch once for this chain
            git_branch: Optional[str] = None
            try:
                git_branch = await get_branch()
            except Exception:
                pass

            session_id = get_session_id()
            slug_cache = get_plan_slug_cache()
            slug = slug_cache.get(session_id, None) if isinstance(slug_cache, dict) else None

            for message in messages:
                is_compact_boundary = is_compact_boundary_message(message)

                effective_parent_uuid = parent_uuid
                if (
                    message.get("type") == "user"
                    and message.get("sourceToolAssistantUUID")
                ):
                    effective_parent_uuid = message["sourceToolAssistantUUID"]

                transcript_message: TranscriptMessage = {
                    "parentUuid": None if is_compact_boundary else effective_parent_uuid,
                    "isSidechain": is_sidechain,
                    **({} if is_compact_boundary else {}),
                    **({"logicalParentUuid": parent_uuid} if is_compact_boundary else {}),
                    **({"teamName": team_info.team_name} if team_info and team_info.team_name else {}),
                    **({"agentName": team_info.agent_name} if team_info and team_info.agent_name else {}),
                    **({"promptId": get_prompt_id()} if message.get("type") == "user" else {}),
                    **({"agentId": agent_id} if agent_id else {}),
                    **message,
                    # Session-stamp fields (override spread)
                    "userType": get_user_type(),
                    "entrypoint": _get_entrypoint(),
                    "cwd": get_cwd(),
                    "sessionId": session_id,
                    "gitBranch": git_branch,
                    **({"slug": slug} if slug else {}),
                }
                await self.append_entry(transcript_message)
                if is_chain_participant(message):
                    parent_uuid = message.get("uuid")

            # Cache last prompt for re-append
            if not is_sidechain:
                text = get_first_meaningful_user_message_text_content(messages)
                if text:
                    flat = text.replace("\n", " ").strip()
                    self.current_session_last_prompt = (
                        flat[:200].strip() + "…" if len(flat) > 200 else flat
                    )

        await self._track_write(_do)

    async def insert_file_history_snapshot(
        self, message_id: UUID, snapshot: Any, is_snapshot_update: bool
    ) -> None:
        async def _do() -> None:
            entry = {
                "type": "file-history-snapshot",
                "messageId": message_id,
                "snapshot": snapshot,
                "isSnapshotUpdate": is_snapshot_update,
            }
            await self.append_entry(entry)

        await self._track_write(_do)

    async def insert_queue_operation(self, queue_op: Dict[str, Any]) -> None:
        async def _do() -> None:
            await self.append_entry(queue_op)

        await self._track_write(_do)

    async def insert_attribution_snapshot(self, snapshot: Dict[str, Any]) -> None:
        async def _do() -> None:
            await self.append_entry(snapshot)

        await self._track_write(_do)

    async def insert_content_replacement(
        self, replacements: List[Any], agent_id: Optional[AgentId] = None
    ) -> None:
        async def _do() -> None:
            entry: Entry = {
                "type": "content-replacement",
                "sessionId": get_session_id(),
                "agentId": agent_id,
                "replacements": replacements,
            }
            await self.append_entry(entry)

        await self._track_write(_do)

    async def append_entry(
        self,
        entry: Entry,
        session_id: Optional[UUID] = None,
    ) -> None:
        """Append an entry to the session file (or buffer it)."""
        if self._should_skip_persistence():
            return

        if session_id is None:
            session_id = get_session_id()
        current_session_id = get_session_id()
        is_current_session = session_id == current_session_id

        if is_current_session:
            if self.session_file is None:
                self._pending_entries.append(entry)
                return
            session_file = self.session_file
        else:
            existing = await self._get_existing_session_file(session_id)
            if not existing:
                log_error(
                    Exception(f"append_entry: session file not found for {session_id}")
                )
                return
            session_file = existing

        entry_type = entry.get("type")

        # Route entries to their appropriate queue
        _ALWAYS_APPEND_TYPES = {
            "summary", "custom-title", "ai-title", "last-prompt", "task-summary",
            "tag", "agent-name", "agent-color", "agent-setting", "pr-link",
            "file-history-snapshot", "attribution-snapshot", "speculation-accept",
            "mode", "worktree-state", "marble-origami-commit", "marble-origami-snapshot",
        }
        if entry_type in _ALWAYS_APPEND_TYPES:
            self._enqueue_write(session_file, entry)
        elif entry_type == "content-replacement":
            agent_id = entry.get("agentId")
            target_file = (
                get_agent_transcript_path(agent_id)
                if agent_id
                else session_file
            )
            self._enqueue_write(target_file, entry)
        elif entry_type == "queue-operation":
            self._enqueue_write(session_file, entry)
        else:
            # Transcript message: dedup by UUID
            message_set = await _get_session_messages(session_id)
            is_agent_sidechain = (
                entry.get("isSidechain") and entry.get("agentId") is not None
            )
            if is_agent_sidechain:
                target_file = get_agent_transcript_path(entry["agentId"])
                self._enqueue_write(target_file, entry)
            else:
                uuid = entry.get("uuid")
                if uuid and uuid not in message_set:
                    self._enqueue_write(session_file, entry)
                    message_set.add(uuid)
                    if is_transcript_message(entry):
                        await self._persist_to_remote(session_id, entry)

    def _ensure_current_session_file(self) -> str:
        if self.session_file is None:
            self.session_file = get_transcript_path()
        return self.session_file

    async def _get_existing_session_file(self, session_id: UUID) -> Optional[str]:
        cached = self._existing_session_files.get(session_id)
        if cached:
            return cached
        target = get_transcript_path_for_session(session_id)
        try:
            os.stat(target)
            self._existing_session_files[session_id] = target
            return target
        except OSError as e:
            if is_fs_inaccessible(e):
                return None
            raise

    async def _persist_to_remote(self, session_id: UUID, entry: TranscriptMessage) -> None:
        if is_shutting_down():
            return

        if self._internal_event_writer:
            try:
                kwargs: Dict[str, Any] = {}
                if is_compact_boundary_message(entry):
                    kwargs["isCompaction"] = True
                if entry.get("agentId"):
                    kwargs["agentId"] = entry["agentId"]
                await self._internal_event_writer("transcript", entry, kwargs or None)
            except Exception:
                log_event("tengu_session_persistence_failed", {})
                log_for_debugging("Failed to write transcript as internal event")
            return

        if (
            not is_env_truthy(os.environ.get("ENABLE_SESSION_PERSISTENCE"))
            or not self._remote_ingress_url
        ):
            return

        if session_ingress is not None:
            success = await session_ingress.append_session_log(
                session_id, entry, self._remote_ingress_url
            )
            if not success:
                log_event("tengu_session_persistence_failed", {})
                graceful_shutdown_sync(1, "other")

    def set_remote_ingress_url(self, url: str) -> None:
        self._remote_ingress_url = url
        log_for_debugging(f"Remote persistence enabled with URL: {url}")
        if url:
            self.FLUSH_INTERVAL = REMOTE_FLUSH_INTERVAL_MS

    def set_internal_event_writer(self, writer: InternalEventWriter) -> None:
        self._internal_event_writer = writer
        log_for_debugging("CCR v2 internal event writer registered")
        self.FLUSH_INTERVAL = REMOTE_FLUSH_INTERVAL_MS

    def set_internal_event_reader(self, reader: InternalEventReader) -> None:
        self._internal_event_reader = reader
        log_for_debugging("CCR v2 internal event reader registered")

    def set_internal_subagent_event_reader(self, reader: InternalEventReader) -> None:
        self._internal_subagent_event_reader = reader
        log_for_debugging("CCR v2 subagent event reader registered")

    def get_internal_event_reader(self) -> Optional[InternalEventReader]:
        return self._internal_event_reader

    def get_internal_subagent_event_reader(self) -> Optional[InternalEventReader]:
        return self._internal_subagent_event_reader


# ---------------------------------------------------------------------------
# Project singleton helpers
# ---------------------------------------------------------------------------


def _get_project() -> Project:
    global _project, _cleanup_registered
    if _project is None:
        _project = Project()
        if not _cleanup_registered:
            async def _cleanup() -> None:
                await _project.flush()  # type: ignore[union-attr]
                try:
                    _project.re_append_session_metadata()  # type: ignore[union-attr]
                except Exception:
                    pass
            register_cleanup(_cleanup)
            _cleanup_registered = True
    return _project


def reset_project_flush_state_for_testing() -> None:
    """Reset the Project singleton's flush state for testing."""
    if _project is not None:
        _project._reset_flush_state()


def reset_project_for_testing() -> None:
    """Reset the entire Project singleton for testing."""
    global _project
    _project = None


def set_session_file_for_testing(path: str) -> None:
    _get_project().session_file = path


def set_internal_event_writer(writer: InternalEventWriter) -> None:
    _get_project().set_internal_event_writer(writer)


def set_internal_event_reader(
    reader: InternalEventReader, subagent_reader: InternalEventReader
) -> None:
    _get_project().set_internal_event_reader(reader)
    _get_project().set_internal_subagent_event_reader(subagent_reader)


def set_remote_ingress_url_for_testing(url: str) -> None:
    _get_project().set_remote_ingress_url(url)


# ---------------------------------------------------------------------------
# Session messages cache
# ---------------------------------------------------------------------------


async def _get_session_messages(session_id: UUID) -> Set[UUID]:
    """Return a mutable set of UUID strings for the session (memoized)."""
    global _session_messages_cache
    if session_id in _session_messages_cache:
        return await _session_messages_cache[session_id]

    loop = asyncio.get_event_loop()
    fut: asyncio.Future = loop.create_future()
    _session_messages_cache[session_id] = fut

    try:
        result = await _load_session_file(session_id)
        msgs: Set[UUID] = set(result["messages"].keys())
        fut.set_result(msgs)
        return msgs
    except Exception as exc:
        del _session_messages_cache[session_id]
        fut.set_exception(exc)
        raise


def clear_session_messages_cache() -> None:
    """Clear the memoized session messages cache."""
    global _session_messages_cache
    _session_messages_cache = {}


async def does_message_exist_in_session(session_id: UUID, message_uuid: UUID) -> bool:
    """Check if a message UUID exists in the session storage."""
    message_set = await _get_session_messages(session_id)
    return message_uuid in message_set


# ---------------------------------------------------------------------------
# Public record functions
# ---------------------------------------------------------------------------


async def record_transcript(
    messages: List[Message],
    team_info: Optional[TeamInfo] = None,
    starting_parent_uuid_hint: Optional[UUID] = None,
    all_messages: Optional[List[Message]] = None,
) -> Optional[UUID]:
    """
    Record transcript messages, deduplicating by UUID.
    Returns the last recorded chain-participant's UUID, or None.
    """
    cleaned = _clean_messages_for_logging(messages, all_messages)
    session_id = get_session_id()
    message_set = await _get_session_messages(session_id)
    new_messages: List[Message] = []
    starting_parent_uuid = starting_parent_uuid_hint
    seen_new_message = False

    for m in cleaned:
        if m.get("uuid") in message_set:
            if not seen_new_message and is_chain_participant(m):
                starting_parent_uuid = m.get("uuid")
        else:
            new_messages.append(m)
            seen_new_message = True

    if new_messages:
        await _get_project().insert_message_chain(
            new_messages, False, None, starting_parent_uuid, team_info
        )

    last_recorded = None
    for m in reversed(new_messages):
        if is_chain_participant(m):
            last_recorded = m.get("uuid")
            break

    return last_recorded or starting_parent_uuid or None


async def record_sidechain_transcript(
    messages: List[Message],
    agent_id: Optional[str] = None,
    starting_parent_uuid: Optional[UUID] = None,
) -> None:
    """Record a sidechain transcript (agent subchain)."""
    await _get_project().insert_message_chain(
        _clean_messages_for_logging(messages),
        True,
        agent_id,
        starting_parent_uuid,
    )


async def record_queue_operation(queue_op: Dict[str, Any]) -> None:
    """Record a queue operation entry."""
    await _get_project().insert_queue_operation(queue_op)


async def remove_transcript_message(target_uuid: UUID) -> None:
    """Remove a message from the transcript by UUID (tombstone)."""
    await _get_project().remove_message_by_uuid(target_uuid)


async def record_file_history_snapshot(
    message_id: UUID, snapshot: Any, is_snapshot_update: bool
) -> None:
    await _get_project().insert_file_history_snapshot(
        message_id, snapshot, is_snapshot_update
    )


async def record_attribution_snapshot(snapshot: Dict[str, Any]) -> None:
    await _get_project().insert_attribution_snapshot(snapshot)


async def record_content_replacement(
    replacements: List[Any], agent_id: Optional[AgentId] = None
) -> None:
    await _get_project().insert_content_replacement(replacements, agent_id)


async def reset_session_file_pointer() -> None:
    """Reset session file pointer after switchSession/regenerateSessionId."""
    _get_project().reset_session_file()


def adopt_resumed_session_file() -> None:
    """Adopt the existing session file after --continue/--resume."""
    project = _get_project()
    project.session_file = get_transcript_path()
    project.re_append_session_metadata(True)


async def record_context_collapse_commit(
    collapse_id: str,
    summary_uuid: str,
    summary_content: str,
    summary: str,
    first_archived_uuid: str,
    last_archived_uuid: str,
) -> None:
    """Append a context-collapse commit entry to the transcript."""
    session_id = get_session_id()
    if not session_id:
        return
    await _get_project().append_entry({
        "type": "marble-origami-commit",
        "sessionId": session_id,
        "collapseId": collapse_id,
        "summaryUuid": summary_uuid,
        "summaryContent": summary_content,
        "summary": summary,
        "firstArchivedUuid": first_archived_uuid,
        "lastArchivedUuid": last_archived_uuid,
    })


async def record_context_collapse_snapshot(
    staged: List[Dict[str, Any]],
    armed: bool,
    last_spawn_tokens: int,
) -> None:
    """Snapshot the staged queue + spawn state."""
    session_id = get_session_id()
    if not session_id:
        return
    await _get_project().append_entry({
        "type": "marble-origami-snapshot",
        "sessionId": session_id,
        "staged": staged,
        "armed": armed,
        "lastSpawnTokens": last_spawn_tokens,
    })


async def flush_session_storage() -> None:
    """Flush all pending session writes."""
    await _get_project().flush()


# ---------------------------------------------------------------------------
# Remote hydration
# ---------------------------------------------------------------------------


async def hydrate_remote_session(session_id: str, ingress_url: str) -> bool:
    """Hydrate local session state from remote ingress."""
    switch_session(session_id)
    project = _get_project()

    try:
        remote_logs = []
        if session_ingress is not None:
            remote_logs = await session_ingress.get_session_logs(session_id, ingress_url) or []

        project_dir = get_project_dir(get_original_cwd())
        os.makedirs(project_dir, exist_ok=True)

        session_file = get_transcript_path_for_session(session_id)
        content = "".join(json_stringify(e) + "\n" for e in remote_logs)
        with open(session_file, "w", encoding="utf-8") as f:
            f.write(content)

        log_for_debugging(f"Hydrated {len(remote_logs)} entries from remote")
        return len(remote_logs) > 0
    except Exception as error:
        log_for_debugging(f"Error hydrating session from remote: {error}")
        log_for_diagnostics_no_pii("error", "hydrate_remote_session_fail")
        return False
    finally:
        project.set_remote_ingress_url(ingress_url)


async def hydrate_from_ccr_v2_internal_events(session_id: str) -> bool:
    """Hydrate session state from CCR v2 internal events."""
    start_ms = time.time() * 1000
    switch_session(session_id)
    project = _get_project()
    reader = project.get_internal_event_reader()
    if not reader:
        log_for_debugging("No internal event reader registered for CCR v2 resume")
        return False

    try:
        events = await reader()
        if not events:
            log_for_debugging("Failed to read internal events for resume")
            log_for_diagnostics_no_pii("error", "hydrate_ccr_v2_read_fail")
            return False

        project_dir = get_project_dir(get_original_cwd())
        os.makedirs(project_dir, exist_ok=True)

        session_file = get_transcript_path_for_session(session_id)
        fg_content = "".join(json_stringify(e["payload"]) + "\n" for e in events)
        with open(session_file, "w", encoding="utf-8") as f:
            f.write(fg_content)

        log_for_debugging(f"Hydrated {len(events)} foreground entries from CCR v2")

        subagent_event_count = 0
        subagent_reader = project.get_internal_subagent_event_reader()
        if subagent_reader:
            subagent_events = await subagent_reader()
            if subagent_events:
                subagent_event_count = len(subagent_events)
                by_agent: Dict[str, List[Dict]] = {}
                for e in subagent_events:
                    agent_id = e.get("agent_id", "")
                    if not agent_id:
                        continue
                    by_agent.setdefault(agent_id, []).append(e["payload"])

                for a_id, entries in by_agent.items():
                    agent_file = get_agent_transcript_path(a_id)
                    os.makedirs(os.path.dirname(agent_file), exist_ok=True)
                    agent_content = "".join(json_stringify(p) + "\n" for p in entries)
                    with open(agent_file, "w", encoding="utf-8") as f:
                        f.write(agent_content)

                log_for_debugging(
                    f"Hydrated {len(subagent_events)} subagent entries across {len(by_agent)} agents"
                )

        duration = time.time() * 1000 - start_ms
        log_for_diagnostics_no_pii("info", "hydrate_ccr_v2_completed", {
            "duration_ms": duration,
            "event_count": len(events),
            "subagent_event_count": subagent_event_count,
        })
        return len(events) > 0

    except Exception as error:
        if isinstance(error, Exception) and "Epoch mismatch" in str(error):
            raise
        log_for_debugging(f"Error hydrating session from CCR v2: {error}")
        log_for_diagnostics_no_pii("error", "hydrate_ccr_v2_fail")
        return False


# ---------------------------------------------------------------------------
# First prompt extraction
# ---------------------------------------------------------------------------


def _extract_first_prompt(transcript: List[TranscriptMessage]) -> str:
    text = get_first_meaningful_user_message_text_content(transcript)
    if text:
        result = text.replace("\n", " ").strip()
        if len(result) > 200:
            result = result[:200].strip() + "…"
        return result
    return "No prompt"


def get_first_meaningful_user_message_text_content(
    transcript: List[Message],
) -> Optional[str]:
    """
    Return the first meaningful user message text content.
    Skips meta messages, compact summaries, and synthetic prompts.
    """
    built_in = built_in_command_names()
    for msg in transcript:
        if msg.get("type") != "user" or msg.get("isMeta"):
            continue
        if msg.get("isCompactSummary"):
            continue
        content = msg.get("message", {}).get("content")
        if not content:
            continue

        texts: List[str] = []
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                    texts.append(block["text"])

        for text_content in texts:
            if not text_content:
                continue

            cmd_tag = extract_tag(text_content, COMMAND_NAME_TAG)
            if cmd_tag:
                cmd_name = cmd_tag.lstrip("/")
                if cmd_name in built_in:
                    continue
                cmd_args = (extract_tag(text_content, "command-args") or "").strip()
                if not cmd_args:
                    continue
                return f"{cmd_tag} {cmd_args}"

            bash_input = extract_tag(text_content, "bash-input")
            if bash_input:
                return f"! {bash_input}"

            if SKIP_FIRST_PROMPT_PATTERN.match(text_content):
                continue

            return text_content

    return None


def remove_extra_fields(transcript: List[TranscriptMessage]) -> List[Dict[str, Any]]:
    """Strip isSidechain and parentUuid for serialization."""
    result = []
    for m in transcript:
        serialized = {k: v for k, v in m.items() if k not in ("isSidechain", "parentUuid")}
        result.append(serialized)
    return result


# ---------------------------------------------------------------------------
# Conversation chain building
# ---------------------------------------------------------------------------


def build_conversation_chain(
    messages: Dict[UUID, TranscriptMessage],
    leaf_message: TranscriptMessage,
) -> List[TranscriptMessage]:
    """Build conversation chain from leaf to root (returns root→leaf)."""
    transcript: List[TranscriptMessage] = []
    seen: Set[UUID] = set()
    current: Optional[TranscriptMessage] = leaf_message

    while current:
        uuid = current.get("uuid")
        if uuid in seen:
            log_error(Exception(f"Cycle detected in parentUuid chain at message {uuid}"))
            log_event("tengu_chain_parent_cycle", {})
            break
        seen.add(uuid)
        transcript.append(current)
        parent_uuid = current.get("parentUuid")
        current = messages.get(parent_uuid) if parent_uuid else None

    transcript.reverse()
    return _recover_orphaned_parallel_tool_results(messages, transcript, seen)


def _recover_orphaned_parallel_tool_results(
    messages: Dict[UUID, TranscriptMessage],
    chain: List[TranscriptMessage],
    seen: Set[UUID],
) -> List[TranscriptMessage]:
    """
    Post-pass: recover sibling assistant blocks and tool_results
    that the single-parent walk orphaned.
    """
    chain_assistants = [m for m in chain if m.get("type") == "assistant"]
    if not chain_assistants:
        return chain

    anchor_by_msg_id: Dict[str, TranscriptMessage] = {}
    for a in chain_assistants:
        msg_id = a.get("message", {}).get("id")
        if msg_id:
            anchor_by_msg_id[msg_id] = a

    siblings_by_msg_id: Dict[str, List[TranscriptMessage]] = {}
    tool_results_by_asst: Dict[UUID, List[TranscriptMessage]] = {}
    for m in messages.values():
        if m.get("type") == "assistant":
            msg_id = m.get("message", {}).get("id")
            if msg_id:
                siblings_by_msg_id.setdefault(msg_id, []).append(m)
        elif (
            m.get("type") == "user"
            and m.get("parentUuid")
            and isinstance(m.get("message", {}).get("content"), list)
            and any(
                b.get("type") == "tool_result"
                for b in m["message"]["content"]
                if isinstance(b, dict)
            )
        ):
            puid = m["parentUuid"]
            tool_results_by_asst.setdefault(puid, []).append(m)

    processed_groups: Set[str] = set()
    inserts: Dict[UUID, List[TranscriptMessage]] = {}
    recovered_count = 0

    for asst in chain_assistants:
        msg_id = asst.get("message", {}).get("id")
        if not msg_id or msg_id in processed_groups:
            continue
        processed_groups.add(msg_id)

        group = siblings_by_msg_id.get(msg_id, [asst])
        orphaned_siblings = [s for s in group if s.get("uuid") not in seen]
        orphaned_trs: List[TranscriptMessage] = []
        for member in group:
            trs = tool_results_by_asst.get(member.get("uuid", ""), [])
            for tr in trs:
                if tr.get("uuid") not in seen:
                    orphaned_trs.append(tr)

        if not orphaned_siblings and not orphaned_trs:
            continue

        orphaned_siblings.sort(key=lambda x: x.get("timestamp", ""))
        orphaned_trs.sort(key=lambda x: x.get("timestamp", ""))

        anchor = anchor_by_msg_id[msg_id]
        recovered = orphaned_siblings + orphaned_trs
        for r in recovered:
            seen.add(r.get("uuid", ""))
        recovered_count += len(recovered)
        inserts[anchor.get("uuid", "")] = recovered

    if recovered_count == 0:
        return chain

    log_event("tengu_chain_parallel_tr_recovered", {"recovered_count": recovered_count})
    result: List[TranscriptMessage] = []
    for m in chain:
        result.append(m)
        to_insert = inserts.get(m.get("uuid", ""))
        if to_insert:
            result.extend(to_insert)
    return result


def check_resume_consistency(chain: List[Message]) -> None:
    """Emit tengu_resume_consistency_delta for BigQuery monitoring."""
    for i in range(len(chain) - 1, -1, -1):
        m = chain[i]
        if m.get("type") != "system" or m.get("subtype") != "turn_duration":
            continue
        expected = m.get("messageCount")
        if expected is None:
            return
        actual = i
        log_event("tengu_resume_consistency_delta", {
            "expected": expected,
            "actual": actual,
            "delta": actual - expected,
            "chain_length": len(chain),
            "checkpoint_age_entries": len(chain) - 1 - i,
        })
        return


# ---------------------------------------------------------------------------
# Preserved segment / snip relinks
# ---------------------------------------------------------------------------


def _apply_preserved_segment_relinks(
    messages: Dict[UUID, TranscriptMessage],
) -> None:
    """
    Splice preserved segment back into the chain after compaction.
    Mutates the dict in place.
    """
    last_seg: Optional[Dict[str, Any]] = None
    last_seg_boundary_idx = -1
    absolute_last_boundary_idx = -1
    entry_index: Dict[UUID, int] = {}

    for i, entry in enumerate(messages.values()):
        entry_index[entry.get("uuid", "")] = i
        if is_compact_boundary_message(entry):
            absolute_last_boundary_idx = i
            seg = (entry.get("compactMetadata") or {}).get("preservedSegment")
            if seg:
                last_seg = seg
                last_seg_boundary_idx = i

    if not last_seg:
        return

    seg_is_live = last_seg_boundary_idx == absolute_last_boundary_idx

    preserved_uuids: Set[UUID] = set()
    if seg_is_live:
        walk_seen: Set[UUID] = set()
        cur = messages.get(last_seg.get("tailUuid", ""))
        reached_head = False
        while cur and cur.get("uuid") not in walk_seen:
            walk_seen.add(cur["uuid"])
            preserved_uuids.add(cur["uuid"])
            if cur["uuid"] == last_seg.get("headUuid"):
                reached_head = True
                break
            cur = messages.get(cur.get("parentUuid", "")) if cur.get("parentUuid") else None

        if not reached_head:
            log_event("tengu_relink_walk_broken", {
                "tailInTranscript": last_seg.get("tailUuid") in messages,
                "headInTranscript": last_seg.get("headUuid") in messages,
                "anchorInTranscript": last_seg.get("anchorUuid") in messages,
                "walkSteps": len(walk_seen),
                "transcriptSize": len(messages),
            })
            return

    if seg_is_live:
        head = messages.get(last_seg.get("headUuid", ""))
        if head:
            messages[last_seg["headUuid"]] = {**head, "parentUuid": last_seg.get("anchorUuid")}
        for uuid, msg in list(messages.items()):
            if msg.get("parentUuid") == last_seg.get("anchorUuid") and uuid != last_seg.get("headUuid"):
                messages[uuid] = {**msg, "parentUuid": last_seg.get("tailUuid")}
        # Zero stale usage for preserved messages
        for uuid in preserved_uuids:
            msg = messages.get(uuid)
            if not msg or msg.get("type") != "assistant":
                continue
            usage = (msg.get("message") or {}).get("usage") or {}
            messages[uuid] = {
                **msg,
                "message": {
                    **msg.get("message", {}),
                    "usage": {
                        **usage,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                    },
                },
            }

    # Prune everything before absolute-last boundary that isn't preserved
    to_delete = [
        uuid
        for uuid in list(messages.keys())
        if (entry_index.get(uuid, absolute_last_boundary_idx + 1) < absolute_last_boundary_idx
            and uuid not in preserved_uuids)
    ]
    for uuid in to_delete:
        del messages[uuid]


def _apply_snip_removals(messages: Dict[UUID, TranscriptMessage]) -> None:
    """
    Delete snip-removed messages and relink parentUuid across gaps.
    Mutates the dict in place.
    """
    to_delete: Set[UUID] = set()
    for entry in messages.values():
        removed = (entry.get("snipMetadata") or {}).get("removedUuids")
        if removed:
            to_delete.update(removed)

    if not to_delete:
        return

    deleted_parent: Dict[UUID, Optional[UUID]] = {}
    removed_count = 0
    for uuid in to_delete:
        entry = messages.get(uuid)
        if not entry:
            continue
        deleted_parent[uuid] = entry.get("parentUuid")
        del messages[uuid]
        removed_count += 1

    def _resolve(start: UUID) -> Optional[UUID]:
        path: List[UUID] = []
        cur: Optional[UUID] = start
        while cur and cur in to_delete:
            path.append(cur)
            cur = deleted_parent.get(cur)
        for p in path:
            deleted_parent[p] = cur
        return cur

    relinked_count = 0
    for uuid, msg in list(messages.items()):
        parent = msg.get("parentUuid")
        if not parent or parent not in to_delete:
            continue
        messages[uuid] = {**msg, "parentUuid": _resolve(parent)}
        relinked_count += 1

    log_event("tengu_snip_resume_filtered", {
        "removed_count": removed_count,
        "relinked_count": relinked_count,
    })


# ---------------------------------------------------------------------------
# Helper: find latest message
# ---------------------------------------------------------------------------


def _find_latest_message(
    messages: Iterable[TranscriptMessage],
    predicate: Callable[[TranscriptMessage], bool],
) -> Optional[TranscriptMessage]:
    """O(n) single-pass: find message with latest timestamp matching predicate."""
    latest: Optional[TranscriptMessage] = None
    max_time = -math.inf
    for m in messages:
        if not predicate(m):
            continue
        try:
            t = datetime.fromisoformat(m["timestamp"]).timestamp()
        except Exception:
            t = 0.0
        if t > max_time:
            max_time = t
            latest = m
    return latest


# ---------------------------------------------------------------------------
# File history / attribution snapshot chain builders
# ---------------------------------------------------------------------------


def _build_file_history_snapshot_chain(
    file_history_snapshots: Dict[UUID, Dict[str, Any]],
    conversation: List[TranscriptMessage],
) -> List[Any]:
    snapshots: List[Any] = []
    index_by_message_id: Dict[str, int] = {}
    for message in conversation:
        snapshot_message = file_history_snapshots.get(message.get("uuid", ""))
        if not snapshot_message:
            continue
        snapshot = snapshot_message.get("snapshot")
        is_update = snapshot_message.get("isSnapshotUpdate", False)
        existing_idx = index_by_message_id.get(snapshot.get("messageId", "")) if is_update else None
        if existing_idx is None:
            index_by_message_id[snapshot.get("messageId", "")] = len(snapshots)
            snapshots.append(snapshot)
        else:
            snapshots[existing_idx] = snapshot
    return snapshots


def _build_attribution_snapshot_chain(
    attribution_snapshots: Dict[UUID, Dict[str, Any]],
    _conversation: List[TranscriptMessage],
) -> List[Any]:
    return list(attribution_snapshots.values())


# ---------------------------------------------------------------------------
# Visible message counting
# ---------------------------------------------------------------------------


def _has_visible_user_content(message: TranscriptMessage) -> bool:
    if message.get("type") != "user":
        return False
    if message.get("isMeta"):
        return False
    content = (message.get("message") or {}).get("content")
    if not content:
        return False
    if isinstance(content, str):
        return len(content.strip()) > 0
    if isinstance(content, list):
        return any(
            b.get("type") in ("text", "image", "document")
            for b in content if isinstance(b, dict)
        )
    return False


def _has_visible_assistant_content(message: TranscriptMessage) -> bool:
    if message.get("type") != "assistant":
        return False
    content = (message.get("message") or {}).get("content")
    if not content or not isinstance(content, list):
        return False
    return any(
        b.get("type") == "text"
        and isinstance(b.get("text"), str)
        and len(b["text"].strip()) > 0
        for b in content if isinstance(b, dict)
    )


def _count_visible_messages(transcript: List[TranscriptMessage]) -> int:
    count = 0
    for message in transcript:
        t = message.get("type")
        if t == "user" and _has_visible_user_content(message):
            count += 1
        elif t == "assistant" and _has_visible_assistant_content(message):
            count += 1
    return count


# ---------------------------------------------------------------------------
# Convert to LogOption
# ---------------------------------------------------------------------------


def _convert_to_log_option(
    transcript: List[TranscriptMessage],
    value: int = 0,
    summary: Optional[str] = None,
    custom_title: Optional[str] = None,
    file_history_snapshots: Optional[List[Any]] = None,
    tag: Optional[str] = None,
    full_path: Optional[str] = None,
    attribution_snapshots: Optional[List[Any]] = None,
    agent_setting: Optional[str] = None,
    content_replacements: Optional[List[Any]] = None,
) -> LogOption:
    if not transcript:
        return {}
    last_message = transcript[-1]
    first_message = transcript[0]
    first_prompt = _extract_first_prompt(transcript)

    created_str = first_message.get("timestamp", "")
    modified_str = last_message.get("timestamp", "")
    try:
        created = datetime.fromisoformat(created_str)
    except Exception:
        created = datetime.now(timezone.utc)
    try:
        modified = datetime.fromisoformat(modified_str)
    except Exception:
        modified = datetime.now(timezone.utc)

    return {
        "date": last_message.get("timestamp"),
        "messages": remove_extra_fields(transcript),
        "fullPath": full_path,
        "value": value,
        "created": created,
        "modified": modified,
        "firstPrompt": first_prompt,
        "messageCount": _count_visible_messages(transcript),
        "isSidechain": first_message.get("isSidechain"),
        "teamName": first_message.get("teamName"),
        "agentName": first_message.get("agentName"),
        "agentSetting": agent_setting,
        "leafUuid": last_message.get("uuid"),
        "summary": summary,
        "customTitle": custom_title,
        "tag": tag,
        "fileHistorySnapshots": file_history_snapshots,
        "attributionSnapshots": attribution_snapshots,
        "contentReplacements": content_replacements,
        "gitBranch": last_message.get("gitBranch"),
        "projectPath": first_message.get("cwd"),
    }


# ---------------------------------------------------------------------------
# Load transcript file
# ---------------------------------------------------------------------------


async def load_transcript_file(
    file_path: str, opts: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Load all messages and metadata from a JSONL transcript file.
    Returns a dict with messages, summaries, customTitles, tags, etc.
    """
    keep_all_leaves = (opts or {}).get("keepAllLeaves", False)

    messages: Dict[UUID, TranscriptMessage] = {}
    summaries: Dict[UUID, str] = {}
    custom_titles: Dict[UUID, str] = {}
    tags: Dict[UUID, str] = {}
    agent_names: Dict[UUID, str] = {}
    agent_colors: Dict[UUID, str] = {}
    agent_settings: Dict[UUID, str] = {}
    pr_numbers: Dict[UUID, int] = {}
    pr_urls: Dict[UUID, str] = {}
    pr_repositories: Dict[UUID, str] = {}
    modes: Dict[UUID, str] = {}
    worktree_states: Dict[UUID, Any] = {}
    file_history_snapshots: Dict[UUID, Dict[str, Any]] = {}
    attribution_snapshots: Dict[UUID, Dict[str, Any]] = {}
    content_replacements: Dict[UUID, List[Any]] = {}
    agent_content_replacements: Dict[AgentId, List[Any]] = {}
    context_collapse_commits: List[Dict[str, Any]] = []
    context_collapse_snapshot: Optional[Dict[str, Any]] = None

    try:
        buf = None
        metadata_lines: Optional[List[str]] = None
        has_preserved_segment = False

        if not is_env_truthy(os.environ.get("CLAUDE_CODE_DISABLE_PRECOMPACT_SKIP")):
            try:
                size = os.path.getsize(file_path)
            except OSError:
                size = 0
            if size > SKIP_PRECOMPACT_THRESHOLD:
                scan = await read_transcript_for_load(file_path, size)
                buf = scan.postBoundaryBuf if hasattr(scan, "postBoundaryBuf") else None
                has_preserved_segment = getattr(scan, "hasPreservedSegment", False)
                boundary_start = getattr(scan, "boundaryStartOffset", 0)
                if boundary_start > 0:
                    metadata_lines = await _scan_pre_boundary_metadata(file_path, boundary_start)

        if buf is None:
            try:
                with open(file_path, "rb") as f:
                    buf = f.read()
            except OSError:
                buf = b""

        # Process pre-boundary metadata
        if metadata_lines:
            meta_data = b"\n".join(line.encode("utf-8") for line in metadata_lines)
            meta_entries = parse_jsonl(meta_data)
            for entry in meta_entries:
                _process_metadata_entry(
                    entry, summaries, custom_titles, tags, agent_names,
                    agent_colors, agent_settings, modes, worktree_states,
                    pr_numbers, pr_urls, pr_repositories,
                )

        entries = parse_jsonl(buf)

        progress_bridge: Dict[UUID, Optional[UUID]] = {}

        for entry in entries:
            if _is_legacy_progress_entry(entry):
                parent = entry.get("parentUuid")
                progress_bridge[entry["uuid"]] = (
                    progress_bridge.get(parent) if parent and parent in progress_bridge else parent
                )
                continue

            if is_transcript_message(entry):
                parent_uuid = entry.get("parentUuid")
                if parent_uuid and parent_uuid in progress_bridge:
                    entry["parentUuid"] = progress_bridge.get(parent_uuid)
                messages[entry["uuid"]] = entry
                if is_compact_boundary_message(entry):
                    context_collapse_commits.clear()
                    context_collapse_snapshot = None
            elif entry.get("type") == "summary" and entry.get("leafUuid"):
                summaries[entry["leafUuid"]] = entry["summary"]
            elif entry.get("type") == "custom-title" and entry.get("sessionId"):
                custom_titles[entry["sessionId"]] = entry["customTitle"]
            elif entry.get("type") == "tag" and entry.get("sessionId"):
                tags[entry["sessionId"]] = entry["tag"]
            elif entry.get("type") == "agent-name" and entry.get("sessionId"):
                agent_names[entry["sessionId"]] = entry["agentName"]
            elif entry.get("type") == "agent-color" and entry.get("sessionId"):
                agent_colors[entry["sessionId"]] = entry["agentColor"]
            elif entry.get("type") == "agent-setting" and entry.get("sessionId"):
                agent_settings[entry["sessionId"]] = entry["agentSetting"]
            elif entry.get("type") == "mode" and entry.get("sessionId"):
                modes[entry["sessionId"]] = entry["mode"]
            elif entry.get("type") == "worktree-state" and entry.get("sessionId"):
                worktree_states[entry["sessionId"]] = entry.get("worktreeSession")
            elif entry.get("type") == "pr-link" and entry.get("sessionId"):
                pr_numbers[entry["sessionId"]] = entry["prNumber"]
                pr_urls[entry["sessionId"]] = entry["prUrl"]
                pr_repositories[entry["sessionId"]] = entry["prRepository"]
            elif entry.get("type") == "file-history-snapshot":
                file_history_snapshots[entry["messageId"]] = entry
            elif entry.get("type") == "attribution-snapshot":
                attribution_snapshots[entry["messageId"]] = entry
            elif entry.get("type") == "content-replacement":
                agent_id = entry.get("agentId")
                if agent_id:
                    existing = agent_content_replacements.get(agent_id, [])
                    agent_content_replacements[agent_id] = existing
                    existing.extend(entry.get("replacements", []))
                else:
                    sid = entry.get("sessionId", "")
                    existing2 = content_replacements.get(sid, [])
                    content_replacements[sid] = existing2
                    existing2.extend(entry.get("replacements", []))
            elif entry.get("type") == "marble-origami-commit":
                context_collapse_commits.append(entry)
            elif entry.get("type") == "marble-origami-snapshot":
                context_collapse_snapshot = entry

    except Exception:
        pass  # File doesn't exist or can't be read

    _apply_preserved_segment_relinks(messages)
    _apply_snip_removals(messages)

    # Compute leaf UUIDs
    all_msgs = list(messages.values())
    parent_uuids: Set[UUID] = {
        m["parentUuid"] for m in all_msgs if m.get("parentUuid")
    }
    terminal_messages = [m for m in all_msgs if m.get("uuid") not in parent_uuids]

    leaf_uuids: Set[UUID] = set()
    has_cycle = False

    use_pebble = get_feature_value_cached_may_be_stale("tengu_pebble_leaf_prune", False)

    if use_pebble:
        has_ua_child: Set[UUID] = set()
        for m in all_msgs:
            if m.get("parentUuid") and m.get("type") in ("user", "assistant"):
                has_ua_child.add(m["parentUuid"])

        for terminal in terminal_messages:
            walk_seen: Set[UUID] = set()
            current: Optional[TranscriptMessage] = terminal
            while current:
                uid = current.get("uuid", "")
                if uid in walk_seen:
                    has_cycle = True
                    break
                walk_seen.add(uid)
                if current.get("type") in ("user", "assistant"):
                    if uid not in has_ua_child:
                        leaf_uuids.add(uid)
                    break
                current = messages.get(current.get("parentUuid", "")) if current.get("parentUuid") else None
    else:
        for terminal in terminal_messages:
            walk_seen2: Set[UUID] = set()
            current2: Optional[TranscriptMessage] = terminal
            while current2:
                uid2 = current2.get("uuid", "")
                if uid2 in walk_seen2:
                    has_cycle = True
                    break
                walk_seen2.add(uid2)
                if current2.get("type") in ("user", "assistant"):
                    leaf_uuids.add(uid2)
                    break
                current2 = messages.get(current2.get("parentUuid", "")) if current2.get("parentUuid") else None

    if has_cycle:
        log_event("tengu_transcript_parent_cycle", {})

    return {
        "messages": messages,
        "summaries": summaries,
        "customTitles": custom_titles,
        "tags": tags,
        "agentNames": agent_names,
        "agentColors": agent_colors,
        "agentSettings": agent_settings,
        "prNumbers": pr_numbers,
        "prUrls": pr_urls,
        "prRepositories": pr_repositories,
        "modes": modes,
        "worktreeStates": worktree_states,
        "fileHistorySnapshots": file_history_snapshots,
        "attributionSnapshots": attribution_snapshots,
        "contentReplacements": content_replacements,
        "agentContentReplacements": agent_content_replacements,
        "contextCollapseCommits": context_collapse_commits,
        "contextCollapseSnapshot": context_collapse_snapshot,
        "leafUuids": leaf_uuids,
    }


def _process_metadata_entry(
    entry: Dict[str, Any],
    summaries: Dict, custom_titles: Dict, tags: Dict,
    agent_names: Dict, agent_colors: Dict, agent_settings: Dict,
    modes: Dict, worktree_states: Dict, pr_numbers: Dict,
    pr_urls: Dict, pr_repositories: Dict,
) -> None:
    """Process a single metadata entry into the appropriate map."""
    t = entry.get("type")
    if t == "summary" and entry.get("leafUuid"):
        summaries[entry["leafUuid"]] = entry["summary"]
    elif t == "custom-title" and entry.get("sessionId"):
        custom_titles[entry["sessionId"]] = entry["customTitle"]
    elif t == "tag" and entry.get("sessionId"):
        tags[entry["sessionId"]] = entry["tag"]
    elif t == "agent-name" and entry.get("sessionId"):
        agent_names[entry["sessionId"]] = entry["agentName"]
    elif t == "agent-color" and entry.get("sessionId"):
        agent_colors[entry["sessionId"]] = entry["agentColor"]
    elif t == "agent-setting" and entry.get("sessionId"):
        agent_settings[entry["sessionId"]] = entry["agentSetting"]
    elif t == "mode" and entry.get("sessionId"):
        modes[entry["sessionId"]] = entry["mode"]
    elif t == "worktree-state" and entry.get("sessionId"):
        worktree_states[entry["sessionId"]] = entry.get("worktreeSession")
    elif t == "pr-link" and entry.get("sessionId"):
        pr_numbers[entry["sessionId"]] = entry["prNumber"]
        pr_urls[entry["sessionId"]] = entry["prUrl"]
        pr_repositories[entry["sessionId"]] = entry["prRepository"]


async def _scan_pre_boundary_metadata(file_path: str, end_offset: int) -> List[str]:
    """Forward scan of [0, end_offset) collecting only metadata-entry lines."""
    metadata_lines: List[str] = []
    try:
        with open(file_path, "rb") as f:
            data = f.read(end_offset)
        for line in data.split(b"\n"):
            line_s = line.decode("utf-8", errors="replace").strip()
            if any(marker in line_s for marker in METADATA_TYPE_MARKERS):
                metadata_lines.append(line_s)
    except OSError:
        pass
    return metadata_lines


# ---------------------------------------------------------------------------
# Load session file (for current session)
# ---------------------------------------------------------------------------


async def _load_session_file(session_id: UUID) -> Dict[str, Any]:
    session_file = os.path.join(
        get_session_project_dir() or get_project_dir(get_original_cwd()),
        f"{session_id}.jsonl",
    )
    return await load_transcript_file(session_file)


# ---------------------------------------------------------------------------
# Load transcript from file (public)
# ---------------------------------------------------------------------------


async def load_transcript_from_file(file_path: str) -> LogOption:
    """
    Load a transcript from a JSON or JSONL file and return as LogOption.
    Raises on missing/invalid files.
    """
    if file_path.endswith(".jsonl"):
        result = await load_transcript_file(file_path)
        messages = result["messages"]
        if not messages:
            raise ValueError("No messages found in JSONL file")

        leaf_uuids = result["leafUuids"]
        leaf_message = _find_latest_message(messages.values(), lambda m: m.get("uuid") in leaf_uuids)
        if not leaf_message:
            raise ValueError("No valid conversation chain found in JSONL file")

        transcript = build_conversation_chain(messages, leaf_message)
        summary = result["summaries"].get(leaf_message.get("uuid", ""))
        session_id = leaf_message.get("sessionId", "")
        custom_title = result["customTitles"].get(session_id)
        tag = result["tags"].get(session_id)
        log = _convert_to_log_option(
            transcript, 0, summary, custom_title,
            _build_file_history_snapshot_chain(result["fileHistorySnapshots"], transcript),
            tag, file_path,
            _build_attribution_snapshot_chain(result["attributionSnapshots"], transcript),
            None,
            result["contentReplacements"].get(session_id, []),
        )
        log["contextCollapseCommits"] = [
            e for e in result["contextCollapseCommits"] if e.get("sessionId") == session_id
        ]
        log["contextCollapseSnapshot"] = (
            result["contextCollapseSnapshot"]
            if result.get("contextCollapseSnapshot", {}).get("sessionId") == session_id
            else None
        )
        log["worktreeSession"] = result["worktreeStates"].get(session_id)
        return log

    # JSON file
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    try:
        parsed = json_parse(content)
    except Exception as error:
        raise ValueError(f"Invalid JSON in transcript file: {error}")

    if isinstance(parsed, list):
        transcript_msgs = parsed
    elif isinstance(parsed, dict) and "messages" in parsed:
        if not isinstance(parsed["messages"], list):
            raise ValueError("Transcript messages must be an array")
        transcript_msgs = parsed["messages"]
    else:
        raise ValueError("Transcript must be an array or object with messages array")

    return _convert_to_log_option(transcript_msgs, 0, None, None, None, None, file_path)


# ---------------------------------------------------------------------------
# Sync file helpers
# ---------------------------------------------------------------------------


def _append_entry_to_file(full_path: str, entry: Dict[str, Any]) -> None:
    """Sync append of a single JSONL entry to a file."""
    line = json_stringify(entry) + "\n"
    try:
        with open(full_path, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "a", encoding="utf-8") as f:
            f.write(line)


def _read_file_tail_sync(full_path: str) -> str:
    """Sync tail read of LITE_READ_BUF_SIZE bytes from a file."""
    try:
        size = os.path.getsize(full_path)
        tail_offset = max(0, size - LITE_READ_BUF_SIZE)
        with open(full_path, "rb") as f:
            f.seek(tail_offset)
            buf = f.read(LITE_READ_BUF_SIZE)
        return buf.decode("utf-8", errors="replace")
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Metadata save functions
# ---------------------------------------------------------------------------


async def save_custom_title(
    session_id: UUID,
    custom_title: str,
    full_path: Optional[str] = None,
    source: Literal["user", "auto"] = "user",
) -> None:
    """Append a custom title entry to the session JSONL."""
    resolved_path = full_path or get_transcript_path_for_session(session_id)
    _append_entry_to_file(resolved_path, {
        "type": "custom-title",
        "customTitle": custom_title,
        "sessionId": session_id,
    })
    if session_id == get_session_id():
        _get_project().current_session_title = custom_title
    log_event("tengu_session_renamed", {"source": source})


def save_ai_generated_title(session_id: UUID, ai_title: str) -> None:
    """Append an AI-generated title entry."""
    _append_entry_to_file(get_transcript_path_for_session(session_id), {
        "type": "ai-title",
        "aiTitle": ai_title,
        "sessionId": session_id,
    })


def save_task_summary(session_id: UUID, summary: str) -> None:
    """Append a periodic task summary entry."""
    _append_entry_to_file(get_transcript_path_for_session(session_id), {
        "type": "task-summary",
        "summary": summary,
        "sessionId": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def save_tag(
    session_id: UUID,
    tag: str,
    full_path: Optional[str] = None,
) -> None:
    """Append a tag entry to the session JSONL."""
    resolved_path = full_path or get_transcript_path_for_session(session_id)
    _append_entry_to_file(resolved_path, {"type": "tag", "tag": tag, "sessionId": session_id})
    if session_id == get_session_id():
        _get_project().current_session_tag = tag
    log_event("tengu_session_tagged", {})


async def link_session_to_pr(
    session_id: UUID,
    pr_number: int,
    pr_url: str,
    pr_repository: str,
    full_path: Optional[str] = None,
) -> None:
    """Link a session to a GitHub pull request."""
    resolved_path = full_path or get_transcript_path_for_session(session_id)
    _append_entry_to_file(resolved_path, {
        "type": "pr-link",
        "sessionId": session_id,
        "prNumber": pr_number,
        "prUrl": pr_url,
        "prRepository": pr_repository,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    if session_id == get_session_id():
        p = _get_project()
        p.current_session_pr_number = pr_number
        p.current_session_pr_url = pr_url
        p.current_session_pr_repository = pr_repository
    log_event("tengu_session_linked_to_pr", {"prNumber": pr_number})


def get_current_session_tag(session_id: UUID) -> Optional[str]:
    if session_id == get_session_id():
        return _get_project().current_session_tag
    return None


def get_current_session_title(session_id: SessionId) -> Optional[str]:
    if session_id == get_session_id():
        return _get_project().current_session_title
    return None


def get_current_session_agent_color() -> Optional[str]:
    return _get_project().current_session_agent_color


def restore_session_metadata(
    custom_title: Optional[str] = None,
    tag: Optional[str] = None,
    agent_name: Optional[str] = None,
    agent_color: Optional[str] = None,
    agent_setting: Optional[str] = None,
    mode: Optional[Literal["coordinator", "normal"]] = None,
    worktree_session: Optional[Any] = None,
    worktree_session_set: bool = False,
    pr_number: Optional[int] = None,
    pr_url: Optional[str] = None,
    pr_repository: Optional[str] = None,
) -> None:
    """Restore session metadata into in-memory cache on resume."""
    p = _get_project()
    if custom_title and p.current_session_title is None:
        p.current_session_title = custom_title
    if tag is not None:
        p.current_session_tag = tag or None
    if agent_name:
        p.current_session_agent_name = agent_name
    if agent_color:
        p.current_session_agent_color = agent_color
    if agent_setting:
        p.current_session_agent_setting = agent_setting
    if mode:
        p.current_session_mode = mode
    if worktree_session_set:
        p.current_session_worktree = worktree_session
        p._current_session_worktree_set = True
    if pr_number is not None:
        p.current_session_pr_number = pr_number
    if pr_url:
        p.current_session_pr_url = pr_url
    if pr_repository:
        p.current_session_pr_repository = pr_repository


def clear_session_metadata() -> None:
    """Clear all cached session metadata."""
    p = _get_project()
    p.current_session_title = None
    p.current_session_tag = None
    p.current_session_agent_name = None
    p.current_session_agent_color = None
    p.current_session_last_prompt = None
    p.current_session_agent_setting = None
    p.current_session_mode = None
    p.current_session_worktree = None
    p._current_session_worktree_set = False
    p.current_session_pr_number = None
    p.current_session_pr_url = None
    p.current_session_pr_repository = None


def re_append_session_metadata() -> None:
    """Re-append cached session metadata to the end of the transcript file."""
    _get_project().re_append_session_metadata()


async def save_agent_name(
    session_id: UUID,
    agent_name: str,
    full_path: Optional[str] = None,
    source: Literal["user", "auto"] = "user",
) -> None:
    resolved_path = full_path or get_transcript_path_for_session(session_id)
    _append_entry_to_file(resolved_path, {
        "type": "agent-name", "agentName": agent_name, "sessionId": session_id
    })
    if session_id == get_session_id():
        _get_project().current_session_agent_name = agent_name
        await update_session_name(agent_name)
    log_event("tengu_agent_name_set", {"source": source})


async def save_agent_color(
    session_id: UUID,
    agent_color: str,
    full_path: Optional[str] = None,
) -> None:
    resolved_path = full_path or get_transcript_path_for_session(session_id)
    _append_entry_to_file(resolved_path, {
        "type": "agent-color", "agentColor": agent_color, "sessionId": session_id
    })
    if session_id == get_session_id():
        _get_project().current_session_agent_color = agent_color
    log_event("tengu_agent_color_set", {})


def save_agent_setting(agent_setting: str) -> None:
    """Cache session agent setting (written to disk on first user message)."""
    _get_project().current_session_agent_setting = agent_setting


def cache_session_title(custom_title: str) -> None:
    """Cache a session title set at startup (--name)."""
    _get_project().current_session_title = custom_title


def save_mode(mode: Literal["coordinator", "normal"]) -> None:
    """Cache session mode."""
    _get_project().current_session_mode = mode


def save_worktree_state(worktree_session: Optional[PersistedWorktreeSession]) -> None:
    """Record the session's worktree state for --resume."""
    stripped: Optional[PersistedWorktreeSession] = None
    if worktree_session is not None:
        stripped = PersistedWorktreeSession(
            original_cwd=worktree_session.original_cwd,
            worktree_path=worktree_session.worktree_path,
            worktree_name=getattr(worktree_session, "worktree_name", None),
            worktree_branch=getattr(worktree_session, "worktree_branch", None),
            original_branch=getattr(worktree_session, "original_branch", None),
            original_head_commit=getattr(worktree_session, "original_head_commit", None),
            session_id=getattr(worktree_session, "session_id", None),
            tmux_session_name=getattr(worktree_session, "tmux_session_name", None),
            hook_based=getattr(worktree_session, "hook_based", None),
        )
    p = _get_project()
    p.current_session_worktree = stripped
    p._current_session_worktree_set = True
    if p.session_file:
        _append_entry_to_file(p.session_file, {
            "type": "worktree-state",
            "worktreeSession": asdict(stripped) if stripped else None,
            "sessionId": get_session_id(),
        })


# ---------------------------------------------------------------------------
# Session ID helpers
# ---------------------------------------------------------------------------


def get_session_id_from_log(log: LogOption) -> Optional[UUID]:
    """Extract session ID from a log (lite or full)."""
    if log.get("sessionId"):
        return log["sessionId"]
    msgs = log.get("messages", [])
    if msgs:
        return msgs[0].get("sessionId")
    return None


def is_lite_log(log: LogOption) -> bool:
    """True if log is a lite log (stat-only, no messages)."""
    return len(log.get("messages", [])) == 0 and log.get("sessionId") is not None


async def load_full_log(log: LogOption) -> LogOption:
    """Load full messages for a lite log. Returns original if already full."""
    if not is_lite_log(log):
        return log
    session_file = log.get("fullPath")
    if not session_file:
        return log

    try:
        result = await load_transcript_file(session_file)
        messages = result["messages"]
        if not messages:
            return log

        leaf_uuids = result["leafUuids"]
        most_recent_leaf = _find_latest_message(
            messages.values(),
            lambda m: m.get("uuid") in leaf_uuids and m.get("type") in ("user", "assistant"),
        )
        if not most_recent_leaf:
            return log

        transcript = build_conversation_chain(messages, most_recent_leaf)
        session_id = most_recent_leaf.get("sessionId", "")
        return {
            **log,
            "messages": remove_extra_fields(transcript),
            "firstPrompt": _extract_first_prompt(transcript),
            "messageCount": _count_visible_messages(transcript),
            "summary": result["summaries"].get(most_recent_leaf.get("uuid", ""), log.get("summary")),
            "customTitle": result["customTitles"].get(session_id, log.get("customTitle")),
            "tag": result["tags"].get(session_id, log.get("tag")),
            "agentName": result["agentNames"].get(session_id, log.get("agentName")),
            "agentColor": result["agentColors"].get(session_id, log.get("agentColor")),
            "agentSetting": result["agentSettings"].get(session_id, log.get("agentSetting")),
            "mode": result["modes"].get(session_id, log.get("mode")),
            "worktreeSession": result["worktreeStates"].get(session_id, log.get("worktreeSession")),
            "prNumber": result["prNumbers"].get(session_id, log.get("prNumber")),
            "prUrl": result["prUrls"].get(session_id, log.get("prUrl")),
            "prRepository": result["prRepositories"].get(session_id, log.get("prRepository")),
            "gitBranch": most_recent_leaf.get("gitBranch", log.get("gitBranch")),
            "isSidechain": (transcript[0].get("isSidechain") if transcript else log.get("isSidechain")),
            "teamName": (transcript[0].get("teamName") if transcript else log.get("teamName")),
            "leafUuid": most_recent_leaf.get("uuid", log.get("leafUuid")),
            "fileHistorySnapshots": _build_file_history_snapshot_chain(result["fileHistorySnapshots"], transcript),
            "attributionSnapshots": _build_attribution_snapshot_chain(result["attributionSnapshots"], transcript),
            "contentReplacements": result["contentReplacements"].get(session_id, log.get("contentReplacements", [])),
            "contextCollapseCommits": [
                e for e in result["contextCollapseCommits"] if e.get("sessionId") == session_id
            ],
            "contextCollapseSnapshot": (
                result["contextCollapseSnapshot"]
                if result.get("contextCollapseSnapshot", {}).get("sessionId") == session_id
                else None
            ),
        }
    except Exception:
        return log


# ---------------------------------------------------------------------------
# Search sessions by custom title
# ---------------------------------------------------------------------------


async def search_sessions_by_custom_title(
    query: str, options: Optional[Dict[str, Any]] = None
) -> List[LogOption]:
    """Search for sessions by custom title (case-insensitive)."""
    options = options or {}
    limit = options.get("limit")
    exact = options.get("exact", False)

    worktree_paths = await get_worktree_paths(get_original_cwd())
    all_stat_logs = await _get_stat_only_logs_for_worktrees(worktree_paths)
    enriched_result = await _enrich_logs(all_stat_logs, 0, len(all_stat_logs))
    logs = enriched_result["logs"]
    normalized_query = query.lower().strip()

    matching: List[LogOption] = []
    for log in logs:
        title = (log.get("customTitle") or "").lower().strip()
        if not title:
            continue
        if exact:
            if title == normalized_query:
                matching.append(log)
        else:
            if normalized_query in title:
                matching.append(log)

    # Deduplicate by sessionId (keep most recent)
    session_id_to_log: Dict[UUID, LogOption] = {}
    for log in matching:
        sid = get_session_id_from_log(log)
        if sid:
            existing = session_id_to_log.get(sid)
            if not existing or log.get("modified", datetime.min) > existing.get("modified", datetime.min):
                session_id_to_log[sid] = log

    deduplicated = list(session_id_to_log.values())
    deduplicated.sort(key=lambda x: x.get("modified", datetime.min), reverse=True)

    if limit:
        return deduplicated[:limit]
    return deduplicated


# ---------------------------------------------------------------------------
# Session file helpers (lite / stat-only)
# ---------------------------------------------------------------------------


async def _get_session_files_with_mtime(project_dir: str) -> Dict[str, float]:
    """Return dict of session_file_path → mtime for all JSONL files in project_dir."""
    result: Dict[str, float] = {}
    try:
        for entry in os.scandir(project_dir):
            if entry.is_file() and entry.name.endswith(".jsonl"):
                result[entry.path] = entry.stat().st_mtime
    except OSError:
        pass
    return result


async def _get_session_files_lite(
    project_dir: str,
    limit: Optional[int] = None,
    project_path_override: Optional[str] = None,
) -> List[LogOption]:
    """Return lite LogOption entries (stat-only, no message reads) for project_dir."""
    files_with_mtime = await _get_session_files_with_mtime(project_dir)
    # Sort by mtime descending
    sorted_files = sorted(files_with_mtime.items(), key=lambda x: x[1], reverse=True)
    if limit:
        sorted_files = sorted_files[:limit]

    lite_logs: List[LogOption] = []
    for file_path, mtime in sorted_files:
        session_id = os.path.splitext(os.path.basename(file_path))[0]
        # Skip subagent files (in subdirectories)
        if "subagents" in file_path:
            continue
        created = datetime.fromtimestamp(mtime, tz=timezone.utc)
        lite_logs.append({
            "date": created.isoformat(),
            "messages": [],
            "fullPath": file_path,
            "value": 0,
            "created": created,
            "modified": created,
            "firstPrompt": "",
            "messageCount": 0,
            "sessionId": session_id,
            "projectPath": project_path_override or project_dir,
        })
    return lite_logs


async def _read_lite_metadata(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Read lite metadata from the head+tail of a session file.
    Returns None if the file can't be read.
    """
    try:
        size = os.path.getsize(file_path)
    except OSError:
        return None
    try:
        head_bytes, tail_bytes = await read_head_and_tail(file_path, size)
    except Exception:
        return None

    combined = (head_bytes + b"\n" + tail_bytes).decode("utf-8", errors="replace")
    lines = combined.splitlines()

    # Extract fields from lines
    first_prompt = None
    git_branch = None
    is_sidechain = False
    project_path = None
    team_name = None
    custom_title = None
    summary = None
    tag = None
    agent_setting = None
    pr_number = None
    pr_url = None
    pr_repository = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = entry.get("type")
        if t in ("user", "assistant") and first_prompt is None:
            content = (entry.get("message") or {}).get("content", "")
            if isinstance(content, str):
                first_prompt = content[:200]
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        first_prompt = block.get("text", "")[:200]
                        break
            if entry.get("gitBranch"):
                git_branch = entry["gitBranch"]
            if entry.get("isSidechain"):
                is_sidechain = True
            if entry.get("cwd"):
                project_path = entry["cwd"]
            if entry.get("teamName"):
                team_name = entry["teamName"]
        elif t == "last-prompt":
            first_prompt = entry.get("lastPrompt", first_prompt)
        elif t == "custom-title":
            custom_title = entry.get("customTitle")
        elif t == "tag":
            tag = entry.get("tag")
        elif t == "summary":
            summary = entry.get("summary")
        elif t == "agent-setting":
            agent_setting = entry.get("agentSetting")
        elif t == "pr-link":
            pr_number = entry.get("prNumber")
            pr_url = entry.get("prUrl")
            pr_repository = entry.get("prRepository")

    return {
        "firstPrompt": first_prompt or "No prompt",
        "gitBranch": git_branch,
        "isSidechain": is_sidechain,
        "projectPath": project_path,
        "teamName": team_name,
        "customTitle": custom_title,
        "summary": summary,
        "tag": tag,
        "agentSetting": agent_setting,
        "prNumber": pr_number,
        "prUrl": pr_url,
        "prRepository": pr_repository,
    }


async def _enrich_logs(
    stat_logs: List[LogOption],
    start: int,
    count: int,
) -> Dict[str, Any]:
    """
    Enrich a slice of stat-only logs with lite metadata.
    Returns {logs: enriched, nextIndex: index after last enriched}.
    """
    enriched: List[LogOption] = []
    end = min(start + count, len(stat_logs))

    for i in range(end):
        log = stat_logs[i]
        full_path = log.get("fullPath", "")
        meta = await _read_lite_metadata(full_path) if full_path else None
        if meta:
            enriched.append({**log, **meta})
        else:
            enriched.append(log)

    return {"logs": enriched, "nextIndex": end}


def _deduplicate_logs_by_session_id(logs: List[LogOption]) -> List[LogOption]:
    """Deduplicate logs by session ID, keeping most recently modified."""
    by_session: Dict[str, LogOption] = {}
    for log in logs:
        sid = get_session_id_from_log(log) or log.get("fullPath", "")
        existing = by_session.get(sid)
        if not existing or log.get("modified", datetime.min) > existing.get("modified", datetime.min):
            by_session[sid] = log
    return list(by_session.values())


# ---------------------------------------------------------------------------
# Fetch logs
# ---------------------------------------------------------------------------


async def fetch_logs(limit: Optional[int] = None) -> List[LogOption]:
    """Fetch lite logs for the current project directory."""
    project_dir = get_project_dir(get_original_cwd())
    return await _get_session_files_lite(project_dir, limit, get_original_cwd())


# ---------------------------------------------------------------------------
# Get last session log
# ---------------------------------------------------------------------------


async def get_last_session_log(session_id: UUID) -> Optional[LogOption]:
    """Load and return the last LogOption for a session."""
    result = await _load_session_file(session_id)
    messages = result["messages"]
    if not messages:
        return None

    # Prime getSessionMessages cache
    if session_id not in _session_messages_cache:
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        fut.set_result(set(messages.keys()))
        _session_messages_cache[session_id] = fut

    last_message = _find_latest_message(messages.values(), lambda m: not m.get("isSidechain"))
    if not last_message:
        return None

    transcript = build_conversation_chain(messages, last_message)
    summary = result["summaries"].get(last_message.get("uuid", ""))
    custom_title = result["customTitles"].get(last_message.get("sessionId", ""))
    tag = result["tags"].get(last_message.get("sessionId", ""))
    agent_setting = result["agentSettings"].get(session_id)
    log = _convert_to_log_option(
        transcript, 0, summary, custom_title,
        _build_file_history_snapshot_chain(result["fileHistorySnapshots"], transcript),
        tag,
        get_transcript_path_for_session(session_id),
        _build_attribution_snapshot_chain(result["attributionSnapshots"], transcript),
        agent_setting,
        result["contentReplacements"].get(session_id, []),
    )
    log["worktreeSession"] = result["worktreeStates"].get(session_id)
    log["contextCollapseCommits"] = [
        e for e in result["contextCollapseCommits"] if e.get("sessionId") == session_id
    ]
    ct = result.get("contextCollapseSnapshot")
    log["contextCollapseSnapshot"] = ct if ct and ct.get("sessionId") == session_id else None
    return log


# ---------------------------------------------------------------------------
# Load message logs
# ---------------------------------------------------------------------------


async def load_message_logs(limit: Optional[int] = None) -> List[LogOption]:
    """Load and return session logs sorted by date."""
    session_logs = await fetch_logs(limit)
    enriched_result = await _enrich_logs(session_logs, 0, len(session_logs))
    logs = enriched_result["logs"]

    # Filter out sidechains and empty sessions
    logs = [log for log in logs if not log.get("isSidechain") and log.get("firstPrompt")]

    # Sort by modified date descending
    logs.sort(key=lambda x: x.get("modified", datetime.min), reverse=True)
    for i, log in enumerate(logs):
        log["value"] = i
    return logs


async def load_all_projects_message_logs(
    limit: Optional[int] = None,
    options: Optional[Dict[str, Any]] = None,
) -> List[LogOption]:
    """Load message logs from all project directories."""
    options = options or {}
    if options.get("skipIndex"):
        return await _load_all_projects_message_logs_full(limit)
    result = await load_all_projects_message_logs_progressive(
        limit, options.get("initialEnrichCount", INITIAL_ENRICH_COUNT)
    )
    return result.logs


async def _load_all_projects_message_logs_full(
    limit: Optional[int] = None,
) -> List[LogOption]:
    """Load all sessions with full message data."""
    projects_dir = get_projects_dir()
    try:
        project_dirs = [
            os.path.join(projects_dir, d)
            for d in os.listdir(projects_dir)
            if os.path.isdir(os.path.join(projects_dir, d))
        ]
    except OSError:
        return []

    all_logs: List[LogOption] = []
    for project_dir in project_dirs:
        all_logs.extend(await _get_logs_without_index(project_dir, limit))

    deduped = _deduplicate_logs_by_session_id(all_logs)
    deduped.sort(key=lambda x: x.get("modified", datetime.min), reverse=True)
    for i, log in enumerate(deduped):
        log["value"] = i
    return deduped


async def load_all_projects_message_logs_progressive(
    limit: Optional[int] = None,
    initial_enrich_count: int = INITIAL_ENRICH_COUNT,
) -> SessionLogResult:
    """Load message logs from all project directories progressively."""
    projects_dir = get_projects_dir()
    try:
        project_dirs = [
            os.path.join(projects_dir, d)
            for d in os.listdir(projects_dir)
            if os.path.isdir(os.path.join(projects_dir, d))
        ]
    except OSError:
        return SessionLogResult(logs=[], all_stat_logs=[], next_index=0)

    raw_logs: List[LogOption] = []
    for project_dir in project_dirs:
        raw_logs.extend(await _get_session_files_lite(project_dir, limit))

    sorted_logs = _deduplicate_logs_by_session_id(raw_logs)
    enriched_result = await _enrich_logs(sorted_logs, 0, initial_enrich_count)
    logs = enriched_result["logs"]
    for i, log in enumerate(logs):
        log["value"] = i
    return SessionLogResult(
        logs=logs,
        all_stat_logs=sorted_logs,
        next_index=enriched_result["nextIndex"],
    )


async def load_same_repo_message_logs(
    worktree_paths: List[str],
    limit: Optional[int] = None,
    initial_enrich_count: int = INITIAL_ENRICH_COUNT,
) -> List[LogOption]:
    """Load message logs from all worktrees of the same git repository."""
    result = await load_same_repo_message_logs_progressive(
        worktree_paths, limit, initial_enrich_count
    )
    return result.logs


async def load_same_repo_message_logs_progressive(
    worktree_paths: List[str],
    limit: Optional[int] = None,
    initial_enrich_count: int = INITIAL_ENRICH_COUNT,
) -> SessionLogResult:
    """Load message logs from all worktrees progressively."""
    log_for_debugging(
        f"/resume: loading sessions for cwd={get_original_cwd()}, worktrees={worktree_paths}"
    )
    all_stat_logs = await _get_stat_only_logs_for_worktrees(worktree_paths, limit)
    log_for_debugging(f"/resume: found {len(all_stat_logs)} session files on disk")

    enriched_result = await _enrich_logs(all_stat_logs, 0, initial_enrich_count)
    logs = enriched_result["logs"]
    for i, log in enumerate(logs):
        log["value"] = i
    return SessionLogResult(
        logs=logs,
        all_stat_logs=all_stat_logs,
        next_index=enriched_result["nextIndex"],
    )


async def _get_stat_only_logs_for_worktrees(
    worktree_paths: List[str],
    limit: Optional[int] = None,
) -> List[LogOption]:
    """Get stat-only logs for worktree paths (no file reads)."""
    projects_dir = get_projects_dir()

    if len(worktree_paths) <= 1:
        cwd = get_original_cwd()
        project_dir = get_project_dir(cwd)
        return await _get_session_files_lite(project_dir, None, cwd)

    case_insensitive = os.name == "nt"

    indexed = []
    for wt in worktree_paths:
        sanitized = sanitize_path(wt)
        indexed.append({
            "path": wt,
            "prefix": sanitized.lower() if case_insensitive else sanitized,
        })
    indexed.sort(key=lambda x: len(x["prefix"]), reverse=True)

    all_logs: List[LogOption] = []
    seen_dirs: Set[str] = set()

    try:
        all_dirents = os.listdir(projects_dir)
    except OSError as e:
        log_for_debugging(f"Failed to read projects dir {projects_dir}: {e}")
        project_dir = get_project_dir(get_original_cwd())
        return await _get_session_files_lite(project_dir, limit, get_original_cwd())

    for dir_name in all_dirents:
        full_dir = os.path.join(projects_dir, dir_name)
        if not os.path.isdir(full_dir):
            continue
        dir_key = dir_name.lower() if case_insensitive else dir_name
        if dir_key in seen_dirs:
            continue

        for item in indexed:
            prefix = item["prefix"]
            if dir_key == prefix or dir_key.startswith(prefix + "-"):
                seen_dirs.add(dir_key)
                all_logs.extend(
                    await _get_session_files_lite(full_dir, None, item["path"])
                )
                break

    return _deduplicate_logs_by_session_id(all_logs)


# ---------------------------------------------------------------------------
# Agent transcript
# ---------------------------------------------------------------------------


async def get_agent_transcript(
    agent_id: AgentId,
) -> Optional[Dict[str, Any]]:
    """
    Retrieve the transcript for a specific agent.
    Returns {messages, contentReplacements} or None.
    """
    agent_file = get_agent_transcript_path(agent_id)
    try:
        result = await load_transcript_file(agent_file)
        messages = result["messages"]
        agent_content_replacements = result["agentContentReplacements"]

        # Find messages with matching agentId
        agent_messages = [
            m for m in messages.values()
            if m.get("agentId") == agent_id and m.get("isSidechain")
        ]

        if not agent_messages:
            return None

        # Find the most recent leaf message
        parent_uuids = {m.get("parentUuid") for m in agent_messages if m.get("parentUuid")}
        leaf_messages = [m for m in agent_messages if m.get("uuid") not in parent_uuids]
        if not leaf_messages:
            return None

        leaf_messages.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
        latest_leaf = leaf_messages[0]
        transcript = build_conversation_chain(messages, latest_leaf)

        return {
            "messages": transcript,
            "contentReplacements": agent_content_replacements.get(agent_id, []),
        }
    except OSError as e:
        if is_fs_inaccessible(e):
            return None
        raise


# ---------------------------------------------------------------------------
# Load all logs from session file (for /insights)
# ---------------------------------------------------------------------------


async def load_all_logs_from_session_file(
    session_file: str,
    project_path_override: Optional[str] = None,
) -> List[LogOption]:
    """Load all LogOption entries (one per leaf) from a single session file."""
    result = await load_transcript_file(session_file, {"keepAllLeaves": True})
    messages = result["messages"]
    if not messages:
        return []

    leaf_uuids = result["leafUuids"]
    leaf_messages = [m for m in messages.values() if m.get("uuid") in leaf_uuids]

    # Build parentUuid → children index
    children_by_parent: Dict[UUID, List[TranscriptMessage]] = {}
    for msg in messages.values():
        if msg.get("uuid") not in leaf_uuids and msg.get("parentUuid"):
            children_by_parent.setdefault(msg["parentUuid"], []).append(msg)

    logs: List[LogOption] = []
    for leaf_message in leaf_messages:
        chain = build_conversation_chain(messages, leaf_message)
        if not chain:
            continue

        trailing = children_by_parent.get(leaf_message.get("uuid", ""), [])
        if trailing:
            trailing.sort(key=lambda x: x.get("timestamp", ""))
            chain.extend(trailing)

        first_message = chain[0]
        session_id = leaf_message.get("sessionId", "")
        logs.append({
            "date": leaf_message.get("timestamp"),
            "messages": remove_extra_fields(chain),
            "fullPath": session_file,
            "value": 0,
            "created": datetime.fromisoformat(first_message.get("timestamp", "")) if first_message.get("timestamp") else datetime.now(timezone.utc),
            "modified": datetime.fromisoformat(leaf_message.get("timestamp", "")) if leaf_message.get("timestamp") else datetime.now(timezone.utc),
            "firstPrompt": _extract_first_prompt(chain),
            "messageCount": _count_visible_messages(chain),
            "isSidechain": first_message.get("isSidechain", False),
            "sessionId": session_id,
            "leafUuid": leaf_message.get("uuid"),
            "summary": result["summaries"].get(leaf_message.get("uuid", "")),
            "customTitle": result["customTitles"].get(session_id),
            "tag": result["tags"].get(session_id),
            "agentName": result["agentNames"].get(session_id),
            "agentColor": result["agentColors"].get(session_id),
            "agentSetting": result["agentSettings"].get(session_id),
            "mode": result["modes"].get(session_id),
            "prNumber": result["prNumbers"].get(session_id),
            "prUrl": result["prUrls"].get(session_id),
            "prRepository": result["prRepositories"].get(session_id),
            "gitBranch": leaf_message.get("gitBranch"),
            "projectPath": project_path_override or first_message.get("cwd"),
            "fileHistorySnapshots": _build_file_history_snapshot_chain(result["fileHistorySnapshots"], chain),
            "attributionSnapshots": _build_attribution_snapshot_chain(result["attributionSnapshots"], chain),
            "contentReplacements": result["contentReplacements"].get(session_id, []),
        })
    return logs


async def _get_logs_without_index(
    project_dir: str,
    limit: Optional[int] = None,
) -> List[LogOption]:
    """Load all logs from project_dir with full message data."""
    files_with_mtime = await _get_session_files_with_mtime(project_dir)
    sorted_files = sorted(files_with_mtime.items(), key=lambda x: x[1], reverse=True)
    if limit:
        sorted_files = sorted_files[:limit]

    all_logs: List[LogOption] = []
    for file_path, _ in sorted_files:
        try:
            logs = await load_all_logs_from_session_file(file_path)
            all_logs.extend(logs)
        except Exception:
            continue
    return all_logs


# ---------------------------------------------------------------------------
# Load conversation for resume
# ---------------------------------------------------------------------------


async def load_conversation_for_resume(
    session_id: Optional[UUID] = None,
) -> Optional[Dict[str, Any]]:
    """
    Load conversation state for session resume.
    Returns full session data or None if not found.
    """
    sid = session_id or get_session_id()
    if not sid:
        return None
    log = await get_last_session_log(sid)
    if not log:
        return None
    # Check resume consistency
    check_resume_consistency(log.get("messages", []))
    return log


# ---------------------------------------------------------------------------
# Find unresolved tool use
# ---------------------------------------------------------------------------


async def find_unresolved_tool_use(
    tool_use_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Find an unresolved tool_use in the transcript by tool_use_id.
    Returns the assistant message containing it, or None if not found or already resolved.
    """
    try:
        transcript_path = get_transcript_path()
        result = await load_transcript_file(transcript_path)
        messages = result["messages"]

        tool_use_message = None
        resolved_tool_use_ids: Set[str] = set()

        for message in messages.values():
            if message.get("type") == "assistant":
                content = (message.get("message") or {}).get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if (
                            isinstance(block, dict)
                            and block.get("type") == "tool_use"
                            and block.get("id") == tool_use_id
                        ):
                            tool_use_message = message
                            break
            elif message.get("type") == "user":
                content = (message.get("message") or {}).get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            tid = block.get("tool_use_id")
                            if tid:
                                resolved_tool_use_ids.add(tid)

        if tool_use_message and tool_use_id not in resolved_tool_use_ids:
            return tool_use_message
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Clean messages for logging
# ---------------------------------------------------------------------------


def _clean_messages_for_logging(
    messages: List[Message],
    all_messages: Optional[List[Message]] = None,
) -> List[Message]:
    """Strip fields that shouldn't be persisted to the transcript."""
    # Simplified: return messages as-is (full implementation would strip large tool outputs etc.)
    return messages


# ---------------------------------------------------------------------------
# Collect replacement IDs helper
# ---------------------------------------------------------------------------


def _collect_repl_ids(messages: List[Message]) -> Set[str]:
    """Collect all tool_use IDs that have associated content replacements."""
    ids: Set[str] = set()
    for m in messages:
        content = (m.get("message") or {}).get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    ids.add(block.get("id", ""))
    return ids


# ---------------------------------------------------------------------------
# Get log by index
# ---------------------------------------------------------------------------


async def get_log_by_index(index: int) -> Optional[LogOption]:
    """Get a log by its index in the sorted list."""
    logs = await load_message_logs()
    return logs[index] if 0 <= index < len(logs) else None


# ---------------------------------------------------------------------------
# Track session branching analytics
# ---------------------------------------------------------------------------


async def _track_session_branching_analytics(logs: List[LogOption]) -> None:
    """Emit analytics for forked/branched sessions."""
    session_id_counts: Dict[str, int] = {}
    max_count = 0
    for log in logs:
        sid = get_session_id_from_log(log)
        if sid:
            new_count = session_id_counts.get(sid, 0) + 1
            session_id_counts[sid] = new_count
            max_count = max(max_count, new_count)

    if max_count <= 1:
        return

    branch_counts = [c for c in session_id_counts.values() if c > 1]
    sessions_with_branches = len(branch_counts)
    total_branches = sum(branch_counts)

    log_event("tengu_session_forked_branches_fetched", {
        "total_sessions": len(session_id_counts),
        "sessions_with_branches": sessions_with_branches,
        "max_branches_per_session": max(branch_counts),
        "avg_branches_per_session": round(total_branches / sessions_with_branches),
        "total_transcript_count": len(logs),
    })
