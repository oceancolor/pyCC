# 原始 TS: commands/insights.ts (3200 lines)
"""
insights.py — Python port of commands/insights.ts

Generates a Claude Code usage insights report by:
1. Scanning session JSONL files
2. Extracting per-session metadata (tool stats, languages, git, tokens…)
3. Extracting AI-analysed "facets" (goals, outcomes, friction, satisfaction)
4. Aggregating across all sessions
5. Generating parallel insight sections via Claude
6. Rendering an HTML report
"""

from __future__ import annotations

import asyncio
import difflib
import html as html_lib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Optional runtime deps (graceful stubs when not available)
# ---------------------------------------------------------------------------
try:
    import aiofiles  # type: ignore
    HAS_AIOFILES = True
except ImportError:
    HAS_AIOFILES = False


# ---------------------------------------------------------------------------
# Internal imports — use TODO stubs if the module doesn't exist yet
# ---------------------------------------------------------------------------
try:
    from claude_code.utils.env_utils import get_claude_config_home_dir  # type: ignore
except ImportError:
    def get_claude_config_home_dir() -> str:  # type: ignore[misc]
        return str(Path.home() / ".claude")

try:
    from claude_code.services.api.claude import query_with_model  # type: ignore  # noqa: F401
    HAS_QUERY = True
except ImportError:
    HAS_QUERY = False
    async def query_with_model(**kwargs: Any) -> Any:  # type: ignore[misc]  # TODO: implement
        raise NotImplementedError("query_with_model not available")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AGENT_TOOL_NAME = "Task"
LEGACY_AGENT_TOOL_NAME = "Agent"

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".py": "Python",
    ".rb": "Ruby",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".md": "Markdown",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".sh": "Shell",
    ".css": "CSS",
    ".html": "HTML",
}

LABEL_MAP: dict[str, str] = {
    # Goal categories
    "debug_investigate": "Debug/Investigate",
    "implement_feature": "Implement Feature",
    "fix_bug": "Fix Bug",
    "write_script_tool": "Write Script/Tool",
    "refactor_code": "Refactor Code",
    "configure_system": "Configure System",
    "create_pr_commit": "Create PR/Commit",
    "analyze_data": "Analyze Data",
    "understand_codebase": "Understand Codebase",
    "write_tests": "Write Tests",
    "write_docs": "Write Docs",
    "deploy_infra": "Deploy/Infra",
    "warmup_minimal": "Cache Warmup",
    # Success factors
    "fast_accurate_search": "Fast/Accurate Search",
    "correct_code_edits": "Correct Code Edits",
    "good_explanations": "Good Explanations",
    "proactive_help": "Proactive Help",
    "multi_file_changes": "Multi-file Changes",
    "handled_complexity": "Multi-file Changes",
    "good_debugging": "Good Debugging",
    # Friction types
    "misunderstood_request": "Misunderstood Request",
    "wrong_approach": "Wrong Approach",
    "buggy_code": "Buggy Code",
    "user_rejected_action": "User Rejected Action",
    "claude_got_blocked": "Claude Got Blocked",
    "user_stopped_early": "User Stopped Early",
    "wrong_file_or_location": "Wrong File/Location",
    "excessive_changes": "Excessive Changes",
    "slow_or_verbose": "Slow/Verbose",
    "tool_failed": "Tool Failed",
    "user_unclear": "User Unclear",
    "external_issue": "External Issue",
    # Satisfaction labels
    "frustrated": "Frustrated",
    "dissatisfied": "Dissatisfied",
    "likely_satisfied": "Likely Satisfied",
    "satisfied": "Satisfied",
    "happy": "Happy",
    "unsure": "Unsure",
    "neutral": "Neutral",
    "delighted": "Delighted",
    # Session types
    "single_task": "Single Task",
    "multi_task": "Multi Task",
    "iterative_refinement": "Iterative Refinement",
    "exploration": "Exploration",
    "quick_question": "Quick Question",
    # Outcomes
    "fully_achieved": "Fully Achieved",
    "mostly_achieved": "Mostly Achieved",
    "partially_achieved": "Partially Achieved",
    "not_achieved": "Not Achieved",
    "unclear_from_transcript": "Unclear",
    # Helpfulness
    "unhelpful": "Unhelpful",
    "slightly_helpful": "Slightly Helpful",
    "moderately_helpful": "Moderately Helpful",
    "very_helpful": "Very Helpful",
    "essential": "Essential",
}

FACET_EXTRACTION_PROMPT = """Analyze this Claude Code session and extract structured facets.

CRITICAL GUIDELINES:

1. **goal_categories**: Count ONLY what the USER explicitly asked for.
   - DO NOT count Claude's autonomous codebase exploration
   - DO NOT count work Claude decided to do on its own
   - ONLY count when user says "can you...", "please...", "I need...", "let's..."

2. **user_satisfaction_counts**: Base ONLY on explicit user signals.
   - "Yay!", "great!", "perfect!" → happy
   - "thanks", "looks good", "that works" → satisfied
   - "ok, now let's..." (continuing without complaint) → likely_satisfied
   - "that's not right", "try again" → dissatisfied
   - "this is broken", "I give up" → frustrated

3. **friction_counts**: Be specific about what went wrong.
   - misunderstood_request: Claude interpreted incorrectly
   - wrong_approach: Right goal, wrong solution method
   - buggy_code: Code didn't work correctly
   - user_rejected_action: User said no/stop to a tool call
   - excessive_changes: Over-engineered or changed too much

4. If very short or just warmup, use warmup_minimal for goal_category

SESSION:
"""

SATISFACTION_ORDER = [
    "frustrated",
    "dissatisfied",
    "likely_satisfied",
    "satisfied",
    "happy",
    "unsure",
]

OUTCOME_ORDER = [
    "not_achieved",
    "partially_achieved",
    "mostly_achieved",
    "fully_achieved",
    "unclear_from_transcript",
]

# ---------------------------------------------------------------------------
# Path helpers (lazy — never call get_claude_config_home_dir at import time)
# ---------------------------------------------------------------------------

def _get_data_dir() -> Path:
    return Path(get_claude_config_home_dir()) / "usage-data"

def _get_facets_dir() -> Path:
    return _get_data_dir() / "facets"

def _get_session_meta_dir() -> Path:
    return _get_data_dir() / "session-meta"

def _get_projects_dir() -> Path:
    return Path(get_claude_config_home_dir()) / "projects"

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class SessionMeta:
    session_id: str
    project_path: str
    start_time: str
    duration_minutes: int
    user_message_count: int
    assistant_message_count: int
    tool_counts: dict[str, int] = field(default_factory=dict)
    languages: dict[str, int] = field(default_factory=dict)
    git_commits: int = 0
    git_pushes: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    first_prompt: str = ""
    summary: Optional[str] = None
    user_interruptions: int = 0
    user_response_times: list[float] = field(default_factory=list)
    tool_errors: int = 0
    tool_error_categories: dict[str, int] = field(default_factory=dict)
    uses_task_agent: bool = False
    uses_mcp: bool = False
    uses_web_search: bool = False
    uses_web_fetch: bool = False
    lines_added: int = 0
    lines_removed: int = 0
    files_modified: int = 0
    message_hours: list[int] = field(default_factory=list)
    user_message_timestamps: list[str] = field(default_factory=list)


@dataclass
class SessionFacets:
    session_id: str
    underlying_goal: str
    goal_categories: dict[str, int] = field(default_factory=dict)
    outcome: str = "unclear_from_transcript"
    user_satisfaction_counts: dict[str, int] = field(default_factory=dict)
    claude_helpfulness: str = "moderately_helpful"
    session_type: str = "single_task"
    friction_counts: dict[str, int] = field(default_factory=dict)
    friction_detail: str = ""
    primary_success: str = "none"
    brief_summary: str = ""
    user_instructions_to_claude: list[str] = field(default_factory=list)


@dataclass
class MultiClauding:
    overlap_events: int = 0
    sessions_involved: int = 0
    user_messages_during: int = 0


@dataclass
class AggregatedData:
    total_sessions: int = 0
    total_sessions_scanned: Optional[int] = None
    sessions_with_facets: int = 0
    date_range: dict[str, str] = field(default_factory=lambda: {"start": "", "end": ""})
    total_messages: int = 0
    total_duration_hours: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    tool_counts: dict[str, int] = field(default_factory=dict)
    languages: dict[str, int] = field(default_factory=dict)
    git_commits: int = 0
    git_pushes: int = 0
    projects: dict[str, int] = field(default_factory=dict)
    goal_categories: dict[str, int] = field(default_factory=dict)
    outcomes: dict[str, int] = field(default_factory=dict)
    satisfaction: dict[str, int] = field(default_factory=dict)
    helpfulness: dict[str, int] = field(default_factory=dict)
    session_types: dict[str, int] = field(default_factory=dict)
    friction: dict[str, int] = field(default_factory=dict)
    success: dict[str, int] = field(default_factory=dict)
    session_summaries: list[dict[str, Any]] = field(default_factory=list)
    total_interruptions: int = 0
    total_tool_errors: int = 0
    tool_error_categories: dict[str, int] = field(default_factory=dict)
    user_response_times: list[float] = field(default_factory=list)
    median_response_time: float = 0.0
    avg_response_time: float = 0.0
    sessions_using_task_agent: int = 0
    sessions_using_mcp: int = 0
    sessions_using_web_search: int = 0
    sessions_using_web_fetch: int = 0
    total_lines_added: int = 0
    total_lines_removed: int = 0
    total_files_modified: int = 0
    days_active: int = 0
    messages_per_day: float = 0.0
    message_hours: list[int] = field(default_factory=list)
    multi_clauding: MultiClauding = field(default_factory=MultiClauding)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def get_language_from_path(file_path: str) -> Optional[str]:
    """Return the programming language for a file path based on extension."""
    ext = Path(file_path).suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(ext)


def _count_diff_lines(old: str, new: str) -> tuple[int, int]:
    """Return (lines_added, lines_removed) using unified diff."""
    added = removed = 0
    for line in difflib.unified_diff(
        old.splitlines(), new.splitlines(), lineterm=""
    ):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return added, removed


def _parse_timestamp(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Tool-stats extraction
# ---------------------------------------------------------------------------

def extract_tool_stats(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract tool statistics from a list of log messages."""
    tool_counts: dict[str, int] = {}
    languages: dict[str, int] = {}
    git_commits = 0
    git_pushes = 0
    input_tokens = 0
    output_tokens = 0

    user_interruptions = 0
    user_response_times: list[float] = []
    tool_errors = 0
    tool_error_categories: dict[str, int] = {}
    uses_task_agent = False
    uses_mcp = False
    uses_web_search = False
    uses_web_fetch = False

    lines_added = 0
    lines_removed = 0
    files_modified: set[str] = set()
    message_hours: list[int] = []
    user_message_timestamps: list[str] = []
    last_assistant_timestamp: Optional[str] = None

    for msg in messages:
        msg_type = msg.get("type")
        msg_timestamp = msg.get("timestamp")
        message = msg.get("message") or {}

        # ----------------------------------------------------------------
        # Assistant messages
        # ----------------------------------------------------------------
        if msg_type == "assistant":
            if msg_timestamp:
                last_assistant_timestamp = msg_timestamp

            usage = message.get("usage", {})
            if usage:
                input_tokens += usage.get("input_tokens", 0) or 0
                output_tokens += usage.get("output_tokens", 0) or 0

            content = message.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if block.get("type") != "tool_use":
                        continue
                    tool_name: str = block.get("name", "")
                    tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1

                    if tool_name in (AGENT_TOOL_NAME, LEGACY_AGENT_TOOL_NAME):
                        uses_task_agent = True
                    if tool_name.startswith("mcp__"):
                        uses_mcp = True
                    if tool_name == "WebSearch":
                        uses_web_search = True
                    if tool_name == "WebFetch":
                        uses_web_fetch = True

                    inp = block.get("input") or {}
                    if inp:
                        file_path: str = inp.get("file_path", "")
                        if file_path:
                            lang = get_language_from_path(file_path)
                            if lang:
                                languages[lang] = languages.get(lang, 0) + 1
                            if tool_name in ("Edit", "Write"):
                                files_modified.add(file_path)

                        if tool_name == "Edit":
                            old_str = inp.get("old_string", "") or ""
                            new_str = inp.get("new_string", "") or ""
                            a, r = _count_diff_lines(old_str, new_str)
                            lines_added += a
                            lines_removed += r

                        if tool_name == "Write":
                            write_content = inp.get("content", "") or ""
                            if write_content:
                                lines_added += write_content.count("\n") + 1

                        command: str = inp.get("command", "") or ""
                        if "git commit" in command:
                            git_commits += 1
                        if "git push" in command:
                            git_pushes += 1

        # ----------------------------------------------------------------
        # User messages
        # ----------------------------------------------------------------
        elif msg_type == "user":
            content = message.get("content", [])

            # Determine if this is a real human message (has text block)
            is_human_message = False
            if isinstance(content, str) and content.strip():
                is_human_message = True
            elif isinstance(content, list):
                for block in content:
                    if block.get("type") == "text" and block.get("text"):
                        is_human_message = True
                        break

            if is_human_message:
                if msg_timestamp:
                    try:
                        dt = _parse_timestamp(msg_timestamp)
                        if dt:
                            message_hours.append(dt.hour)
                            user_message_timestamps.append(msg_timestamp)
                    except Exception:
                        pass

                    if last_assistant_timestamp and msg_timestamp:
                        try:
                            a_dt = _parse_timestamp(last_assistant_timestamp)
                            u_dt = _parse_timestamp(msg_timestamp)
                            if a_dt and u_dt:
                                secs = (u_dt - a_dt).total_seconds()
                                if 2 < secs < 3600:
                                    user_response_times.append(secs)
                        except Exception:
                            pass

            # Process tool results for error tracking
            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "tool_result":
                        if block.get("is_error"):
                            tool_errors += 1
                            result_content = block.get("content", "") or ""
                            category = "Other"
                            if isinstance(result_content, str):
                                lc = result_content.lower()
                                if "exit code" in lc:
                                    category = "Command Failed"
                                elif "rejected" in lc or "doesn't want" in lc:
                                    category = "User Rejected"
                                elif (
                                    "string to replace not found" in lc
                                    or "no changes" in lc
                                ):
                                    category = "Edit Failed"
                                elif "modified since read" in lc:
                                    category = "File Changed"
                                elif "exceeds maximum" in lc or "too large" in lc:
                                    category = "File Too Large"
                                elif "file not found" in lc or "does not exist" in lc:
                                    category = "File Not Found"
                            tool_error_categories[category] = (
                                tool_error_categories.get(category, 0) + 1
                            )

            # Check for interruptions
            interrupt_text = "[Request interrupted by user"
            if isinstance(content, str):
                if interrupt_text in content:
                    user_interruptions += 1
            elif isinstance(content, list):
                for block in content:
                    if block.get("type") == "text" and interrupt_text in (
                        block.get("text") or ""
                    ):
                        user_interruptions += 1
                        break

    return {
        "tool_counts": tool_counts,
        "languages": languages,
        "git_commits": git_commits,
        "git_pushes": git_pushes,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "user_interruptions": user_interruptions,
        "user_response_times": user_response_times,
        "tool_errors": tool_errors,
        "tool_error_categories": tool_error_categories,
        "uses_task_agent": uses_task_agent,
        "uses_mcp": uses_mcp,
        "uses_web_search": uses_web_search,
        "uses_web_fetch": uses_web_fetch,
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "files_modified": files_modified,
        "message_hours": message_hours,
        "user_message_timestamps": user_message_timestamps,
    }


# ---------------------------------------------------------------------------
# Session meta extraction
# ---------------------------------------------------------------------------

def extract_session_meta(
    session_id: str,
    project_path: str,
    messages: list[dict[str, Any]],
    created: Optional[datetime] = None,
    modified: Optional[datetime] = None,
    first_prompt: str = "",
    summary: Optional[str] = None,
) -> SessionMeta:
    """Build a SessionMeta from raw session data."""
    stats = extract_tool_stats(messages)

    start_time = (created or datetime.now(timezone.utc)).isoformat()
    duration_minutes = 0
    if created and modified:
        duration_minutes = max(
            0, int((modified - created).total_seconds() / 60)
        )

    user_message_count = 0
    assistant_message_count = 0
    for msg in messages:
        if msg.get("type") == "assistant":
            assistant_message_count += 1
        elif msg.get("type") == "user":
            content = (msg.get("message") or {}).get("content", [])
            is_human = False
            if isinstance(content, str) and content.strip():
                is_human = True
            elif isinstance(content, list):
                for block in content:
                    if block.get("type") == "text" and block.get("text"):
                        is_human = True
                        break
            if is_human:
                user_message_count += 1

    return SessionMeta(
        session_id=session_id,
        project_path=project_path,
        start_time=start_time,
        duration_minutes=duration_minutes,
        user_message_count=user_message_count,
        assistant_message_count=assistant_message_count,
        tool_counts=stats["tool_counts"],
        languages=stats["languages"],
        git_commits=stats["git_commits"],
        git_pushes=stats["git_pushes"],
        input_tokens=stats["input_tokens"],
        output_tokens=stats["output_tokens"],
        first_prompt=first_prompt,
        summary=summary,
        user_interruptions=stats["user_interruptions"],
        user_response_times=stats["user_response_times"],
        tool_errors=stats["tool_errors"],
        tool_error_categories=stats["tool_error_categories"],
        uses_task_agent=stats["uses_task_agent"],
        uses_mcp=stats["uses_mcp"],
        uses_web_search=stats["uses_web_search"],
        uses_web_fetch=stats["uses_web_fetch"],
        lines_added=stats["lines_added"],
        lines_removed=stats["lines_removed"],
        files_modified=len(stats["files_modified"]),
        message_hours=stats["message_hours"],
        user_message_timestamps=stats["user_message_timestamps"],
    )


# ---------------------------------------------------------------------------
# Load sessions from disk
# ---------------------------------------------------------------------------

def _read_jsonl_file(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file and return a list of parsed objects."""
    lines: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if raw:
                    try:
                        lines.append(json.loads(raw))
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass
    return lines


def _get_session_id_from_path(path: Path) -> str:
    return path.stem


def _extract_first_prompt_and_summary(
    messages: list[dict[str, Any]],
) -> tuple[str, Optional[str]]:
    """Return (first_prompt, summary) from messages."""
    first_prompt = ""
    summary: Optional[str] = None

    for msg in messages:
        if msg.get("type") == "user" and not first_prompt:
            content = (msg.get("message") or {}).get("content", "")
            if isinstance(content, str):
                first_prompt = content[:200]
            elif isinstance(content, list):
                for block in content:
                    if block.get("type") == "text":
                        first_prompt = (block.get("text") or "")[:200]
                        break
        if msg.get("type") == "summary":
            summary = msg.get("summary") or msg.get("text")

    return first_prompt, summary


async def load_all_session_meta(
    projects_dir: Optional[Path] = None,
    max_sessions: int = 200,
) -> tuple[list[SessionMeta], int]:
    """
    Load SessionMeta for all sessions found in projects_dir.

    Returns (list_of_metas, total_scanned_count).
    Tries cache first; falls back to parsing JSONL.
    """
    if projects_dir is None:
        projects_dir = _get_projects_dir()

    if not projects_dir.exists():
        return [], 0

    # Collect all .jsonl files sorted by mtime descending
    session_files: list[tuple[float, Path]] = []
    try:
        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            for jsonl_file in project_dir.glob("*.jsonl"):
                try:
                    mtime = jsonl_file.stat().st_mtime
                    session_files.append((mtime, jsonl_file))
                except OSError:
                    pass
    except OSError:
        return [], 0

    session_files.sort(key=lambda x: x[0], reverse=True)
    total_scanned = len(session_files)

    metas: list[SessionMeta] = []
    loaded = 0

    for _mtime, jsonl_path in session_files:
        if loaded >= max_sessions:
            break

        session_id = _get_session_id_from_path(jsonl_path)

        # Try cache
        cached = await _load_cached_session_meta(session_id)
        if cached:
            metas.append(cached)
            loaded += 1
            continue

        # Parse JSONL
        raw_messages = _read_jsonl_file(jsonl_path)
        if not raw_messages:
            continue

        project_path = str(jsonl_path.parent.name)
        first_prompt, summary = _extract_first_prompt_and_summary(raw_messages)

        # Estimate created/modified from message timestamps or file stat
        created: Optional[datetime] = None
        modified: Optional[datetime] = None
        for msg in raw_messages:
            ts_str = msg.get("timestamp")
            if ts_str:
                dt = _parse_timestamp(ts_str)
                if dt:
                    if created is None:
                        created = dt
                    modified = dt
        if created is None:
            try:
                stat = jsonl_path.stat()
                created = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc)
                modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            except OSError:
                pass

        meta = extract_session_meta(
            session_id=session_id,
            project_path=project_path,
            messages=raw_messages,
            created=created,
            modified=modified,
            first_prompt=first_prompt,
            summary=summary,
        )

        # Skip meta-sessions (insights command's own API calls)
        if _is_meta_session(raw_messages):
            continue

        metas.append(meta)
        loaded += 1

        # Save to cache
        await _save_session_meta(meta)

    return metas, total_scanned


def _is_meta_session(messages: list[dict[str, Any]]) -> bool:
    """Return True if this session is a meta-session (insights API call)."""
    for msg in messages[:5]:
        if msg.get("type") == "user":
            content = (msg.get("message") or {}).get("content", "")
            if isinstance(content, str):
                if (
                    "RESPOND WITH ONLY A VALID JSON OBJECT" in content
                    or "record_facets" in content
                ):
                    return True
    return False


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

async def _load_cached_session_meta(session_id: str) -> Optional[SessionMeta]:
    meta_path = _get_session_meta_dir() / f"{session_id}.json"
    try:
        if HAS_AIOFILES:
            import aiofiles  # type: ignore
            async with aiofiles.open(meta_path, encoding="utf-8") as fh:
                raw = await fh.read()
        else:
            raw = meta_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return SessionMeta(**{k: v for k, v in data.items() if k in SessionMeta.__dataclass_fields__})  # type: ignore[attr-defined]
    except Exception:
        return None


async def _save_session_meta(meta: SessionMeta) -> None:
    _get_session_meta_dir().mkdir(parents=True, exist_ok=True)
    meta_path = _get_session_meta_dir() / f"{meta.session_id}.json"
    try:
        import dataclasses
        raw = json.dumps(dataclasses.asdict(meta), indent=2, default=str)
        if HAS_AIOFILES:
            import aiofiles  # type: ignore
            async with aiofiles.open(meta_path, "w", encoding="utf-8") as fh:
                await fh.write(raw)
        else:
            meta_path.write_text(raw, encoding="utf-8")
    except Exception:
        pass


async def _load_cached_facets(session_id: str) -> Optional[SessionFacets]:
    facet_path = _get_facets_dir() / f"{session_id}.json"
    try:
        if HAS_AIOFILES:
            import aiofiles  # type: ignore
            async with aiofiles.open(facet_path, encoding="utf-8") as fh:
                raw = await fh.read()
        else:
            raw = facet_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not _is_valid_session_facets(data):
            facet_path.unlink(missing_ok=True)
            return None
        return SessionFacets(**{k: v for k, v in data.items() if k in SessionFacets.__dataclass_fields__})  # type: ignore[attr-defined]
    except Exception:
        return None


async def _save_facets(facets: SessionFacets) -> None:
    _get_facets_dir().mkdir(parents=True, exist_ok=True)
    facet_path = _get_facets_dir() / f"{facets.session_id}.json"
    try:
        import dataclasses
        raw = json.dumps(dataclasses.asdict(facets), indent=2, default=str)
        if HAS_AIOFILES:
            import aiofiles  # type: ignore
            async with aiofiles.open(facet_path, "w", encoding="utf-8") as fh:
                await fh.write(raw)
        else:
            facet_path.write_text(raw, encoding="utf-8")
    except Exception:
        pass


def _is_valid_session_facets(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    return (
        isinstance(obj.get("underlying_goal"), str)
        and isinstance(obj.get("outcome"), str)
        and isinstance(obj.get("brief_summary"), str)
        and isinstance(obj.get("goal_categories"), dict)
        and isinstance(obj.get("user_satisfaction_counts"), dict)
        and isinstance(obj.get("friction_counts"), dict)
    )


# ---------------------------------------------------------------------------
# Multi-clauding detection
# ---------------------------------------------------------------------------

def detect_multi_clauding(
    sessions: list[SessionMeta],
) -> MultiClauding:
    """
    Detect multi-clauding: concurrent use of multiple Claude sessions.

    Uses a sliding 30-minute window to find the pattern s1 → s2 → s1.
    """
    OVERLAP_WINDOW_MS = 30 * 60 * 1000  # 30 minutes in ms

    all_msgs: list[tuple[int, str]] = []  # (ts_ms, session_id)
    for session in sessions:
        for ts_str in session.user_message_timestamps:
            dt = _parse_timestamp(ts_str)
            if dt:
                all_msgs.append((int(dt.timestamp() * 1000), session.session_id))

    all_msgs.sort(key=lambda x: x[0])

    multi_claude_pairs: set[str] = set()
    messages_during: set[str] = set()

    window_start = 0
    session_last_index: dict[str, int] = {}

    for i, (ts, sid) in enumerate(all_msgs):
        # Shrink window from left
        while window_start < i and ts - all_msgs[window_start][0] > OVERLAP_WINDOW_MS:
            exp_ts, exp_sid = all_msgs[window_start]
            if session_last_index.get(exp_sid) == window_start:
                del session_last_index[exp_sid]
            window_start += 1

        prev_idx = session_last_index.get(sid)
        if prev_idx is not None:
            for j in range(prev_idx + 1, i):
                between_ts, between_sid = all_msgs[j]
                if between_sid != sid:
                    pair = ":".join(sorted([sid, between_sid]))
                    multi_claude_pairs.add(pair)
                    prev_ts = all_msgs[prev_idx][0]
                    messages_during.add(f"{prev_ts}:{sid}")
                    messages_during.add(f"{between_ts}:{between_sid}")
                    messages_during.add(f"{ts}:{sid}")
                    break

        session_last_index[sid] = i

    sessions_with_overlaps: set[str] = set()
    for pair in multi_claude_pairs:
        parts = pair.split(":", 1)
        if len(parts) == 2:
            sessions_with_overlaps.add(parts[0])
            sessions_with_overlaps.add(parts[1])

    return MultiClauding(
        overlap_events=len(multi_claude_pairs),
        sessions_involved=len(sessions_with_overlaps),
        user_messages_during=len(messages_during),
    )


# ---------------------------------------------------------------------------
# Data aggregation
# ---------------------------------------------------------------------------

def aggregate_sessions(
    sessions: list[SessionMeta],
    facets: dict[str, SessionFacets],
) -> AggregatedData:
    """Aggregate all session data and facets into a single AggregatedData."""
    data = AggregatedData(
        total_sessions=len(sessions),
        sessions_with_facets=len(facets),
    )

    dates: list[str] = []
    all_response_times: list[float] = []
    all_message_hours: list[int] = []

    for session in sessions:
        dates.append(session.start_time)
        data.total_messages += session.user_message_count
        data.total_duration_hours += session.duration_minutes / 60.0
        data.total_input_tokens += session.input_tokens
        data.total_output_tokens += session.output_tokens
        data.git_commits += session.git_commits
        data.git_pushes += session.git_pushes

        data.total_interruptions += session.user_interruptions
        data.total_tool_errors += session.tool_errors
        for cat, cnt in session.tool_error_categories.items():
            data.tool_error_categories[cat] = (
                data.tool_error_categories.get(cat, 0) + cnt
            )
        all_response_times.extend(session.user_response_times)

        if session.uses_task_agent:
            data.sessions_using_task_agent += 1
        if session.uses_mcp:
            data.sessions_using_mcp += 1
        if session.uses_web_search:
            data.sessions_using_web_search += 1
        if session.uses_web_fetch:
            data.sessions_using_web_fetch += 1

        data.total_lines_added += session.lines_added
        data.total_lines_removed += session.lines_removed
        data.total_files_modified += session.files_modified
        all_message_hours.extend(session.message_hours)

        for tool, cnt in session.tool_counts.items():
            data.tool_counts[tool] = data.tool_counts.get(tool, 0) + cnt

        for lang, cnt in session.languages.items():
            data.languages[lang] = data.languages.get(lang, 0) + cnt

        if session.project_path:
            data.projects[session.project_path] = (
                data.projects.get(session.project_path, 0) + 1
            )

        sf = facets.get(session.session_id)
        if sf:
            for cat, cnt in sf.goal_categories.items():
                if cnt > 0:
                    data.goal_categories[cat] = (
                        data.goal_categories.get(cat, 0) + cnt
                    )
            data.outcomes[sf.outcome] = data.outcomes.get(sf.outcome, 0) + 1
            for level, cnt in sf.user_satisfaction_counts.items():
                if cnt > 0:
                    data.satisfaction[level] = (
                        data.satisfaction.get(level, 0) + cnt
                    )
            data.helpfulness[sf.claude_helpfulness] = (
                data.helpfulness.get(sf.claude_helpfulness, 0) + 1
            )
            data.session_types[sf.session_type] = (
                data.session_types.get(sf.session_type, 0) + 1
            )
            for ftype, cnt in sf.friction_counts.items():
                if cnt > 0:
                    data.friction[ftype] = data.friction.get(ftype, 0) + cnt
            if sf.primary_success and sf.primary_success != "none":
                data.success[sf.primary_success] = (
                    data.success.get(sf.primary_success, 0) + 1
                )

        if len(data.session_summaries) < 50:
            data.session_summaries.append(
                {
                    "id": session.session_id[:8],
                    "date": (session.start_time.split("T")[0] if "T" in session.start_time else session.start_time),
                    "summary": session.summary or session.first_prompt[:100],
                    "goal": sf.underlying_goal if sf else None,
                }
            )

    dates.sort()
    data.date_range["start"] = dates[0].split("T")[0] if dates else ""
    data.date_range["end"] = dates[-1].split("T")[0] if dates else ""

    data.user_response_times = all_response_times
    if all_response_times:
        sorted_rt = sorted(all_response_times)
        data.median_response_time = sorted_rt[len(sorted_rt) // 2]
        data.avg_response_time = sum(all_response_times) / len(all_response_times)

    unique_days: set[str] = set(d.split("T")[0] for d in dates)
    data.days_active = len(unique_days)
    data.messages_per_day = (
        round(data.total_messages / data.days_active * 10) / 10
        if data.days_active
        else 0.0
    )

    data.message_hours = all_message_hours
    data.multi_clauding = detect_multi_clauding(sessions)

    return data


# ---------------------------------------------------------------------------
# Facet extraction via Claude
# ---------------------------------------------------------------------------

def _format_transcript_for_facets(
    session_id: str,
    start_time: str,
    project_path: str,
    duration_minutes: int,
    messages: list[dict[str, Any]],
) -> str:
    lines: list[str] = [
        f"Session: {session_id[:8]}",
        f"Date: {start_time}",
        f"Project: {project_path}",
        f"Duration: {duration_minutes} min",
        "",
    ]
    for msg in messages:
        if msg.get("type") == "user":
            content = (msg.get("message") or {}).get("content", "")
            if isinstance(content, str):
                lines.append(f"[User]: {content[:500]}")
            elif isinstance(content, list):
                for block in content:
                    if block.get("type") == "text":
                        lines.append(f"[User]: {(block.get('text') or '')[:500]}")
        elif msg.get("type") == "assistant":
            content = (msg.get("message") or {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "text":
                        lines.append(f"[Assistant]: {(block.get('text') or '')[:300]}")
                    elif block.get("type") == "tool_use":
                        lines.append(f"[Tool: {block.get('name', '')}]")
    return "\n".join(lines)


SUMMARIZE_CHUNK_PROMPT = """Summarize this portion of a Claude Code session transcript. Focus on:
1. What the user asked for
2. What Claude did (tools used, files modified)
3. Any friction or issues
4. The outcome

Keep it concise - 3-5 sentences. Preserve specific details like file names, error messages, and user feedback.

TRANSCRIPT CHUNK:
"""


async def _summarize_transcript_chunk(chunk: str) -> str:
    """Summarize a single transcript chunk using Claude."""
    if not HAS_QUERY:
        return chunk[:2000]
    try:
        result = await query_with_model(
            system_prompt=[],
            user_prompt=SUMMARIZE_CHUNK_PROMPT + chunk,
            options={
                "querySource": "insights",
                "isNonInteractiveSession": True,
                "maxOutputTokensOverride": 500,
            },
        )
        text = ""
        content = (
            getattr(result, "content", None)
            or (result.get("message", {}).get("content", []) if isinstance(result, dict) else [])
        )
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text += block.get("text", "")
                elif hasattr(block, "text"):
                    text += getattr(block, "text", "")
        elif isinstance(content, str):
            text = content
        return text or chunk[:2000]
    except Exception:
        return chunk[:2000]


async def _format_transcript_with_summarization(
    session_id: str,
    start_time: str,
    project_path: str,
    duration_minutes: int,
    messages: list[dict[str, Any]],
) -> str:
    """Format transcript, summarising in chunks if it exceeds 30k chars."""
    full_transcript = _format_transcript_for_facets(
        session_id, start_time, project_path, duration_minutes, messages
    )
    if len(full_transcript) <= 30000:
        return full_transcript

    CHUNK_SIZE = 25000
    chunks = [
        full_transcript[i : i + CHUNK_SIZE]
        for i in range(0, len(full_transcript), CHUNK_SIZE)
    ]
    summaries = await asyncio.gather(*[_summarize_transcript_chunk(c) for c in chunks])

    header_lines = [
        f"Session: {session_id[:8]}",
        f"Date: {start_time}",
        f"Project: {project_path}",
        f"Duration: {duration_minutes} min",
        f"[Long session - {len(chunks)} parts summarized]",
        "",
    ]
    return "\n".join(header_lines) + "\n\n---\n\n".join(summaries)


async def extract_facets_with_llm(
    session_id: str,
    start_time: str,
    project_path: str,
    duration_minutes: int,
    messages: list[dict[str, Any]],
) -> Optional[SessionFacets]:
    """Extract session facets using Claude (LLM analysis)."""
    if not HAS_QUERY:
        return None

    transcript = await _format_transcript_with_summarization(
        session_id, start_time, project_path, duration_minutes, messages
    )

    json_prompt = f"""{FACET_EXTRACTION_PROMPT}{transcript}

RESPOND WITH ONLY A VALID JSON OBJECT matching this schema:
{{
  "underlying_goal": "What the user fundamentally wanted to achieve",
  "goal_categories": {{"category_name": count}},
  "outcome": "fully_achieved|mostly_achieved|partially_achieved|not_achieved|unclear_from_transcript",
  "user_satisfaction_counts": {{"level": count}},
  "claude_helpfulness": "unhelpful|slightly_helpful|moderately_helpful|very_helpful|essential",
  "session_type": "single_task|multi_task|iterative_refinement|exploration|quick_question",
  "friction_counts": {{"friction_type": count}},
  "friction_detail": "One sentence describing friction or empty",
  "primary_success": "none|fast_accurate_search|correct_code_edits|good_explanations|proactive_help|multi_file_changes|good_debugging",
  "brief_summary": "One sentence: what user wanted and whether they got it"
}}"""

    try:
        result = await query_with_model(
            system_prompt=[],
            user_prompt=json_prompt,
            options={
                "querySource": "insights",
                "isNonInteractiveSession": True,
                "maxOutputTokensOverride": 4096,
            },
        )

        text = ""
        content = getattr(result, "content", None) or (
            result.get("message", {}).get("content", []) if isinstance(result, dict) else []
        )
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text += block.get("text", "")
                elif hasattr(block, "text"):
                    text += getattr(block, "text", "")
        elif isinstance(content, str):
            text = content

        json_match = re.search(r"\{[\s\S]*\}", text)
        if not json_match:
            return None

        parsed = json.loads(json_match.group(0))
        if not _is_valid_session_facets(parsed):
            return None

        parsed["session_id"] = session_id
        return SessionFacets(
            session_id=session_id,
            underlying_goal=parsed.get("underlying_goal", ""),
            goal_categories=parsed.get("goal_categories", {}),
            outcome=parsed.get("outcome", "unclear_from_transcript"),
            user_satisfaction_counts=parsed.get("user_satisfaction_counts", {}),
            claude_helpfulness=parsed.get("claude_helpfulness", "moderately_helpful"),
            session_type=parsed.get("session_type", "single_task"),
            friction_counts=parsed.get("friction_counts", {}),
            friction_detail=parsed.get("friction_detail", ""),
            primary_success=parsed.get("primary_success", "none"),
            brief_summary=parsed.get("brief_summary", ""),
            user_instructions_to_claude=parsed.get("user_instructions_to_claude", []),
        )
    except Exception as exc:
        print(f"[insights] Facet extraction failed for {session_id}: {exc}")
        return None


# ---------------------------------------------------------------------------
# HTML report generation helpers
# ---------------------------------------------------------------------------

def _escape_html(text: str) -> str:
    return html_lib.escape(str(text))


def _escape_html_with_bold(text: str) -> str:
    escaped = _escape_html(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)


def _generate_bar_chart(
    data: dict[str, int],
    color: str,
    max_items: int = 6,
    fixed_order: Optional[list[str]] = None,
) -> str:
    if fixed_order:
        entries = [
            (k, data[k]) for k in fixed_order if k in data and data[k] > 0
        ]
    else:
        entries = sorted(data.items(), key=lambda x: x[1], reverse=True)[:max_items]

    if not entries:
        return '<p class="empty">No data</p>'

    max_val = max(v for _, v in entries)
    rows: list[str] = []
    for label, count in entries:
        pct = (count / max_val) * 100
        clean = LABEL_MAP.get(label) or label.replace("_", " ").title()
        rows.append(
            f'<div class="bar-row">'
            f'<div class="bar-label">{_escape_html(clean)}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%;background:{color}"></div></div>'
            f'<div class="bar-value">{count}</div>'
            f"</div>"
        )
    return "\n".join(rows)


def _generate_response_time_histogram(times: list[float]) -> str:
    if not times:
        return '<p class="empty">No response time data</p>'

    buckets: dict[str, int] = {
        "2-10s": 0,
        "10-30s": 0,
        "30s-1m": 0,
        "1-2m": 0,
        "2-5m": 0,
        "5-15m": 0,
        ">15m": 0,
    }
    for t in times:
        if t < 10:
            buckets["2-10s"] += 1
        elif t < 30:
            buckets["10-30s"] += 1
        elif t < 60:
            buckets["30s-1m"] += 1
        elif t < 120:
            buckets["1-2m"] += 1
        elif t < 300:
            buckets["2-5m"] += 1
        elif t < 900:
            buckets["5-15m"] += 1
        else:
            buckets[">15m"] += 1

    max_val = max(buckets.values()) or 1
    rows: list[str] = []
    for label, count in buckets.items():
        pct = (count / max_val) * 100
        rows.append(
            f'<div class="bar-row">'
            f'<div class="bar-label">{label}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%;background:#6366f1"></div></div>'
            f'<div class="bar-value">{count}</div>'
            f"</div>"
        )
    return "\n".join(rows)


def _generate_time_of_day_chart(message_hours: list[int]) -> str:
    if not message_hours:
        return '<p class="empty">No time data</p>'

    periods = [
        ("Morning (6-12)", list(range(6, 12))),
        ("Afternoon (12-18)", list(range(12, 18))),
        ("Evening (18-24)", list(range(18, 24))),
        ("Night (0-6)", list(range(0, 6))),
    ]

    hour_counts: dict[int, int] = {}
    for h in message_hours:
        hour_counts[h] = hour_counts.get(h, 0) + 1

    period_counts = [
        (label, sum(hour_counts.get(h, 0) for h in rng))
        for label, rng in periods
    ]
    max_val = max((c for _, c in period_counts), default=1) or 1

    rows: list[str] = []
    for label, count in period_counts:
        pct = (count / max_val) * 100
        rows.append(
            f"<div class=\"bar-row\">"
            f"<div class=\"bar-label\">{label}</div>"
            f"<div class=\"bar-track\"><div class=\"bar-fill\" style=\"width:{pct:.1f}%;background:#8b5cf6\"></div></div>"
            f"<div class=\"bar-value\">{count}</div>"
            f"</div>"
        )
    return f'<div id="hour-histogram">{"".join(rows)}</div>'


def _get_hour_counts_json(message_hours: list[int]) -> str:
    hour_counts: dict[int, int] = {}
    for h in message_hours:
        hour_counts[h] = hour_counts.get(h, 0) + 1
    return json.dumps(hour_counts)


# ---------------------------------------------------------------------------
# AI insight section generation
# ---------------------------------------------------------------------------

INSIGHT_SECTIONS = [
    {
        "name": "project_areas",
        "prompt": (
            "Analyze this Claude Code usage data and identify project areas.\n\n"
            "RESPOND WITH ONLY A VALID JSON OBJECT:\n"
            '{\n  "areas": [\n    {"name": "Area name", "session_count": N, "description": "2-3 sentences."}\n  ]\n}\n'
            "Include 4-5 areas."
        ),
        "max_tokens": 8192,
    },
    {
        "name": "interaction_style",
        "prompt": (
            "Analyze this Claude Code usage data and describe the user's interaction style.\n\n"
            "RESPOND WITH ONLY A VALID JSON OBJECT:\n"
            '{\n  "narrative": "2-3 paragraphs. Use second person.",\n  "key_pattern": "One sentence summary"\n}'
        ),
        "max_tokens": 8192,
    },
    {
        "name": "what_works",
        "prompt": (
            "Analyze this Claude Code usage data and identify what's working well. Use second person.\n\n"
            "RESPOND WITH ONLY A VALID JSON OBJECT:\n"
            '{\n  "intro": "1 sentence",\n  "impressive_workflows": [\n    {"title": "Short title", "description": "2-3 sentences"}\n  ]\n}\n'
            "Include 3 impressive workflows."
        ),
        "max_tokens": 8192,
    },
    {
        "name": "friction_analysis",
        "prompt": (
            "Analyze this Claude Code usage data and identify friction points. Use second person.\n\n"
            "RESPOND WITH ONLY A VALID JSON OBJECT:\n"
            '{\n  "intro": "1 sentence",\n  "categories": [\n    {"category": "Name", "description": "1-2 sentences", "examples": ["example 1", "example 2"]}\n  ]\n}\n'
            "Include 3 friction categories with 2 examples each."
        ),
        "max_tokens": 8192,
    },
    {
        "name": "suggestions",
        "prompt": (
            "Analyze this Claude Code usage data and suggest improvements.\n\n"
            "RESPOND WITH ONLY A VALID JSON OBJECT:\n"
            "{\n"
            '  "claude_md_additions": [{"addition": "...", "why": "...", "prompt_scaffold": "..."}],\n'
            '  "features_to_try": [{"feature": "...", "one_liner": "...", "why_for_you": "...", "example_code": "..."}],\n'
            '  "usage_patterns": [{"title": "...", "suggestion": "...", "detail": "...", "copyable_prompt": "..."}]\n'
            "}\n"
            "Include 2-3 items per category."
        ),
        "max_tokens": 8192,
    },
    {
        "name": "on_the_horizon",
        "prompt": (
            "Analyze this Claude Code usage data and identify future opportunities.\n\n"
            "RESPOND WITH ONLY A VALID JSON OBJECT:\n"
            "{\n"
            '  "intro": "1 sentence",\n'
            '  "opportunities": [{"title": "...", "whats_possible": "2-3 sentences", "how_to_try": "...", "copyable_prompt": "..."}]\n'
            "}\n"
            "Include 3 opportunities."
        ),
        "max_tokens": 8192,
    },
    {
        "name": "fun_ending",
        "prompt": (
            "Analyze this Claude Code usage data and find a memorable moment.\n\n"
            "RESPOND WITH ONLY A VALID JSON OBJECT:\n"
            '{\n  "headline": "A memorable qualitative moment, not a statistic.",\n  "detail": "Brief context"\n}'
        ),
        "max_tokens": 8192,
    },
]


async def _generate_section_insight(
    section: dict[str, Any],
    data_context: str,
) -> tuple[str, Optional[Any]]:
    """Generate a single insight section using Claude."""
    if not HAS_QUERY:
        return section["name"], None
    try:
        result = await query_with_model(
            system_prompt=[],
            user_prompt=section["prompt"] + "\n\nDATA:\n" + data_context,
            options={
                "querySource": "insights",
                "isNonInteractiveSession": True,
                "maxOutputTokensOverride": section["max_tokens"],
            },
        )

        text = ""
        content = (
            getattr(result, "content", None)
            or (
                result.get("message", {}).get("content", [])
                if isinstance(result, dict)
                else []
            )
        )
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text += block.get("text", "")
                elif hasattr(block, "text"):
                    text += getattr(block, "text", "")
        elif isinstance(content, str):
            text = content

        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            try:
                return section["name"], json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
    except Exception as exc:
        print(f"[insights] Section {section['name']} failed: {exc}")
    return section["name"], None


async def generate_insights_report(data: AggregatedData, facets: dict[str, SessionFacets]) -> dict[str, Any]:
    """Generate all insight sections in parallel, then produce the at-a-glance summary."""
    facet_summaries = "\n".join(
        f"- {f.brief_summary} ({f.outcome}, {f.claude_helpfulness})"
        for f in list(facets.values())[:50]
    )
    friction_details = "\n".join(
        f"- {f.friction_detail}"
        for f in list(facets.values())[:20]
        if f.friction_detail
    )
    user_instructions = "\n".join(
        f"- {instr}"
        for f in facets.values()
        for instr in (f.user_instructions_to_claude or [])[:15]
    )

    data_context = json.dumps(
        {
            "sessions": data.total_sessions,
            "analyzed": data.sessions_with_facets,
            "date_range": data.date_range,
            "messages": data.total_messages,
            "hours": round(data.total_duration_hours),
            "commits": data.git_commits,
            "top_tools": sorted(data.tool_counts.items(), key=lambda x: x[1], reverse=True)[:8],
            "top_goals": sorted(data.goal_categories.items(), key=lambda x: x[1], reverse=True)[:8],
            "outcomes": data.outcomes,
            "satisfaction": data.satisfaction,
            "friction": data.friction,
            "success": data.success,
            "languages": data.languages,
        },
        indent=2,
    )

    full_context = (
        data_context
        + "\n\nSESSION SUMMARIES:\n"
        + facet_summaries
        + "\n\nFRICTION DETAILS:\n"
        + friction_details
        + "\n\nUSER INSTRUCTIONS TO CLAUDE:\n"
        + (user_instructions or "None captured")
    )

    section_results = await asyncio.gather(
        *[_generate_section_insight(sec, full_context) for sec in INSIGHT_SECTIONS]
    )

    insights: dict[str, Any] = {}
    for name, result in section_results:
        if result is not None:
            insights[name] = result

    # --- At a Glance ---
    project_areas_text = "\n".join(
        f"- {a['name']}: {a['description']}"
        for a in (insights.get("project_areas") or {}).get("areas", [])
    )
    big_wins_text = "\n".join(
        f"- {w['title']}: {w['description']}"
        for w in (insights.get("what_works") or {}).get("impressive_workflows", [])
    )
    friction_text = "\n".join(
        f"- {c['category']}: {c['description']}"
        for c in (insights.get("friction_analysis") or {}).get("categories", [])
    )
    features_text = "\n".join(
        f"- {f['feature']}: {f['one_liner']}"
        for f in (insights.get("suggestions") or {}).get("features_to_try", [])
    )
    patterns_text = "\n".join(
        f"- {p['title']}: {p['suggestion']}"
        for p in (insights.get("suggestions") or {}).get("usage_patterns", [])
    )
    horizon_text = "\n".join(
        f"- {o['title']}: {o['whats_possible']}"
        for o in (insights.get("on_the_horizon") or {}).get("opportunities", [])
    )

    at_a_glance_prompt = f"""You're writing an "At a Glance" summary for a Claude Code usage insights report.

Use this 4-part structure:
1. **What's working** - user's unique interaction style and impactful things done
2. **What's hindering you** - Claude's fault vs user-side friction
3. **Quick wins to try** - specific CC features to try
4. **Ambitious workflows for better models** - workflows possible with improved models

RESPOND WITH ONLY A VALID JSON OBJECT:
{{
  "whats_working": "...",
  "whats_hindering": "...",
  "quick_wins": "...",
  "ambitious_workflows": "..."
}}

SESSION DATA:
{full_context}

## Project Areas
{project_areas_text}

## Big Wins
{big_wins_text}

## Friction Categories
{friction_text}

## Features to Try
{features_text}

## Usage Patterns
{patterns_text}

## On the Horizon
{horizon_text}"""

    _, at_a_glance_result = await _generate_section_insight(
        {"name": "at_a_glance", "prompt": at_a_glance_prompt, "max_tokens": 8192},
        "",
    )
    if at_a_glance_result:
        insights["at_a_glance"] = at_a_glance_result

    return insights


# ---------------------------------------------------------------------------
# HTML report renderer
# ---------------------------------------------------------------------------

_CSS = """
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; background: #f8fafc; color: #334155; line-height: 1.65; padding: 48px 24px; }
    .container { max-width: 800px; margin: 0 auto; }
    h1 { font-size: 32px; font-weight: 700; color: #0f172a; margin-bottom: 8px; }
    h2 { font-size: 20px; font-weight: 600; color: #0f172a; margin-top: 48px; margin-bottom: 16px; }
    .subtitle { color: #64748b; font-size: 15px; margin-bottom: 32px; }
    .nav-toc { display: flex; flex-wrap: wrap; gap: 8px; margin: 24px 0 32px 0; padding: 16px; background: white; border-radius: 8px; border: 1px solid #e2e8f0; }
    .nav-toc a { font-size: 12px; color: #64748b; text-decoration: none; padding: 6px 12px; border-radius: 6px; background: #f1f5f9; transition: all 0.15s; }
    .nav-toc a:hover { background: #e2e8f0; color: #334155; }
    .stats-row { display: flex; gap: 24px; margin-bottom: 40px; padding: 20px 0; border-top: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; flex-wrap: wrap; }
    .stat { text-align: center; }
    .stat-value { font-size: 24px; font-weight: 700; color: #0f172a; }
    .stat-label { font-size: 11px; color: #64748b; text-transform: uppercase; }
    .at-a-glance { background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border: 1px solid #f59e0b; border-radius: 12px; padding: 20px 24px; margin-bottom: 32px; }
    .glance-title { font-size: 16px; font-weight: 700; color: #92400e; margin-bottom: 16px; }
    .glance-sections { display: flex; flex-direction: column; gap: 12px; }
    .glance-section { font-size: 14px; color: #78350f; line-height: 1.6; }
    .glance-section strong { color: #92400e; }
    .see-more { color: #b45309; text-decoration: none; font-size: 13px; white-space: nowrap; }
    .see-more:hover { text-decoration: underline; }
    .project-areas { display: flex; flex-direction: column; gap: 12px; margin-bottom: 32px; }
    .project-area { background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }
    .area-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
    .area-name { font-weight: 600; font-size: 15px; color: #0f172a; }
    .area-count { font-size: 12px; color: #64748b; background: #f1f5f9; padding: 2px 8px; border-radius: 4px; }
    .area-desc { font-size: 14px; color: #475569; line-height: 1.5; }
    .narrative { background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin-bottom: 24px; }
    .narrative p { margin-bottom: 12px; font-size: 14px; color: #475569; line-height: 1.7; }
    .key-insight { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 12px 16px; margin-top: 12px; font-size: 14px; color: #166534; }
    .section-intro { font-size: 14px; color: #64748b; margin-bottom: 16px; }
    .big-wins { display: flex; flex-direction: column; gap: 12px; margin-bottom: 24px; }
    .big-win { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 16px; }
    .big-win-title { font-weight: 600; font-size: 15px; color: #166534; margin-bottom: 8px; }
    .big-win-desc { font-size: 14px; color: #15803d; line-height: 1.5; }
    .friction-categories { display: flex; flex-direction: column; gap: 16px; margin-bottom: 24px; }
    .friction-category { background: #fef2f2; border: 1px solid #fca5a5; border-radius: 8px; padding: 16px; }
    .friction-title { font-weight: 600; font-size: 15px; color: #991b1b; margin-bottom: 6px; }
    .friction-desc { font-size: 13px; color: #7f1d1d; margin-bottom: 10px; }
    .friction-examples { margin: 0 0 0 20px; font-size: 13px; color: #334155; }
    .friction-examples li { margin-bottom: 4px; }
    .claude-md-section { background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 16px; margin-bottom: 20px; }
    .claude-md-section h3 { font-size: 14px; font-weight: 600; color: #1e40af; margin: 0 0 12px 0; }
    .claude-md-actions { margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #dbeafe; }
    .copy-all-btn { background: #2563eb; color: white; border: none; border-radius: 4px; padding: 6px 12px; font-size: 12px; cursor: pointer; font-weight: 500; transition: all 0.2s; }
    .copy-all-btn:hover { background: #1d4ed8; }
    .copy-all-btn.copied { background: #16a34a; }
    .claude-md-item { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 8px; padding: 10px 0; border-bottom: 1px solid #dbeafe; }
    .claude-md-item:last-child { border-bottom: none; }
    .cmd-checkbox { margin-top: 2px; }
    .cmd-code { background: white; padding: 8px 12px; border-radius: 4px; font-size: 12px; color: #1e40af; border: 1px solid #bfdbfe; font-family: monospace; display: block; white-space: pre-wrap; word-break: break-word; flex: 1; }
    .cmd-why { font-size: 12px; color: #64748b; width: 100%; padding-left: 24px; margin-top: 4px; }
    .features-section, .patterns-section { display: flex; flex-direction: column; gap: 12px; margin: 16px 0; }
    .feature-card { background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 16px; }
    .pattern-card { background: #f0f9ff; border: 1px solid #7dd3fc; border-radius: 8px; padding: 16px; }
    .feature-title, .pattern-title { font-weight: 600; font-size: 15px; color: #0f172a; margin-bottom: 6px; }
    .feature-oneliner { font-size: 14px; color: #475569; margin-bottom: 8px; }
    .pattern-summary { font-size: 14px; color: #475569; margin-bottom: 8px; }
    .feature-why, .pattern-detail { font-size: 13px; color: #334155; line-height: 1.5; }
    .feature-examples { margin-top: 12px; }
    .feature-example { padding: 8px 0; border-top: 1px solid #d1fae5; }
    .feature-example:first-child { border-top: none; }
    .example-code-row { display: flex; align-items: flex-start; gap: 8px; }
    .example-code { flex: 1; background: #f1f5f9; padding: 8px 12px; border-radius: 4px; font-family: monospace; font-size: 12px; color: #334155; overflow-x: auto; white-space: pre-wrap; }
    .copyable-prompt-section { margin-top: 12px; padding-top: 12px; border-top: 1px solid #e2e8f0; }
    .copyable-prompt-row { display: flex; align-items: flex-start; gap: 8px; }
    .copyable-prompt { flex: 1; background: #f8fafc; padding: 10px 12px; border-radius: 4px; font-family: monospace; font-size: 12px; color: #334155; border: 1px solid #e2e8f0; white-space: pre-wrap; line-height: 1.5; }
    .pattern-prompt { background: #f8fafc; padding: 12px; border-radius: 6px; margin-top: 12px; border: 1px solid #e2e8f0; }
    .pattern-prompt code { font-family: monospace; font-size: 12px; color: #334155; display: block; white-space: pre-wrap; margin-bottom: 8px; }
    .prompt-label { font-size: 11px; font-weight: 600; text-transform: uppercase; color: #64748b; margin-bottom: 6px; }
    .charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin: 24px 0; }
    .chart-card { background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }
    .chart-title { font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; margin-bottom: 12px; }
    .bar-row { display: flex; align-items: center; margin-bottom: 6px; }
    .bar-label { width: 100px; font-size: 11px; color: #475569; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .bar-track { flex: 1; height: 6px; background: #f1f5f9; border-radius: 3px; margin: 0 8px; }
    .bar-fill { height: 100%; border-radius: 3px; }
    .bar-value { width: 28px; font-size: 11px; font-weight: 500; color: #64748b; text-align: right; }
    .empty { color: #94a3b8; font-size: 13px; }
    .horizon-section { display: flex; flex-direction: column; gap: 16px; }
    .horizon-card { background: linear-gradient(135deg, #faf5ff 0%, #f5f3ff 100%); border: 1px solid #c4b5fd; border-radius: 8px; padding: 16px; }
    .horizon-title { font-weight: 600; font-size: 15px; color: #5b21b6; margin-bottom: 8px; }
    .horizon-possible { font-size: 14px; color: #334155; margin-bottom: 10px; line-height: 1.5; }
    .horizon-tip { font-size: 13px; color: #6b21a8; background: rgba(255,255,255,0.6); padding: 8px 12px; border-radius: 4px; }
    .feedback-header { margin-top: 48px; color: #64748b; font-size: 16px; }
    .feedback-intro { font-size: 13px; color: #94a3b8; margin-bottom: 16px; }
    .feedback-card { background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
    .feedback-card.team-card { background: #eff6ff; border-color: #bfdbfe; }
    .feedback-card.model-card { background: #faf5ff; border-color: #e9d5ff; }
    .feedback-title { font-weight: 600; font-size: 14px; color: #0f172a; margin-bottom: 6px; }
    .feedback-detail { font-size: 13px; color: #475569; line-height: 1.5; }
    .feedback-evidence { font-size: 12px; color: #64748b; margin-top: 8px; }
    .fun-ending { background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border: 1px solid #fbbf24; border-radius: 12px; padding: 24px; margin-top: 40px; text-align: center; }
    .fun-headline { font-size: 18px; font-weight: 600; color: #78350f; margin-bottom: 8px; }
    .fun-detail { font-size: 14px; color: #92400e; }
    .collapsible-section { margin-top: 16px; }
    .collapsible-header { display: flex; align-items: center; gap: 8px; cursor: pointer; padding: 12px 0; border-bottom: 1px solid #e2e8f0; }
    .collapsible-header h3 { margin: 0; font-size: 14px; font-weight: 600; color: #475569; }
    .collapsible-arrow { font-size: 12px; color: #94a3b8; transition: transform 0.2s; }
    .collapsible-content { display: none; padding-top: 16px; }
    .collapsible-content.open { display: block; }
    .collapsible-header.open .collapsible-arrow { transform: rotate(90deg); }
    .copy-btn { background: #e2e8f0; border: none; border-radius: 4px; padding: 4px 8px; font-size: 11px; cursor: pointer; color: #475569; flex-shrink: 0; }
    .copy-btn:hover { background: #cbd5e1; }
    @media (max-width: 640px) { .charts-row { grid-template-columns: 1fr; } .stats-row { justify-content: center; } }
"""

_JS = """
    function toggleCollapsible(header) {
      header.classList.toggle('open');
      const content = header.nextElementSibling;
      content.classList.toggle('open');
    }
    function copyText(btn) {
      const code = btn.previousElementSibling;
      navigator.clipboard.writeText(code.textContent).then(() => {
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = 'Copy'; }, 2000);
      });
    }
    function copyCmdItem(idx) {
      const checkbox = document.getElementById('cmd-' + idx);
      if (checkbox) {
        const text = checkbox.dataset.text;
        navigator.clipboard.writeText(text).then(() => {
          const btn = checkbox.nextElementSibling.querySelector('.copy-btn');
          if (btn) { btn.textContent = 'Copied!'; setTimeout(() => { btn.textContent = 'Copy'; }, 2000); }
        });
      }
    }
    function copyAllCheckedClaudeMd() {
      const checkboxes = document.querySelectorAll('.cmd-checkbox:checked');
      const texts = [];
      checkboxes.forEach(cb => { if (cb.dataset.text) { texts.push(cb.dataset.text); } });
      const combined = texts.join('\\n');
      const btn = document.querySelector('.copy-all-btn');
      if (btn) {
        navigator.clipboard.writeText(combined).then(() => {
          btn.textContent = 'Copied ' + texts.length + ' items!';
          btn.classList.add('copied');
          setTimeout(() => { btn.textContent = 'Copy All Checked'; btn.classList.remove('copied'); }, 2000);
        });
      }
    }
    const rawHourCounts = HOUR_COUNTS_JSON;
    function updateHourHistogram(offsetFromPT) {
      const periods = [
        { label: "Morning (6-12)", range: [6,7,8,9,10,11] },
        { label: "Afternoon (12-18)", range: [12,13,14,15,16,17] },
        { label: "Evening (18-24)", range: [18,19,20,21,22,23] },
        { label: "Night (0-6)", range: [0,1,2,3,4,5] }
      ];
      const adjustedCounts = {};
      for (const [hour, count] of Object.entries(rawHourCounts)) {
        const newHour = (parseInt(hour) + offsetFromPT + 24) % 24;
        adjustedCounts[newHour] = (adjustedCounts[newHour] || 0) + count;
      }
      const periodCounts = periods.map(p => ({
        label: p.label,
        count: p.range.reduce((sum, h) => sum + (adjustedCounts[h] || 0), 0)
      }));
      const maxCount = Math.max(...periodCounts.map(p => p.count)) || 1;
      const container = document.getElementById('hour-histogram');
      container.textContent = '';
      periodCounts.forEach(p => {
        const row = document.createElement('div'); row.className = 'bar-row';
        const label = document.createElement('div'); label.className = 'bar-label'; label.textContent = p.label;
        const track = document.createElement('div'); track.className = 'bar-track';
        const fill = document.createElement('div'); fill.className = 'bar-fill';
        fill.style.width = (p.count / maxCount) * 100 + '%'; fill.style.background = '#8b5cf6';
        track.appendChild(fill);
        const value = document.createElement('div'); value.className = 'bar-value'; value.textContent = p.count;
        row.appendChild(label); row.appendChild(track); row.appendChild(value);
        container.appendChild(row);
      });
    }
    document.getElementById('timezone-select').addEventListener('change', function() {
      const customInput = document.getElementById('custom-offset');
      if (this.value === 'custom') {
        customInput.style.display = 'inline-block';
        customInput.focus();
      } else {
        customInput.style.display = 'none';
        updateHourHistogram(parseInt(this.value));
      }
    });
    document.getElementById('custom-offset').addEventListener('change', function() {
      const offset = parseInt(this.value) + 8;
      updateHourHistogram(offset);
    });
"""


def render_html_report(data: AggregatedData, insights: dict[str, Any]) -> str:
    """Render the full HTML insights report."""

    def md_to_html(text: str) -> str:
        if not text:
            return ""
        parts: list[str] = []
        for para in text.split("\n\n"):
            h = _escape_html(para)
            h = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", h)
            h = re.sub(r"^- ", "• ", h, flags=re.MULTILINE)
            h = h.replace("\n", "<br>")
            parts.append(f"<p>{h}</p>")
        return "\n".join(parts)

    # ---- At a Glance ----
    ag = insights.get("at_a_glance") or {}
    at_a_glance_html = ""
    if ag:
        sections_html = ""
        if ag.get("whats_working"):
            sections_html += (
                f'<div class="glance-section"><strong>What\'s working:</strong> '
                f'{_escape_html_with_bold(ag["whats_working"])} '
                f'<a href="#section-wins" class="see-more">Impressive Things You Did \u2192</a></div>'
            )
        if ag.get("whats_hindering"):
            sections_html += (
                f'<div class="glance-section"><strong>What\'s hindering you:</strong> '
                f'{_escape_html_with_bold(ag["whats_hindering"])} '
                f'<a href="#section-friction" class="see-more">Where Things Go Wrong \u2192</a></div>'
            )
        if ag.get("quick_wins"):
            sections_html += (
                f'<div class="glance-section"><strong>Quick wins to try:</strong> '
                f'{_escape_html_with_bold(ag["quick_wins"])} '
                f'<a href="#section-features" class="see-more">Features to Try \u2192</a></div>'
            )
        if ag.get("ambitious_workflows"):
            sections_html += (
                f'<div class="glance-section"><strong>Ambitious workflows:</strong> '
                f'{_escape_html_with_bold(ag["ambitious_workflows"])} '
                f'<a href="#section-horizon" class="see-more">On the Horizon \u2192</a></div>'
            )
        at_a_glance_html = (
            f'<div class="at-a-glance">'
            f'<div class="glance-title">At a Glance</div>'
            f'<div class="glance-sections">{sections_html}</div>'
            f'</div>'
        )

    # ---- Project Areas ----
    project_areas = (insights.get("project_areas") or {}).get("areas") or []
    project_areas_html = ""
    if project_areas:
        items = "".join(
            f'<div class="project-area">'
            f'<div class="area-header">'
            f'<span class="area-name">{_escape_html(a.get("name",""))}</span>'
            f'<span class="area-count">~{a.get("session_count",0)} sessions</span>'
            f'</div>'
            f'<div class="area-desc">{_escape_html(a.get("description",""))}</div>'
            f'</div>'
            for a in project_areas
        )
        project_areas_html = f'<h2 id="section-work">What You Work On</h2><div class="project-areas">{items}</div>'

    # ---- Interaction Style ----
    is_data = insights.get("interaction_style") or {}
    interaction_html = ""
    if is_data.get("narrative"):
        key_p = (
            f'<div class="key-insight"><strong>Key pattern:</strong> {_escape_html(is_data["key_pattern"])}</div>'
            if is_data.get("key_pattern")
            else ""
        )
        interaction_html = (
            f'<h2 id="section-usage">How You Use Claude Code</h2>'
            f'<div class="narrative">{md_to_html(is_data["narrative"])}{key_p}</div>'
        )

    # ---- What Works ----
    ww = insights.get("what_works") or {}
    what_works_html = ""
    if ww.get("impressive_workflows"):
        items = "".join(
            f'<div class="big-win">'
            f'<div class="big-win-title">{_escape_html(w.get("title",""))}</div>'
            f'<div class="big-win-desc">{_escape_html(w.get("description",""))}</div>'
            f'</div>'
            for w in ww["impressive_workflows"]
        )
        intro = f'<p class="section-intro">{_escape_html(ww["intro"])}</p>' if ww.get("intro") else ""
        what_works_html = f'<h2 id="section-wins">Impressive Things You Did</h2>{intro}<div class="big-wins">{items}</div>'

    # ---- Friction ----
    fa = insights.get("friction_analysis") or {}
    friction_html = ""
    if fa.get("categories"):
        intro = f'<p class="section-intro">{_escape_html(fa["intro"])}</p>' if fa.get("intro") else ""
        items = "".join(
            f'<div class="friction-category">'
            f'<div class="friction-title">{_escape_html(c.get("category",""))}</div>'
            f'<div class="friction-desc">{_escape_html(c.get("description",""))}</div>'
            + (
                f'<ul class="friction-examples">{"".join("<li>"+_escape_html(ex)+"</li>" for ex in (c.get("examples") or []))}</ul>'
                if c.get("examples")
                else ""
            )
            + "</div>"
            for c in fa["categories"]
        )
        friction_html = f'<h2 id="section-friction">Where Things Go Wrong</h2>{intro}<div class="friction-categories">{items}</div>'

    # ---- Suggestions ----
    sug = insights.get("suggestions") or {}
    suggestions_html = ""

    # CLAUDE.md additions section
    if sug.get("claude_md_additions"):
        cmd_items = "".join(
            f'<div class="claude-md-item">'
            f'<input type="checkbox" id="cmd-{i}" class="cmd-checkbox" checked '
            f'data-text="{_escape_html((add.get("prompt_scaffold") or add.get("where") or "Add to CLAUDE.md"))}\\n\\n{_escape_html(add.get("addition",""))}">'
            f'<label for="cmd-{i}">'
            f'<code class="cmd-code">{_escape_html(add.get("addition",""))}</code>'
            f'<button class="copy-btn" onclick="copyCmdItem({i})">Copy</button>'
            f'</label>'
            f'<div class="cmd-why">{_escape_html(add.get("why",""))}</div>'
            f'</div>'
            for i, add in enumerate(sug["claude_md_additions"])
        )
        suggestions_html += (
            f'<h2 id="section-features">Existing CC Features to Try</h2>'
            f'<div class="claude-md-section">'
            f'<h3>Suggested CLAUDE.md Additions</h3>'
            f'<p style="font-size: 12px; color: #64748b; margin-bottom: 12px;">Just copy this into Claude Code to add it to your CLAUDE.md.</p>'
            f'<div class="claude-md-actions">'
            f'<button class="copy-all-btn" onclick="copyAllCheckedClaudeMd()">Copy All Checked</button>'
            f'</div>'
            f'{cmd_items}'
            f'</div>'
        )

    if sug.get("features_to_try"):
        feature_items = "".join(
            f'<div class="feature-card">'
            f'<div class="feature-title">{_escape_html(f.get("feature",""))}</div>'
            f'<div class="feature-oneliner">{_escape_html(f.get("one_liner",""))}</div>'
            f'<div class="feature-why"><strong>Why for you:</strong> {_escape_html(f.get("why_for_you",""))}</div>'
            + (
                f'<div class="feature-examples"><div class="feature-example"><div class="example-code-row">'
                f'<code class="example-code">{_escape_html(f["example_code"])}</code>'
                f'<button class="copy-btn" onclick="copyText(this)">Copy</button>'
                f'</div></div></div>'
                if f.get("example_code")
                else ""
            )
            + "</div>"
            for f in sug["features_to_try"]
        )
        intro_text = '<p style="font-size: 13px; color: #64748b; margin-bottom: 12px;">Just copy this into Claude Code and it\'ll set it up for you.</p>'
        if not sug.get("claude_md_additions"):
            suggestions_html += f'<h2 id="section-features">Features to Try</h2>'
        suggestions_html += f'{intro_text}<div class="features-section">{feature_items}</div>'

    if sug.get("usage_patterns"):
        pattern_items = "".join(
            f'<div class="pattern-card">'
            f'<div class="pattern-title">{_escape_html(p.get("title",""))}</div>'
            f'<div class="pattern-summary">{_escape_html(p.get("suggestion",""))}</div>'
            + (f'<div class="pattern-detail">{_escape_html(p["detail"])}</div>' if p.get("detail") else "")
            + (
                f'<div class="pattern-prompt">'
                f'<div class="prompt-label">Paste into Claude Code:</div>'
                f'<div class="copyable-prompt-row">'
                f'<code class="copyable-prompt">{_escape_html(p["copyable_prompt"])}</code>'
                f'<button class="copy-btn" onclick="copyText(this)">Copy</button>'
                f'</div></div>'
                if p.get("copyable_prompt")
                else ""
            )
            + "</div>"
            for p in sug["usage_patterns"]
        )
        suggestions_html += (
            f'<h2 id="section-patterns">New Ways to Use Claude Code</h2>'
            f'<p style="font-size: 13px; color: #64748b; margin-bottom: 12px;">Just copy this into Claude Code and it\'ll walk you through it.</p>'
            f'<div class="patterns-section">{pattern_items}</div>'
        )

    # ---- On the Horizon ----
    hz = insights.get("on_the_horizon") or {}
    horizon_html = ""
    if hz.get("opportunities"):
        intro = f'<p class="section-intro">{_escape_html(hz["intro"])}</p>' if hz.get("intro") else ""
        items = "".join(
            f'<div class="horizon-card">'
            f'<div class="horizon-title">{_escape_html(o.get("title",""))}</div>'
            f'<div class="horizon-possible">{_escape_html(o.get("whats_possible",""))}</div>'
            + (
                f'<div class="horizon-tip"><strong>Getting started:</strong> {_escape_html(o["how_to_try"])}</div>'
                if o.get("how_to_try") else ""
            )
            + (
                f'<div class="pattern-prompt"><div class="prompt-label">Paste into Claude Code:</div>'
                f'<code>{_escape_html(o["copyable_prompt"])}</code>'
                f'<button class="copy-btn" onclick="copyText(this)">Copy</button></div>'
                if o.get("copyable_prompt") else ""
            )
            + "</div>"
            for o in hz["opportunities"]
        )
        horizon_html = f'<h2 id="section-horizon">On the Horizon</h2>{intro}<div class="horizon-section">{items}</div>'

    # ---- Team Feedback (collapsible) ----
    cc_improvements = list((insights.get("cc_team_improvements") or {}).get("improvements") or [])
    model_improvements = list((insights.get("model_behavior_improvements") or {}).get("improvements") or [])
    team_feedback_html = ""
    if cc_improvements or model_improvements:
        cc_html = ""
        if cc_improvements:
            cards = "".join(
                f'<div class="feedback-card team-card">'
                f'<div class="feedback-title">{_escape_html(imp.get("title",""))}</div>'
                f'<div class="feedback-detail">{_escape_html(imp.get("detail",""))}</div>'
                + (f'<div class="feedback-evidence"><em>Evidence:</em> {_escape_html(imp["evidence"])}</div>' if imp.get("evidence") else "")
                + "</div>"
                for imp in cc_improvements
            )
            cc_html = (
                f'<div class="collapsible-section">'
                f'<div class="collapsible-header" onclick="toggleCollapsible(this)">'
                f'<span class="collapsible-arrow">\u25b6</span>'
                f'<h3>Product Improvements for CC Team</h3>'
                f'</div>'
                f'<div class="collapsible-content">{cards}</div>'
                f'</div>'
            )
        model_html = ""
        if model_improvements:
            cards = "".join(
                f'<div class="feedback-card model-card">'
                f'<div class="feedback-title">{_escape_html(imp.get("title",""))}</div>'
                f'<div class="feedback-detail">{_escape_html(imp.get("detail",""))}</div>'
                + (f'<div class="feedback-evidence"><em>Evidence:</em> {_escape_html(imp["evidence"])}</div>' if imp.get("evidence") else "")
                + "</div>"
                for imp in model_improvements
            )
            model_html = (
                f'<div class="collapsible-section">'
                f'<div class="collapsible-header" onclick="toggleCollapsible(this)">'
                f'<span class="collapsible-arrow">\u25b6</span>'
                f'<h3>Model Behavior Improvements</h3>'
                f'</div>'
                f'<div class="collapsible-content">{cards}</div>'
                f'</div>'
            )
        team_feedback_html = (
            f'<h2 id="section-feedback" class="feedback-header">Closing the Loop: Feedback for Other Teams</h2>'
            f'<p class="feedback-intro">Suggestions for the CC product and model teams based on your usage patterns. Click to expand.</p>'
            + cc_html + model_html
        )

    # ---- Fun Ending ----
    fe = insights.get("fun_ending") or {}
    fun_html = ""
    if fe.get("headline"):
        fun_html = (
            f'<div class="fun-ending"><div class="fun-headline">&quot;{_escape_html(fe["headline"])}&quot;</div>'
            + (f'<div class="fun-detail">{_escape_html(fe["detail"])}</div>' if fe.get("detail") else "")
            + "</div>"
        )

    # ---- Multi-Clauding ----
    multi = data.multi_clauding
    if multi.overlap_events == 0:
        multi_html = (
            '<p style="font-size: 14px; color: #64748b; padding: 8px 0;">'
            'No parallel session usage detected. You typically work with one Claude Code session at a time.'
            '</p>'
        )
    else:
        pct = round(100 * multi.user_messages_during / data.total_messages) if data.total_messages else 0
        multi_html = (
            f'<div style="display: flex; gap: 24px; margin: 12px 0;">'
            f'<div style="text-align: center;"><div style="font-size: 24px; font-weight: 700; color: #7c3aed;">{multi.overlap_events}</div>'
            f'<div style="font-size: 11px; color: #64748b; text-transform: uppercase;">Overlap Events</div></div>'
            f'<div style="text-align: center;"><div style="font-size: 24px; font-weight: 700; color: #7c3aed;">{multi.sessions_involved}</div>'
            f'<div style="font-size: 11px; color: #64748b; text-transform: uppercase;">Sessions Involved</div></div>'
            f'<div style="text-align: center;"><div style="font-size: 24px; font-weight: 700; color: #7c3aed;">{pct}%</div>'
            f'<div style="font-size: 11px; color: #64748b; text-transform: uppercase;">Of Messages</div></div>'
            f'</div>'
            f'<p style="font-size: 13px; color: #475569; margin-top: 12px;">'
            f'You run multiple Claude Code sessions simultaneously. Multi-clauding is detected when sessions '
            f'overlap in time, suggesting parallel workflows.'
            f'</p>'
        )

    scanned_info = ""
    if data.total_sessions_scanned and data.total_sessions_scanned > data.total_sessions:
        scanned_info = f" ({data.total_sessions_scanned:,} total)"

    hour_counts_json = _get_hour_counts_json(data.message_hours)
    js_final = _JS.replace("HOUR_COUNTS_JSON", hour_counts_json)

    tool_errors_html = (
        _generate_bar_chart(data.tool_error_categories, "#dc2626")
        if data.tool_error_categories
        else '<p class="empty">No tool errors</p>'
    )

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Claude Code Insights</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>{_CSS}</style>
</head>
<body>
  <div class="container">
    <h1>Claude Code Insights</h1>
    <p class="subtitle">{data.total_messages:,} messages across {data.total_sessions} sessions{scanned_info} | {data.date_range.get("start","")} to {data.date_range.get("end","")}</p>

    {at_a_glance_html}

    <nav class="nav-toc">
      <a href="#section-work">What You Work On</a>
      <a href="#section-usage">How You Use CC</a>
      <a href="#section-wins">Impressive Things</a>
      <a href="#section-friction">Where Things Go Wrong</a>
      <a href="#section-features">Features to Try</a>
      <a href="#section-patterns">New Usage Patterns</a>
      <a href="#section-horizon">On the Horizon</a>
      <a href="#section-feedback">Team Feedback</a>
    </nav>

    <div class="stats-row">
      <div class="stat"><div class="stat-value">{data.total_messages:,}</div><div class="stat-label">Messages</div></div>
      <div class="stat"><div class="stat-value">+{data.total_lines_added:,}/-{data.total_lines_removed:,}</div><div class="stat-label">Lines</div></div>
      <div class="stat"><div class="stat-value">{data.total_files_modified}</div><div class="stat-label">Files</div></div>
      <div class="stat"><div class="stat-value">{data.days_active}</div><div class="stat-label">Days</div></div>
      <div class="stat"><div class="stat-value">{data.messages_per_day}</div><div class="stat-label">Msgs/Day</div></div>
    </div>

    {project_areas_html}

    <div class="charts-row">
      <div class="chart-card"><div class="chart-title">What You Wanted</div>{_generate_bar_chart(data.goal_categories,"#2563eb")}</div>
      <div class="chart-card"><div class="chart-title">Top Tools Used</div>{_generate_bar_chart(data.tool_counts,"#0891b2")}</div>
    </div>

    <div class="charts-row">
      <div class="chart-card"><div class="chart-title">Languages</div>{_generate_bar_chart(data.languages,"#10b981")}</div>
      <div class="chart-card"><div class="chart-title">Session Types</div>{_generate_bar_chart(data.session_types,"#8b5cf6")}</div>
    </div>

    {interaction_html}

    <div class="chart-card" style="margin: 24px 0;">
      <div class="chart-title">User Response Time Distribution</div>
      {_generate_response_time_histogram(data.user_response_times)}
      <div style="font-size: 12px; color: #64748b; margin-top: 8px;">
        Median: {data.median_response_time:.1f}s &bull; Average: {data.avg_response_time:.1f}s
      </div>
    </div>

    <div class="chart-card" style="margin: 24px 0;">
      <div class="chart-title">Multi-Clauding (Parallel Sessions)</div>
      {multi_html}
    </div>

    <div class="charts-row">
      <div class="chart-card">
        <div class="chart-title" style="display: flex; align-items: center; gap: 12px;">
          User Messages by Time of Day
          <select id="timezone-select" style="font-size: 12px; padding: 4px 8px; border-radius: 4px; border: 1px solid #e2e8f0;">
            <option value="0">PT (UTC-8)</option>
            <option value="3">ET (UTC-5)</option>
            <option value="8">London (UTC)</option>
            <option value="9">CET (UTC+1)</option>
            <option value="17">Tokyo (UTC+9)</option>
            <option value="custom">Custom offset...</option>
          </select>
          <input type="number" id="custom-offset" placeholder="UTC offset" style="display: none; width: 80px; font-size: 12px; padding: 4px; border-radius: 4px; border: 1px solid #e2e8f0;">
        </div>
        {_generate_time_of_day_chart(data.message_hours)}
      </div>
      <div class="chart-card">
        <div class="chart-title">Tool Errors Encountered</div>
        {tool_errors_html}
      </div>
    </div>

    {what_works_html}

    <div class="charts-row">
      <div class="chart-card"><div class="chart-title">What Helped Most (Claude&#39;s Capabilities)</div>{_generate_bar_chart(data.success,"#16a34a")}</div>
      <div class="chart-card"><div class="chart-title">Outcomes</div>{_generate_bar_chart(data.outcomes,"#8b5cf6",6,OUTCOME_ORDER)}</div>
    </div>

    {friction_html}

    <div class="charts-row">
      <div class="chart-card"><div class="chart-title">Primary Friction Types</div>{_generate_bar_chart(data.friction,"#dc2626")}</div>
      <div class="chart-card"><div class="chart-title">Inferred Satisfaction (model-estimated)</div>{_generate_bar_chart(data.satisfaction,"#eab308",6,SATISFACTION_ORDER)}</div>
    </div>

    {suggestions_html}
    {horizon_html}
    {fun_html}
    {team_feedback_html}
  </div>
  <script>{js_final}</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Build export data
# ---------------------------------------------------------------------------

def build_export_data(
    data: AggregatedData,
    insights: dict[str, Any],
    facets: dict[str, SessionFacets],
    remote_stats: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build structured export data for external consumption (e.g. S3 upload)."""
    import os as _os

    remote_hosts_collected: Optional[list[str]] = None
    if remote_stats:
        remote_hosts_collected = [
            h["name"] for h in (remote_stats.get("hosts") or []) if h.get("sessionCount", 0) > 0
        ]

    facets_summary: dict[str, Any] = {
        "total": len(facets),
        "goal_categories": {},
        "outcomes": {},
        "satisfaction": {},
        "friction": {},
    }
    for f in facets.values():
        for cat, cnt in f.goal_categories.items():
            if cnt > 0:
                facets_summary["goal_categories"][cat] = facets_summary["goal_categories"].get(cat, 0) + cnt
        facets_summary["outcomes"][f.outcome] = facets_summary["outcomes"].get(f.outcome, 0) + 1
        for level, cnt in f.user_satisfaction_counts.items():
            if cnt > 0:
                facets_summary["satisfaction"][level] = facets_summary["satisfaction"].get(level, 0) + cnt
        for ftype, cnt in f.friction_counts.items():
            if cnt > 0:
                facets_summary["friction"][ftype] = facets_summary["friction"].get(ftype, 0) + cnt

    import dataclasses

    metadata: dict[str, Any] = {
        "username": _os.environ.get("SAFEUSER") or _os.environ.get("USER") or "unknown",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "claude_code_version": "unknown",
        "date_range": data.date_range,
        "session_count": data.total_sessions,
    }
    if remote_hosts_collected:
        metadata["remote_hosts_collected"] = remote_hosts_collected

    return {
        "metadata": metadata,
        "aggregated_data": dataclasses.asdict(data),
        "insights": insights,
        "facets_summary": facets_summary,
    }


# ---------------------------------------------------------------------------
# Main entry point: generate_usage_report (full two-phase scan)
# ---------------------------------------------------------------------------

async def generate_usage_report(
    collect_remote: bool = False,
    projects_dir: Optional[Path] = None,
    max_sessions: int = 200,
) -> dict[str, Any]:
    """
    Main entry point: full two-phase scan → extract facets → aggregate → generate HTML.

    Phase 1: Load SessionMeta from cache or JSONL files.
    Phase 2: Extract facets from Claude for sessions without cached facets.

    Returns a dict with keys: insights, html_path, data, facets.
    """
    if projects_dir is None:
        projects_dir = _get_projects_dir()

    # ---- Phase 1: Collect session files ----
    session_files: list[tuple[float, Path]] = []
    try:
        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            for jsonl_file in project_dir.glob("*.jsonl"):
                try:
                    mtime = jsonl_file.stat().st_mtime
                    session_files.append((mtime, jsonl_file))
                except OSError:
                    pass
    except OSError:
        pass

    session_files.sort(key=lambda x: x[0], reverse=True)
    total_sessions_scanned = len(session_files)

    # ---- Phase 2: Load SessionMeta — use cache where available ----
    META_BATCH_SIZE = 50
    all_metas: list[SessionMeta] = []
    uncached_paths: list[Path] = []

    for i in range(0, len(session_files), META_BATCH_SIZE):
        batch = session_files[i : i + META_BATCH_SIZE]
        results = await asyncio.gather(
            *[_load_cached_session_meta(_get_session_id_from_path(p)) for _, p in batch]
        )
        for (_, path), cached in zip(batch, results):
            if cached:
                all_metas.append(cached)
            elif len(uncached_paths) < max_sessions:
                uncached_paths.append(path)

    # ---- Load uncached sessions from JSONL ----
    logs_for_facets: dict[str, list[dict[str, Any]]] = {}  # session_id -> messages
    LOAD_BATCH_SIZE = 10
    metas_to_save: list[SessionMeta] = []

    for i in range(0, len(uncached_paths), LOAD_BATCH_SIZE):
        batch = uncached_paths[i : i + LOAD_BATCH_SIZE]
        for path in batch:
            raw_messages = _read_jsonl_file(path)
            if not raw_messages:
                continue
            session_id = _get_session_id_from_path(path)
            if _is_meta_session(raw_messages):
                continue

            project_path = str(path.parent.name)
            first_prompt, summary = _extract_first_prompt_and_summary(raw_messages)

            created: Optional[datetime] = None
            modified: Optional[datetime] = None
            for msg in raw_messages:
                ts_str = msg.get("timestamp")
                if ts_str:
                    dt = _parse_timestamp(ts_str)
                    if dt:
                        if created is None:
                            created = dt
                        modified = dt
            if created is None:
                try:
                    stat = path.stat()
                    created = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc)
                    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                except OSError:
                    pass

            meta = extract_session_meta(
                session_id=session_id,
                project_path=project_path,
                messages=raw_messages,
                created=created,
                modified=modified,
                first_prompt=first_prompt,
                summary=summary,
            )
            all_metas.append(meta)
            metas_to_save.append(meta)
            logs_for_facets[session_id] = raw_messages

        # Yield control between batches
        await asyncio.sleep(0)

    # Save new metas in parallel
    await asyncio.gather(*[_save_session_meta(m) for m in metas_to_save])

    # ---- Deduplicate session branches ----
    best_by_session: dict[str, SessionMeta] = {}
    for meta in all_metas:
        existing = best_by_session.get(meta.session_id)
        if (
            not existing
            or meta.user_message_count > existing.user_message_count
            or (
                meta.user_message_count == existing.user_message_count
                and meta.duration_minutes > existing.duration_minutes
            )
        ):
            best_by_session[meta.session_id] = meta

    # Clean up logs for non-kept sessions
    kept_ids = set(best_by_session.keys())
    logs_for_facets = {sid: msgs for sid, msgs in logs_for_facets.items() if sid in kept_ids}

    all_metas = sorted(best_by_session.values(), key=lambda m: m.start_time, reverse=True)

    # ---- Filter to substantive sessions ----
    substantive_metas = [
        m for m in all_metas
        if m.user_message_count >= 2 and m.duration_minutes >= 1
    ]

    # ---- Phase 3: Facet extraction ----
    facets: dict[str, SessionFacets] = {}
    to_extract: list[tuple[str, list[dict[str, Any]]]] = []
    MAX_FACET_EXTRACTIONS = 50

    # Load cached facets in parallel
    cached_facet_results = await asyncio.gather(
        *[_load_cached_facets(m.session_id) for m in substantive_metas]
    )
    for meta, cached in zip(substantive_metas, cached_facet_results):
        if cached:
            facets[meta.session_id] = cached
        else:
            msgs = logs_for_facets.get(meta.session_id)
            if msgs and len(to_extract) < MAX_FACET_EXTRACTIONS:
                to_extract.append((meta.session_id, msgs))

    # Extract facets for sessions needing it
    CONCURRENCY = 50
    facets_to_save: list[SessionFacets] = []
    for i in range(0, len(to_extract), CONCURRENCY):
        batch = to_extract[i : i + CONCURRENCY]
        results = await asyncio.gather(
            *[
                extract_facets_with_llm(
                    session_id=sid,
                    start_time=best_by_session[sid].start_time if sid in best_by_session else "",
                    project_path=best_by_session[sid].project_path if sid in best_by_session else "",
                    duration_minutes=best_by_session[sid].duration_minutes if sid in best_by_session else 0,
                    messages=msgs,
                )
                for sid, msgs in batch
            ]
        )
        for (sid, _), new_facets in zip(batch, results):
            if new_facets:
                facets[sid] = new_facets
                facets_to_save.append(new_facets)

    await asyncio.gather(*[_save_facets(f) for f in facets_to_save])

    # ---- Filter warmup/minimal sessions ----
    def _is_minimal(session_id: str) -> bool:
        sf = facets.get(session_id)
        if not sf:
            return False
        cats = [k for k, v in sf.goal_categories.items() if v > 0]
        return cats == ["warmup_minimal"]

    final_sessions = [s for s in substantive_metas if not _is_minimal(s.session_id)]
    final_facets = {sid: f for sid, f in facets.items() if not _is_minimal(sid)}

    # ---- Aggregate ----
    data = aggregate_sessions(final_sessions, final_facets)
    data.total_sessions_scanned = total_sessions_scanned

    # ---- Generate AI insights in parallel ----
    insights_data = await generate_insights_report(data, final_facets)

    # ---- Render HTML ----
    html_report = render_html_report(data, insights_data)

    # ---- Save report ----
    data_dir = _get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    html_path = data_dir / "report.html"

    if HAS_AIOFILES:
        import aiofiles  # type: ignore
        async with aiofiles.open(html_path, "w", encoding="utf-8") as fh:
            await fh.write(html_report)
    else:
        html_path.write_text(html_report, encoding="utf-8")

    return {
        "insights": insights_data,
        "html_path": str(html_path),
        "data": data,
        "facets": final_facets,
    }


# Backward-compatible alias
async def get_insights(collect_remote: bool = False) -> dict[str, Any]:
    """Backward-compatible alias for generate_usage_report."""
    return await generate_usage_report(collect_remote=collect_remote)


# ---------------------------------------------------------------------------
# Command prompt builder
# ---------------------------------------------------------------------------

async def get_prompt_for_command(args: Optional[list[str]] = None) -> list[dict[str, Any]]:
    """
    Build the prompt returned to the Claude Code agent after /insights.

    Runs generate_usage_report, renders markdown summary, returns prompt list.
    """
    import json as _json

    collect_remote = bool(args and "--homespaces" in args)

    result = await generate_usage_report(collect_remote=collect_remote)
    insights_data: dict[str, Any] = result["insights"]
    html_path: str = result["html_path"]
    data: AggregatedData = result["data"]

    report_url = f"file://{html_path}"

    # Build stats line
    scanned = data.total_sessions_scanned
    if scanned and scanned > data.total_sessions:
        session_label = f"{scanned:,} sessions total \u00b7 {data.total_sessions} analyzed"
    else:
        session_label = f"{data.total_sessions} sessions"

    stats = " \u00b7 ".join([
        session_label,
        f"{data.total_messages:,} messages",
        f"{round(data.total_duration_hours)}h",
        f"{data.git_commits} commits",
    ])

    # Build At a Glance markdown
    at_a_glance = insights_data.get("at_a_glance") or {}
    if at_a_glance:
        parts = ["## At a Glance\n"]
        if at_a_glance.get("whats_working"):
            parts.append(f"**What's working:** {at_a_glance['whats_working']} See _Impressive Things You Did_.\n")
        if at_a_glance.get("whats_hindering"):
            parts.append(f"**What's hindering you:** {at_a_glance['whats_hindering']} See _Where Things Go Wrong_.\n")
        if at_a_glance.get("quick_wins"):
            parts.append(f"**Quick wins to try:** {at_a_glance['quick_wins']} See _Features to Try_.\n")
        if at_a_glance.get("ambitious_workflows"):
            parts.append(f"**Ambitious workflows:** {at_a_glance['ambitious_workflows']} See _On the Horizon_.\n")
        summary_text = "\n".join(parts)
    else:
        summary_text = "_No insights generated_"

    header = (
        f"# Claude Code Insights\n\n"
        f"{stats}\n"
        f"{data.date_range.get('start','')} to {data.date_range.get('end','')}\n\n"
    )
    user_summary = f"{header}{summary_text}\n\nYour full insights report is ready: {report_url}"

    return [
        {
            "type": "text",
            "text": (
                f"The user just ran /insights to generate a usage report analyzing their Claude Code sessions.\n\n"
                f"Here is the full insights data:\n{_json.dumps(insights_data, indent=2, default=str)}\n\n"
                f"Report URL: {report_url}\n"
                f"HTML file: {html_path}\n"
                f"Facets directory: {str(_get_facets_dir())}\n\n"
                f"Here is what the user sees:\n{user_summary}\n\n"
                f"Now output the following message exactly:\n\n"
                f"<message>\n"
                f"Your insights report is ready:\n"
                f"{report_url}\n\n"
                f"Want to dig into any section or try one of the suggestions?\n"
                f"</message>"
            ),
        }
    ]


# ---------------------------------------------------------------------------
# Command registration
# ---------------------------------------------------------------------------

# Command descriptor (matches the TypeScript Command interface)
Command: dict[str, Any] = {
    "type": "prompt",
    "name": "insights",
    "description": "Generate a report analyzing your Claude Code sessions",
    "progress_message": "analyzing your sessions",
    "source": "builtin",
    "get_prompt_for_command": get_prompt_for_command,
}

default = Command
