"""
Ported from: commands/branch/branch.ts (296 lines)

Creates a fork of the current conversation by copying from the transcript
file. Preserves all original metadata (timestamps, gitBranch, etc.) while
updating sessionId and adding forkedFrom traceability.

React/JSX UI components are omitted — only the data layer is ported.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Helper: derive first user prompt as a title baseline
# ---------------------------------------------------------------------------

def derive_first_prompt(first_user_message: Optional[Dict[str, Any]]) -> str:
    """
    Derive a single-line title base from the first user message.
    Collapses whitespace so multiline content doesn't break the saved title.
    Mirrors deriveFirstPrompt() from the TS source.
    """
    if not first_user_message:
        return "Branched conversation"
    content = first_user_message.get("message", {}).get("content")
    if not content:
        return "Branched conversation"
    if isinstance(content, str):
        raw = content
    elif isinstance(content, list):
        raw = next(
            (block.get("text", "") for block in content if block.get("type") == "text"),
            "",
        )
    else:
        return "Branched conversation"
    title = re.sub(r"\s+", " ", raw).strip()[:100]
    return title or "Branched conversation"


# ---------------------------------------------------------------------------
# Helper: session storage utilities (stubs / thin wrappers)
# ---------------------------------------------------------------------------

def _get_original_cwd() -> str:
    try:
        from claude_code.bootstrap.state import get_original_cwd
        return get_original_cwd()
    except ImportError:
        return os.getcwd()


def _get_session_id() -> str:
    try:
        from claude_code.bootstrap.state import get_session_id
        return get_session_id()
    except ImportError:
        return str(uuid.uuid4())


def _get_project_dir(cwd: str) -> str:
    try:
        from claude_code.utils.session_storage import get_project_dir
        return get_project_dir(cwd)
    except ImportError:
        return os.path.join(os.path.expanduser("~"), ".claude", "projects")


def _get_transcript_path() -> str:
    try:
        from claude_code.utils.session_storage import get_transcript_path
        return get_transcript_path()
    except ImportError:
        return os.path.join(_get_project_dir(_get_original_cwd()), f"{_get_session_id()}.jsonl")


def _get_transcript_path_for_session(session_id: str) -> str:
    try:
        from claude_code.utils.session_storage import get_transcript_path_for_session
        return get_transcript_path_for_session(session_id)
    except ImportError:
        return os.path.join(_get_project_dir(_get_original_cwd()), f"{session_id}.jsonl")


def _is_transcript_message(entry: Dict[str, Any]) -> bool:
    try:
        from claude_code.utils.session_storage import is_transcript_message
        return is_transcript_message(entry)
    except ImportError:
        return entry.get("type") in ("user", "assistant", "progress")


def _parse_jsonl(content: bytes) -> List[Dict[str, Any]]:
    entries = []
    for line in content.decode("utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


async def _search_sessions_by_custom_title(
    title: str,
    exact: bool = False,
) -> List[Dict[str, Any]]:
    try:
        from claude_code.utils.session_storage import search_sessions_by_custom_title
        return await search_sessions_by_custom_title(title, exact=exact)
    except (ImportError, Exception):
        return []


async def _save_custom_title(session_id: str, title: str, path: str) -> None:
    try:
        from claude_code.utils.session_storage import save_custom_title
        await save_custom_title(session_id, title, path)
    except (ImportError, Exception):
        pass


def _escape_regexp(s: str) -> str:
    return re.escape(s)


def _log_event(event: str, data: Dict[str, Any]) -> None:
    try:
        from claude_code.services.analytics.index import log_event
        log_event(event, data)
    except (ImportError, Exception):
        pass


# ---------------------------------------------------------------------------
# Core fork logic
# ---------------------------------------------------------------------------

async def get_unique_fork_name(base_name: str) -> str:
    """
    Generate a unique fork name, avoiding collisions with existing sessions.
    Mirrors getUniqueForkName() from the TS source.
    """
    candidate = f"{base_name} (Branch)"
    existing_exact = await _search_sessions_by_custom_title(candidate, exact=True)
    if not existing_exact:
        return candidate

    # Collision: search for all sessions starting with the pattern
    existing_forks = await _search_sessions_by_custom_title(f"{base_name} (Branch")
    used_numbers = {1}  # "(Branch)" without number is treated as 1
    pattern = re.compile(
        r"^" + _escape_regexp(base_name) + r" \(Branch(?: (\d+))?\)$"
    )
    for session in existing_forks:
        custom_title = session.get("customTitle") or session.get("custom_title", "")
        match = pattern.match(custom_title)
        if match:
            if match.group(1):
                used_numbers.add(int(match.group(1)))
            else:
                used_numbers.add(1)

    next_number = 2
    while next_number in used_numbers:
        next_number += 1

    return f"{base_name} (Branch {next_number})"


async def create_fork(custom_title: Optional[str] = None) -> Dict[str, Any]:
    """
    Creates a fork of the current conversation.
    Mirrors createFork() from the TS source.

    Returns a dict with keys:
        session_id, title, fork_path,
        serialized_messages, content_replacement_records
    """
    fork_session_id = str(uuid.uuid4())
    original_session_id = _get_session_id()
    project_dir = _get_project_dir(_get_original_cwd())
    fork_session_path = _get_transcript_path_for_session(fork_session_id)
    current_transcript_path = _get_transcript_path()

    # Ensure project directory exists
    Path(project_dir).mkdir(parents=True, exist_ok=True)

    # Read current transcript
    transcript_path = Path(current_transcript_path)
    if not transcript_path.exists() or transcript_path.stat().st_size == 0:
        raise ValueError("No conversation to branch")

    transcript_content = transcript_path.read_bytes()
    if not transcript_content:
        raise ValueError("No conversation to branch")

    # Parse all entries
    entries = _parse_jsonl(transcript_content)

    # Filter to main conversation messages (exclude sidechains)
    main_entries = [
        e for e in entries
        if _is_transcript_message(e) and not e.get("isSidechain", False)
    ]

    # Content-replacement entries: rewrite sessionId for the fork
    content_replacement_records = [
        replacement
        for e in entries
        if e.get("type") == "content-replacement" and e.get("sessionId") == original_session_id
        for replacement in e.get("replacements", [])
    ]

    if not main_entries:
        raise ValueError("No messages to branch")

    # Build forked JSONL lines
    parent_uuid: Optional[str] = None
    lines: List[str] = []
    serialized_messages: List[Dict[str, Any]] = []

    for entry in main_entries:
        forked_entry = {
            **entry,
            "sessionId": fork_session_id,
            "parentUuid": parent_uuid,
            "isSidechain": False,
            "forkedFrom": {
                "sessionId": original_session_id,
                "messageUuid": entry.get("uuid"),
            },
        }
        serialized = {**entry, "sessionId": fork_session_id}
        serialized_messages.append(serialized)
        lines.append(json.dumps(forked_entry, separators=(",", ":")))
        if entry.get("type") != "progress":
            parent_uuid = entry.get("uuid")

    # Append content-replacement entry for the fork
    if content_replacement_records:
        forked_replacement_entry = {
            "type": "content-replacement",
            "sessionId": fork_session_id,
            "replacements": content_replacement_records,
        }
        lines.append(json.dumps(forked_replacement_entry, separators=(",", ":")))

    # Write fork session file
    fork_path = Path(fork_session_path)
    fork_path.parent.mkdir(parents=True, exist_ok=True)
    fork_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Restrict permissions (0600)
    os.chmod(fork_session_path, 0o600)

    return {
        "session_id": fork_session_id,
        "title": custom_title,
        "fork_path": fork_session_path,
        "serialized_messages": serialized_messages,
        "content_replacement_records": content_replacement_records,
    }


async def call(
    args: str,
    context: Any = None,
    on_done: Any = None,
) -> Optional[str]:
    """
    Entry point for the /branch command.
    Mirrors call() from the TS source (without React/JSX).

    Returns a success or failure message string.
    """
    custom_title: Optional[str] = (args or "").strip() or None
    original_session_id = _get_session_id()

    try:
        fork_data = await create_fork(custom_title)
        session_id: str = fork_data["session_id"]
        fork_path: str = fork_data["fork_path"]
        serialized_messages: List[Dict[str, Any]] = fork_data["serialized_messages"]
        content_replacement_records: List[Any] = fork_data["content_replacement_records"]

        # Derive title from first user message
        first_user = next((m for m in serialized_messages if m.get("type") == "user"), None)
        first_prompt = derive_first_prompt(first_user)
        base_name = custom_title or first_prompt
        effective_title = await get_unique_fork_name(base_name)

        await _save_custom_title(session_id, effective_title, fork_path)

        _log_event(
            "tengu_conversation_forked",
            {
                "message_count": len(serialized_messages),
                "has_custom_title": bool(custom_title),
            },
        )

        title_info = f' "{custom_title}"' if custom_title else ""
        resume_hint = f"\nTo resume the original: claude -r {original_session_id}"
        success_message = (
            f"Branched conversation{title_info}. "
            f"You are now in the branch.{resume_hint}"
        )

        # Try to resume into the fork if context supports it
        if context is not None:
            resume_fn = getattr(context, "resume", None)
            if callable(resume_fn):
                await resume_fn(session_id, fork_data, "fork")
                if callable(on_done):
                    on_done(success_message, {"display": "system"})
                return success_message

        fallback_msg = (
            f"Branched conversation{title_info}. "
            f"Resume with: /resume {session_id}"
        )
        if callable(on_done):
            on_done(fallback_msg)
        return fallback_msg

    except Exception as error:
        message = str(error) if error else "Unknown error occurred"
        fail_msg = f"Failed to branch conversation: {message}"
        if callable(on_done):
            on_done(fail_msg)
        return fail_msg
