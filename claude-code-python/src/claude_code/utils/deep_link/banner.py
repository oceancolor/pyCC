"""Deep link warning banner. Ported from utils/deepLink/banner.ts"""

from __future__ import annotations

import os
import stat as stat_module
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

STALE_FETCH_WARN_MS = 7 * 24 * 60 * 60 * 1000  # 7 days in ms
LONG_PREFILL_THRESHOLD = 1000  # characters


def _format_relative_time_ago(dt: datetime) -> str:
    """Simple relative-time formatter (e.g. '2 hours ago')."""
    delta = datetime.now() - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds} seconds ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minutes ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hours ago"
    days = hours // 24
    return f"{days} days ago"


def _tildify(path: str) -> str:
    """Shorten home-directory-prefixed paths to ~ notation."""
    home = str(Path.home())
    if path == home:
        return "~"
    if path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path


def _format_number(n: int) -> str:
    """Format a number with comma separators."""
    return f"{n:,}"


def build_deep_link_banner(
    cwd: str,
    prefill_length: Optional[int] = None,
    repo: Optional[str] = None,
    last_fetch: Optional[datetime] = None,
) -> str:
    """Build the multi-line warning banner for a deep-link-originated session.

    Always shows the working directory so the user can see which CLAUDE.md will
    load. When the link pre-filled a prompt, adds a second line prompting the
    user to review it.

    Args:
        cwd: Resolved working directory the session launched in.
        prefill_length: Length of the pre-filled prompt (chars). None = no prefill.
        repo: The ``?repo=`` slug if cwd was resolved from the githubRepoPaths MRU.
        last_fetch: Last-fetch timestamp for the repo (FETCH_HEAD mtime).

    Returns:
        Multi-line banner string (lines joined with ``\\n``).
    """
    lines = [f"This session was opened by an external deep link in {_tildify(cwd)}"]

    if repo:
        age = _format_relative_time_ago(last_fetch) if last_fetch else "never"
        stale = (
            last_fetch is None
            or (datetime.now() - last_fetch).total_seconds() * 1000 > STALE_FETCH_WARN_MS
        )
        stale_suffix = " — CLAUDE.md may be stale" if stale else ""
        lines.append(f"Resolved {repo} from local clones · last fetched {age}{stale_suffix}")

    if prefill_length:
        if prefill_length > LONG_PREFILL_THRESHOLD:
            lines.append(
                f"The prompt below ({_format_number(prefill_length)} chars) was supplied "
                "by the link — scroll to review the entire prompt before pressing Enter."
            )
        else:
            lines.append(
                "The prompt below was supplied by the link — review carefully before pressing Enter."
            )

    return "\n".join(lines)


async def read_last_fetch_time(cwd: str) -> Optional[datetime]:
    """Read the mtime of .git/FETCH_HEAD, which git updates on every fetch.

    Returns None if the directory is not a git repo or has never been fetched.
    Checks both the worktree-local FETCH_HEAD and the common-dir FETCH_HEAD,
    returning whichever is newer.
    """
    git_dir = await _get_git_dir(cwd)
    if not git_dir:
        return None

    common_dir = await _get_common_dir(git_dir)

    local_fetch = await _mtime_or_none(Path(git_dir) / "FETCH_HEAD")
    common_fetch = await _mtime_or_none(Path(common_dir) / "FETCH_HEAD") if common_dir else None

    if local_fetch and common_fetch:
        return local_fetch if local_fetch > common_fetch else common_fetch
    return local_fetch or common_fetch


async def _get_git_dir(cwd: str) -> Optional[str]:
    """Return the .git directory path for the given working directory, or None."""
    import asyncio
    import subprocess

    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", cwd, "rev-parse", "--git-dir",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return None
        git_dir = stdout.decode().strip()
        if not os.path.isabs(git_dir):
            git_dir = os.path.join(cwd, git_dir)
        return git_dir
    except Exception:
        return None


async def _get_common_dir(git_dir: str) -> Optional[str]:
    """Return the common dir for a worktree, or None if it equals git_dir."""
    import asyncio

    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "--git-dir", git_dir, "rev-parse", "--git-common-dir",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return None
        common = stdout.decode().strip()
        common = os.path.join(git_dir, common) if not os.path.isabs(common) else common
        return common if common != git_dir else None
    except Exception:
        return None


async def _mtime_or_none(path: Path) -> Optional[datetime]:
    """Return the mtime of a file, or None if it doesn't exist."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        st = await loop.run_in_executor(None, path.stat)
        return datetime.fromtimestamp(st.st_mtime)
    except Exception:
        return None
