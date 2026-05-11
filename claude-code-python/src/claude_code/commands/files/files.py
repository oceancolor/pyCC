"""
Ported from: commands/files/files.ts

/files command — list all files currently held in the tool-use context's
read-file state cache, relative to the current working directory.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

def _get_cwd() -> str:
    try:
        from claude_code.utils.cwd import get_cwd  # type: ignore[import]
        return get_cwd()
    except ImportError:
        return os.getcwd()


def _cache_keys(read_file_state: object) -> List[str]:
    """
    Extract the absolute file paths from the read-file-state cache.

    The TS source calls ``cacheKeys(context.readFileState)`` which returns
    the keys of the Map<string, …> cache.  In Python the cache may be a
    dict or an object exposing ``.keys()``.
    """
    try:
        from claude_code.utils.file_state_cache import cache_keys  # type: ignore[import]
        return list(cache_keys(read_file_state))
    except ImportError:
        pass

    # Fallback: if read_file_state is dict-like use its keys
    if isinstance(read_file_state, dict):
        return list(read_file_state.keys())
    keys_fn = getattr(read_file_state, "keys", None)
    if callable(keys_fn):
        return list(keys_fn())
    return []


# ---------------------------------------------------------------------------
# Command entry point
# ---------------------------------------------------------------------------

async def call(
    _args: str,
    context: object,
) -> Dict[str, str]:
    """
    Return a text listing of files in the current context.

    Parameters
    ----------
    _args:
        Unused argument string (command takes no arguments).
    context:
        ToolUseContext duck-typed object; must expose ``read_file_state``
        attribute.

    Returns
    -------
    dict
        ``{"type": "text", "value": <listing>}``
    """
    read_file_state: Optional[object] = getattr(context, "read_file_state", None)
    files: List[str] = _cache_keys(read_file_state) if read_file_state is not None else []

    if not files:
        return {"type": "text", "value": "No files in context"}

    cwd = _get_cwd()
    relative_paths = [os.path.relpath(f, cwd) for f in files]
    file_list = "\n".join(relative_paths)
    return {"type": "text", "value": f"Files in context:\n{file_list}"}
