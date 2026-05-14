"""Team memory merge. Three-way merge logic for team memory content.

Merges local changes on top of a remote base when both sides have diverged.
"""
from __future__ import annotations
from typing import Dict, Optional, Tuple


def merge_content(
    base: str,
    local: str,
    remote: str,
) -> Tuple[str, bool]:
    """Three-way merge of text content.

    Returns:
        (merged_content, has_conflict): The merged text and whether
        there were any irreconcilable conflicts.
    """
    if local == remote:
        return local, False

    if local == base:
        return remote, False

    if remote == base:
        return local, False

    # Both sides changed — perform line-level three-way merge
    base_lines = base.splitlines()
    local_lines = local.splitlines()
    remote_lines = remote.splitlines()

    try:
        import difflib
        # Apply remote diff to local as best-effort
        remote_patch = list(difflib.unified_diff(base_lines, remote_lines, lineterm=""))
        if not remote_patch:
            return local, False
        # Fallback: prefer local with conflict markers
        merged_lines = local_lines + [
            "<<<<<<< LOCAL",
            *remote_lines,
            "=======",
            ">>>>>>> REMOTE",
        ]
        return "\n".join(merged_lines), True
    except Exception:
        return local, True


def merge_entries(
    base_entries: Dict[str, str],
    local_entries: Dict[str, str],
    remote_entries: Dict[str, str],
) -> Tuple[Dict[str, str], Dict[str, bool]]:
    """Merge two sets of entry updates on top of a common base.

    Returns:
        (merged, conflicts): merged entries dict and per-filename conflict flags.
    """
    merged: Dict[str, str] = {}
    conflicts: Dict[str, bool] = {}

    all_keys = set(base_entries) | set(local_entries) | set(remote_entries)

    for key in all_keys:
        base = base_entries.get(key, "")
        local = local_entries.get(key, "")
        remote = remote_entries.get(key, "")

        if key not in local_entries:
            # Deleted locally — honour the deletion unless remote changed it
            if remote != base:
                merged[key] = remote
            # else: deleted both places or only locally — omit
            continue

        if key not in remote_entries:
            # Deleted remotely — honour the deletion unless local changed it
            if local != base:
                merged[key] = local
            continue

        content, has_conflict = merge_content(base, local, remote)
        merged[key] = content
        if has_conflict:
            conflicts[key] = True

    return merged, conflicts
