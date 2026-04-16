"""
Session restore utilities.
Ported from sessionRestore.ts — loads previous session message history from disk.

The TS original is deeply coupled to the Bun/React REPL internals
(AppState, switchSession, worktree, context-collapse, etc.).
This Python port focuses on the portable core:
  - find_latest_session(cwd)  → most-recent session ID
  - restore_session(session_id, cwd) → load messages from JSONL transcript
  - prepare_resume_messages(messages) → clean up messages for resumption
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLAUDE_HOME = Path(os.environ.get("CLAUDE_HOME", Path.home() / ".claude"))
PROJECTS_DIR = CLAUDE_HOME / "projects"


# ---------------------------------------------------------------------------
# Minimal message types
# ---------------------------------------------------------------------------

@dataclass
class Message:
    """Minimal representation of a Claude conversation message."""
    type: str                           # "user" | "assistant" | "system"
    content: Any                        # str or list of content blocks
    role: Optional[str] = None
    # Extra metadata carried through from JSONL
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"type": self.type, "content": self.content}
        if self.role:
            d["role"] = self.role
        d.update(self.extra)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        return cls(
            type=data.get("type", ""),
            content=data.get("content", ""),
            role=data.get("role"),
            extra={k: v for k, v in data.items() if k not in ("type", "content", "role")},
        )


@dataclass
class SessionTranscript:
    """Loaded transcript for a session."""
    session_id: str
    messages: List[Message]
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _project_dir_for_cwd(cwd: str) -> Path:
    """
    Map a working directory path to its Claude projects subdirectory.
    Claude encodes the cwd as a URL-encoded or slash-to-dash path component.
    Example: /home/user/myproject → ~/.claude/projects/-home-user-myproject/
    """
    # Encode path: replace "/" with "-" (Claude's convention)
    encoded = cwd.replace(os.sep, "-")
    if encoded.startswith("-"):
        pass  # expected: leading slash becomes leading dash
    return PROJECTS_DIR / encoded


def _find_project_dirs(cwd: str) -> List[Path]:
    """Return candidate project dirs for *cwd* (exact match first, then fuzzy)."""
    exact = _project_dir_for_cwd(cwd)
    candidates = [exact]

    if PROJECTS_DIR.exists():
        for p in PROJECTS_DIR.iterdir():
            if p != exact and p.is_dir():
                # Simple heuristic: directory name ends with the last component of cwd
                last = Path(cwd).name
                if last and p.name.endswith(last):
                    candidates.append(p)
    return candidates


def _jsonl_files_in(directory: Path) -> List[Path]:
    """Return all .jsonl files in *directory*, sorted by mtime descending."""
    if not directory.exists():
        return []
    files = [f for f in directory.iterdir() if f.suffix == ".jsonl"]
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------

def find_latest_session(cwd: str) -> Optional[str]:
    """
    Find the most-recently modified session ID for *cwd*.
    Returns the session ID string (stem of the .jsonl file), or None.
    """
    for proj_dir in _find_project_dirs(cwd):
        files = _jsonl_files_in(proj_dir)
        if files:
            return files[0].stem  # filename without extension = session ID
    logger.debug("No sessions found for cwd=%s", cwd)
    return None


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read a JSONL file; skip malformed lines."""
    records: List[Dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("Cannot read %s: %s", path, exc)
        return records

    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            logger.debug("Skipping malformed JSON at %s:%d — %s", path, lineno, exc)
    return records


def restore_session(
    session_id: str,
    cwd: str,
) -> Optional[SessionTranscript]:
    """
    Load a session transcript from disk.

    Scans ~/.claude/projects/<encoded-cwd>/<session_id>.jsonl.
    Returns None if the file is not found.
    """
    for proj_dir in _find_project_dirs(cwd):
        jsonl_path = proj_dir / f"{session_id}.jsonl"
        if jsonl_path.exists():
            return _load_transcript(session_id, jsonl_path)

    logger.debug("Session %s not found for cwd=%s", session_id, cwd)
    return None


def _load_transcript(session_id: str, path: Path) -> SessionTranscript:
    """Parse a JSONL transcript file into a SessionTranscript."""
    records = _read_jsonl(path)
    messages: List[Message] = []
    metadata: Dict[str, Any] = {}

    for record in records:
        record_type = record.get("type", "")

        # Metadata / summary entries — not conversation messages
        if record_type in ("summary", "metadata", "session_metadata"):
            metadata.update({k: v for k, v in record.items() if k != "type"})
            continue

        # Context-collapse and other internal markers — skip
        if record_type in (
            "context_collapse_commit",
            "context_collapse_snapshot",
            "attribution_snapshot",
            "file_history_snapshot",
            "content_replacement",
        ):
            continue

        # Conversation message
        if record_type in ("user", "assistant", "system"):
            messages.append(Message.from_dict(record))
        elif "message" in record:
            # Some formats wrap the message object
            inner = record["message"]
            if isinstance(inner, dict):
                msg = Message.from_dict(inner)
                if not msg.type:
                    msg.type = record_type
                messages.append(msg)

    logger.debug(
        "Loaded %d messages from %s (metadata keys: %s)",
        len(messages),
        path,
        list(metadata.keys()),
    )
    return SessionTranscript(
        session_id=session_id,
        messages=messages,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Message preparation
# ---------------------------------------------------------------------------

def prepare_resume_messages(
    messages: List[Message],
    *,
    drop_empty_assistant: bool = True,
    max_messages: Optional[int] = None,
) -> List[Message]:
    """
    Process a loaded message list to prepare it for resumption.

    Steps:
    1. Drop trailing empty/whitespace-only assistant messages (they indicate
       an incomplete turn that was interrupted).
    2. Optionally truncate to *max_messages* most-recent entries.
    3. Ensure the list ends with a complete user/assistant exchange
       (drop a lone trailing user message, since the model hasn't responded).
    """
    result = list(messages)

    # Drop trailing empty assistant messages
    if drop_empty_assistant:
        while result:
            last = result[-1]
            if last.type == "assistant" and _is_empty_content(last.content):
                result.pop()
            else:
                break

    # Remove a lone trailing user turn (no paired assistant response)
    if result and result[-1].type == "user":
        # Only strip if the second-to-last is also user or there's nothing before
        # i.e. we have an unpaired user message at the very end
        # (assistant message would be right before it to form a pair)
        prev = result[-2] if len(result) >= 2 else None
        if prev is None or prev.type != "assistant":
            result.pop()

    # Truncate
    if max_messages and len(result) > max_messages:
        result = result[-max_messages:]

    return result


def _is_empty_content(content: Any) -> bool:
    """Return True if *content* is empty or contains only whitespace."""
    if content is None:
        return True
    if isinstance(content, str):
        return not content.strip()
    if isinstance(content, list):
        if not content:
            return True
        # Check if every block is empty
        return all(_is_empty_block(block) for block in content)
    return False


def _is_empty_block(block: Any) -> bool:
    if not isinstance(block, dict):
        return False
    block_type = block.get("type", "")
    if block_type == "text":
        return not block.get("text", "").strip()
    return False


# ---------------------------------------------------------------------------
# Convenience: restore latest
# ---------------------------------------------------------------------------

def restore_latest_session(cwd: str) -> Optional[SessionTranscript]:
    """Find and load the most recent session for *cwd*."""
    session_id = find_latest_session(cwd)
    if not session_id:
        return None
    return restore_session(session_id, cwd)
