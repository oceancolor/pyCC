"""
Release notes checker for Claude Code Python port.

Flow:
1. On startup, check if version changed vs last_seen_version
2. Parse CHANGELOG.md from cache or fetch from GitHub
3. Return notes newer than last_seen_version (up to MAX_RELEASE_NOTES_SHOWN)
4. After user sees notes, call mark_release_notes_seen(version)
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from packaging.version import Version, InvalidVersion

MAX_RELEASE_NOTES_SHOWN = 5

CHANGELOG_URL = "https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md"
_RAW_CHANGELOG_URL = (
    "https://raw.githubusercontent.com/anthropics/claude-code/refs/heads/main/CHANGELOG.md"
)

# In-memory cache for the changelog content
_changelog_cache: Optional[str] = None


# ── Config / path helpers ─────────────────────────────────────────────────

def _cfg_home() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_HOME", Path.home() / ".claude"))

def _changelog_cache_path() -> Path:
    return _cfg_home() / "cache" / "changelog.md"

def _seen_version_path() -> Path:
    return _cfg_home() / "release_notes_seen_version"


# ── Changelog I/O ─────────────────────────────────────────────────────────

async def _fetch_changelog() -> str:
    """Fetch raw changelog from GitHub. Returns empty string on failure."""
    try:
        import aiohttp  # type: ignore
        async with aiohttp.ClientSession() as session:
            async with session.get(_RAW_CHANGELOG_URL, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.text()
    except Exception:
        pass
    # Fallback: try urllib
    try:
        import urllib.request
        with urllib.request.urlopen(_RAW_CHANGELOG_URL, timeout=10) as r:
            return r.read().decode("utf-8")
    except Exception:
        pass
    return ""


async def get_stored_changelog() -> str:
    """Load changelog from disk cache (populates in-memory cache)."""
    global _changelog_cache
    if _changelog_cache is not None:
        return _changelog_cache
    try:
        content = _changelog_cache_path().read_text(encoding="utf-8")
        _changelog_cache = content
        return content
    except Exception:
        _changelog_cache = ""
        return ""


async def fetch_and_store_changelog() -> None:
    """Fetch latest changelog and persist to disk cache."""
    global _changelog_cache
    content = await _fetch_changelog()
    if not content:
        return
    if content == _changelog_cache:
        return
    cache_path = _changelog_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(content, encoding="utf-8")
    _changelog_cache = content


def _reset_cache_for_testing() -> None:
    global _changelog_cache
    _changelog_cache = None


# ── Parsing ───────────────────────────────────────────────────────────────

def parse_changelog(content: str) -> Dict[str, List[str]]:
    """Parse markdown changelog → {version: [bullet, ...]}."""
    if not content:
        return {}
    result: Dict[str, List[str]] = {}
    sections = re.split(r"^## ", content, flags=re.MULTILINE)[1:]
    for section in sections:
        lines = section.strip().splitlines()
        if not lines:
            continue
        version = lines[0].split(" - ")[0].strip()
        if not version:
            continue
        notes = [
            ln.strip()[2:].strip()
            for ln in lines[1:]
            if ln.strip().startswith("- ")
        ]
        if notes:
            result[version] = notes
    return result


def _parse_ver(v: str) -> Optional[Version]:
    try:
        return Version(v)
    except InvalidVersion:
        # strip git SHA suffix if present (e.g. "1.2.3-abc123")
        m = re.match(r"^(\d+\.\d+(?:\.\d+)?)", v)
        if m:
            try:
                return Version(m.group(1))
            except InvalidVersion:
                pass
    return None


# ── Public API ────────────────────────────────────────────────────────────

def should_show_release_notes(
    current_version: str,
    last_seen_version: Optional[str],
) -> bool:
    """Return True if there are unseen release notes to display."""
    if not last_seen_version:
        return True
    cur = _parse_ver(current_version)
    last = _parse_ver(last_seen_version)
    if cur is None or last is None:
        return current_version != last_seen_version
    return cur > last


def get_release_notes(
    current_version: str,
    last_seen_version: Optional[str],
    changelog_content: str = "",
) -> str:
    """
    Return formatted release notes for versions newer than last_seen_version.
    changelog_content defaults to in-memory cache if empty.
    """
    content = changelog_content or (_changelog_cache or "")
    if not content:
        return ""

    parsed = parse_changelog(content)
    last = _parse_ver(last_seen_version) if last_seen_version else None

    # Collect entries newer than last_seen
    entries: List[Tuple[Version, str, List[str]]] = []
    for ver_str, notes in parsed.items():
        v = _parse_ver(ver_str)
        if v is None:
            continue
        if last is None or v > last:
            entries.append((v, ver_str, notes))

    # Sort newest first
    entries.sort(key=lambda x: x[0], reverse=True)

    # Flatten bullets up to MAX_RELEASE_NOTES_SHOWN
    bullets: List[str] = []
    for _, ver_str, notes in entries:
        for note in notes:
            bullets.append(f"• [{ver_str}] {note}")
            if len(bullets) >= MAX_RELEASE_NOTES_SHOWN:
                break
        if len(bullets) >= MAX_RELEASE_NOTES_SHOWN:
            break

    return "\n".join(bullets)


def mark_release_notes_seen(version: str) -> None:
    """Record that the user has seen release notes for this version."""
    path = _seen_version_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(version, encoding="utf-8")


def get_last_seen_version() -> Optional[str]:
    """Read the last version for which release notes were shown."""
    try:
        return _seen_version_path().read_text(encoding="utf-8").strip() or None
    except Exception:
        return None


async def check_for_release_notes(
    current_version: str,
    last_seen_version: Optional[str] = None,
) -> dict:
    """
    Async entry-point: load cached changelog, trigger background fetch if needed.
    Returns {"has_release_notes": bool, "release_notes": str}.
    """
    if last_seen_version is None:
        last_seen_version = get_last_seen_version()

    changelog = await get_stored_changelog()

    # Trigger background fetch if version changed or no cache
    if last_seen_version != current_version or not changelog:
        import asyncio
        asyncio.ensure_future(fetch_and_store_changelog())

    notes = get_release_notes(current_version, last_seen_version, changelog)
    return {
        "has_release_notes": bool(notes),
        "release_notes": notes,
    }
