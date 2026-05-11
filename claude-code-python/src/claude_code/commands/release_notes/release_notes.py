"""
Ported from: commands/release-notes/release-notes.ts

/release-notes command — fetch and display the Claude Code changelog.
Attempts a live fetch with a 500 ms timeout; falls back to the cached notes;
finally falls back to showing the changelog URL.
"""
from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, Tuple

CHANGELOG_URL = "https://raw.githubusercontent.com/anthropics/anthropic-quickstarts/main/claude-code/CHANGELOG.md"


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

async def _fetch_and_store_changelog() -> None:
    try:
        from claude_code.utils.release_notes import (  # type: ignore[import]
            fetch_and_store_changelog,
        )
        await fetch_and_store_changelog()
    except ImportError:
        pass


async def _get_stored_changelog() -> Optional[str]:
    try:
        from claude_code.utils.release_notes import get_stored_changelog  # type: ignore[import]
        return await get_stored_changelog()
    except ImportError:
        return None


def _get_all_release_notes(
    raw: Optional[str],
) -> List[Tuple[str, List[str]]]:
    """Parse changelog text into ``[(version, [bullet, ...]), ...]``."""
    if not raw:
        return []
    try:
        from claude_code.utils.release_notes import get_all_release_notes  # type: ignore[import]
        return get_all_release_notes(raw)
    except ImportError:
        pass
    return _parse_changelog(raw)


def _parse_changelog(raw: str) -> List[Tuple[str, List[str]]]:
    """
    Minimal Markdown changelog parser.

    Expects sections like::

        ## [1.2.3]
        - bullet one
        - bullet two
    """
    import re
    results: List[Tuple[str, List[str]]] = []
    current_version: Optional[str] = None
    current_bullets: List[str] = []

    for line in raw.splitlines():
        version_match = re.match(r"^##\s+\[?([0-9]+\.[0-9]+\.[0-9][^\]]*)\]?", line)
        if version_match:
            if current_version and current_bullets:
                results.append((current_version, current_bullets))
            current_version = version_match.group(1)
            current_bullets = []
            continue

        if current_version:
            bullet_match = re.match(r"^\s*[-*]\s+(.+)", line)
            if bullet_match:
                current_bullets.append(bullet_match.group(1).strip())

    if current_version and current_bullets:
        results.append((current_version, current_bullets))

    return results


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _format_release_notes(notes: List[Tuple[str, List[str]]]) -> str:
    """Format parsed notes into human-readable text."""
    sections = []
    for version, bullets in notes:
        header = f"Version {version}:"
        bullet_lines = "\n".join(f"\u00b7 {note}" for note in bullets)
        sections.append(f"{header}\n{bullet_lines}")
    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Command entry point
# ---------------------------------------------------------------------------

async def call() -> Dict[str, str]:
    """
    Fetch and display release notes.

    Returns
    -------
    dict
        ``{"type": "text", "value": <notes or URL>}``
    """
    fresh_notes: List[Tuple[str, List[str]]] = []

    try:
        timeout_task = asyncio.create_task(asyncio.sleep(0.5))
        fetch_task = asyncio.create_task(_fetch_and_store_changelog())

        done, pending = await asyncio.wait(
            {timeout_task, fetch_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()

        changelog = await _get_stored_changelog()
        fresh_notes = _get_all_release_notes(changelog)
    except Exception:  # noqa: BLE001
        pass

    if fresh_notes:
        return {"type": "text", "value": _format_release_notes(fresh_notes)}

    # Fallback: check cached notes
    cached: Optional[str] = await _get_stored_changelog()
    cached_notes = _get_all_release_notes(cached)
    if cached_notes:
        return {"type": "text", "value": _format_release_notes(cached_notes)}

    # Last resort: show the changelog URL
    return {
        "type": "text",
        "value": f"See the full changelog at: {CHANGELOG_URL}",
    }
