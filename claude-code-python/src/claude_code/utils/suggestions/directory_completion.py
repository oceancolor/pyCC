"""Directory path completion for the prompt input. Ported from utils/suggestions/directoryCompletion.ts"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional


def complete_directory_path(
    partial: str,
    cwd: str,
    max_results: int = 20,
) -> List[str]:
    """Return filesystem path completions for the given partial path.

    Supports ``~`` expansion and both absolute and relative paths.

    Args:
        partial: The partial path the user has typed so far.
        cwd: The current working directory (for relative path resolution).
        max_results: Maximum number of completions to return.

    Returns:
        A list of completed path strings, ending with ``/`` for directories.
    """
    # Expand ~ to home directory
    expanded = os.path.expanduser(partial)

    # Determine the directory to list and the prefix to filter by
    if expanded.endswith("/") or expanded.endswith(os.sep):
        search_dir = expanded
        prefix = ""
    else:
        search_dir = os.path.dirname(expanded) or "."
        prefix = os.path.basename(expanded)

    # Resolve the directory relative to cwd
    if not os.path.isabs(search_dir):
        search_dir = os.path.join(cwd, search_dir)

    try:
        entries = os.listdir(search_dir)
    except (OSError, PermissionError):
        return []

    entries.sort()
    results: List[str] = []

    for entry in entries:
        if prefix and not entry.lower().startswith(prefix.lower()):
            continue

        full_path = os.path.join(search_dir, entry)
        is_dir = os.path.isdir(full_path)

        # Build the completion (preserve the user's tilde)
        if partial.startswith("~"):
            home = str(Path.home())
            display = full_path.replace(home, "~", 1)
        elif not os.path.isabs(partial):
            try:
                display = os.path.relpath(full_path, cwd)
            except ValueError:
                display = full_path
        else:
            display = full_path

        if is_dir:
            display = display.rstrip("/") + "/"

        results.append(display)
        if len(results) >= max_results:
            break

    return results


def get_directory_suggestions(
    partial: str,
    cwd: str,
    max_results: int = 20,
) -> List[dict]:
    """Return directory completion suggestions as dicts suitable for the UI.

    Each dict has ``value`` (the completion) and ``label`` (display text).
    """
    completions = complete_directory_path(partial, cwd, max_results)
    return [{"value": c, "label": c} for c in completions]
