"""Deep link protocol handler. Ported from utils/deepLink/protocolHandler.ts"""

from __future__ import annotations

import os
import sys
import asyncio
from typing import Optional

from .parse_deep_link import parse_deep_link, DeepLinkAction
from .banner import read_last_fetch_time


async def handle_deep_link_uri(uri: str) -> int:
    """Handle an incoming deep link URI.

    Called from the CLI entry point when ``--handle-uri`` is passed. Parses the
    URI, resolves the working directory, and launches Claude Code in the user's
    terminal.

    Args:
        uri: The raw URI string (e.g. ``claude-cli://open?q=hello+world``).

    Returns:
        Exit code – 0 on success, 1 on error.
    """
    try:
        action = parse_deep_link(uri)
    except (ValueError, Exception) as exc:
        print(f"Deep link error: {exc}", file=sys.stderr)
        return 1

    cwd, resolved_repo = await _resolve_cwd(action)
    last_fetch = await read_last_fetch_time(cwd) if resolved_repo else None

    try:
        from .terminal_launcher import launch_in_terminal

        launched = await launch_in_terminal(
            sys.executable,
            cwd=cwd,
            prefill=action.query,
            deep_link_origin=True,
            repo=resolved_repo,
            last_fetch=last_fetch,
        )
        return 0 if launched else 1
    except Exception as exc:
        print(f"Failed to launch terminal: {exc}", file=sys.stderr)
        return 1


async def _resolve_cwd(action: DeepLinkAction) -> tuple[str, Optional[str]]:
    """Resolve the working directory from the deep link action.

    Priority:
    1. Explicit ``cwd`` parameter (must exist as a directory).
    2. ``repo`` parameter resolved against the githubRepoPaths MRU config.
    3. Fall back to the current working directory.

    Returns:
        (resolved_cwd, resolved_repo_slug_or_None)
    """
    if action.cwd and os.path.isdir(action.cwd):
        return action.cwd, None

    if action.repo:
        resolved = await _resolve_repo_path(action.repo)
        if resolved:
            return resolved, action.repo

    return os.getcwd(), None


async def _resolve_repo_path(repo_slug: str) -> Optional[str]:
    """Resolve a ``owner/repo`` slug to a local clone path.

    Reads the githubRepoPaths config (a list of recently-opened directories)
    and returns the first directory whose basename matches the repo name portion.
    Returns None if no matching directory is found.
    """
    try:
        from claude_code.utils.config import get_global_config

        config = get_global_config()
        github_paths: list = getattr(config, "github_repo_paths", []) or []
        repo_name = repo_slug.split("/")[-1] if "/" in repo_slug else repo_slug

        for path in github_paths:
            if os.path.isdir(path) and os.path.basename(path) == repo_name:
                return path
    except Exception:
        pass
    return None
