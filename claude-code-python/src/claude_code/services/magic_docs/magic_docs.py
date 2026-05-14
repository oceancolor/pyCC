"""Magic Docs service. Ported from services/MagicDocs/magicDocs.ts

Magic Docs automatically maintains markdown documentation files marked with
a "# MAGIC DOC: [title]" header. When such a file is read, a background
sub-agent periodically updates it with new learnings from the conversation.
"""
from __future__ import annotations
import re
from typing import Dict, Optional, Tuple

# Header pattern: # MAGIC DOC: [title]
_MAGIC_DOC_HEADER_PATTERN = re.compile(r"^#\s*MAGIC\s+DOC:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_ITALICS_PATTERN = re.compile(r"^[_*](.+?)[_*]\s*$", re.MULTILINE)

# Track discovered magic docs {path: title}
_tracked_magic_docs: Dict[str, str] = {}


def detect_magic_doc_header(content: str) -> Optional[Dict[str, Optional[str]]]:
    """Detect if a file contains a Magic Doc header.

    Returns {"title": str, "instructions": Optional[str]}, or None.
    """
    match = _MAGIC_DOC_HEADER_PATTERN.search(content)
    if not match or not match.group(1):
        return None

    title = match.group(1).strip()

    # Look for italics instruction on the line immediately after the header
    after_header = content[match.end():]
    next_line_match = re.match(r"^\s*\n(?:\s*\n)?(.+?)(?:\n|$)", after_header)
    instructions: Optional[str] = None

    if next_line_match and next_line_match.group(1):
        italics_match = _ITALICS_PATTERN.match(next_line_match.group(1))
        if italics_match and italics_match.group(1):
            instructions = italics_match.group(1).strip()

    return {"title": title, "instructions": instructions}


def register_magic_doc(path: str, title: str) -> None:
    """Register a file as a tracked Magic Doc."""
    _tracked_magic_docs[path] = title


def unregister_magic_doc(path: str) -> None:
    """Remove a file from the tracked Magic Docs registry."""
    _tracked_magic_docs.pop(path, None)


def get_tracked_magic_docs() -> Dict[str, str]:
    """Return a copy of all tracked Magic Docs (path -> title)."""
    return dict(_tracked_magic_docs)


def clear_tracked_magic_docs() -> None:
    """Clear all tracked Magic Docs (e.g. after compaction)."""
    _tracked_magic_docs.clear()


async def fetch_magic_doc(url: str) -> Optional[str]:
    """Fetch the content of a Magic Doc from a URL."""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.text()
    except Exception:
        pass
    return None


async def maybe_trigger_magic_doc_update(
    path: str,
    content: str,
    context: object = None,
) -> None:
    """Check if a file is a Magic Doc and, if so, queue a background update.

    This is a no-op when running outside of an interactive REPL context
    that supports post-sampling hooks.
    """
    detection = detect_magic_doc_header(content)
    if detection is None:
        return

    title = detection["title"]
    register_magic_doc(path, title)

    # In a full implementation, this would register a post-sampling hook
    # that runs a sub-agent to update the doc after each conversation turn.
    # Here we just track the doc; the orchestration layer should call
    # run_magic_doc_update() at the right time.


async def run_magic_doc_update(
    path: str,
    title: str,
    conversation_context: object = None,
    instructions: Optional[str] = None,
) -> bool:
    """Run a Magic Doc update for the given file.

    Returns True if the update was attempted (even if it found nothing to do),
    False if the update could not run (e.g. file not readable).
    """
    from pathlib import Path

    doc_path = Path(path)
    if not doc_path.is_file():
        return False

    try:
        doc_contents = doc_path.read_text(encoding="utf-8")
    except Exception:
        return False

    try:
        from claude_code.services.magic_docs.prompts import build_update_prompt
        _prompt = build_update_prompt(
            doc_path=path,
            doc_contents=doc_contents,
            doc_title=title,
            custom_instructions=instructions or "",
        )
        # In a full implementation, this would invoke a sub-agent with the prompt.
        # For now we return True to indicate the update was requested.
        return True
    except Exception:
        return False
