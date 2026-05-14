"""Team memory diff. Computes diffs between local and remote team memory entries.

These functions support the sync logic in index.py. The TS source keeps all
sync logic in a single index.ts; we split it into focused modules for clarity.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple


def diff_entries(
    local: Dict[str, str],
    remote: Dict[str, str],
) -> Tuple[List[str], List[str], List[str]]:
    """Compute diff between local and remote memory entries by filename.

    Returns:
        (added, modified, removed): filenames in each category.
        - added: in local, not in remote
        - modified: in both, but content differs
        - removed: in remote, not in local
    """
    local_keys = set(local.keys())
    remote_keys = set(remote.keys())

    added = sorted(local_keys - remote_keys)
    removed = sorted(remote_keys - local_keys)
    modified = sorted(
        k for k in local_keys & remote_keys
        if local[k] != remote[k]
    )

    return added, modified, removed


def entries_to_upload(
    local: Dict[str, str],
    remote_checksums: Dict[str, str],
) -> Dict[str, str]:
    """Return entries that need to be uploaded (new or changed)."""
    import hashlib

    result: Dict[str, str] = {}
    for filename, content in local.items():
        checksum = hashlib.sha256(content.encode()).hexdigest()
        if remote_checksums.get(filename) != checksum:
            result[filename] = content
    return result


def entries_to_delete(
    local_files: List[str],
    remote_files: List[str],
) -> List[str]:
    """Return remote filenames that no longer exist locally."""
    local_set = set(local_files)
    return [f for f in remote_files if f not in local_set]
