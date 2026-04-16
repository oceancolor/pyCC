"""Paste store - Python port of pasteStore.ts.

Content-addressable disk store for pasted text, keyed by SHA-256 hash.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

PASTE_STORE_DIR = 'paste-cache'


def _get_paste_store_dir() -> Path:
    """Return the paste cache directory path."""
    config_home = os.environ.get('CLAUDE_CONFIG_HOME') or os.path.join(
        os.path.expanduser('~'), '.claude'
    )
    return Path(config_home) / PASTE_STORE_DIR


def hash_pasted_text(content: str) -> str:
    """Return a 16-char hex SHA-256 hash of *content*."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]


def _get_paste_path(hash_: str) -> Path:
    return _get_paste_store_dir() / f'{hash_}.txt'


def store_pasted_text(hash_: str, content: str) -> None:
    """Write *content* to disk under *hash_*. Content-addressable: safe to overwrite."""
    try:
        directory = _get_paste_store_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = _get_paste_path(hash_)
        path.write_text(content, encoding='utf-8')
        path.chmod(0o600)
    except OSError:
        pass  # Fail silently, matching TS behaviour


def retrieve_pasted_text(hash_: str) -> Optional[str]:
    """Read and return paste content by *hash_*. Returns None if not found."""
    try:
        return _get_paste_path(hash_).read_text(encoding='utf-8')
    except FileNotFoundError:
        return None
    except OSError:
        return None


def cleanup_old_pastes(cutoff_date: datetime) -> None:
    """Remove paste files older than *cutoff_date* (based on mtime)."""
    paste_dir = _get_paste_store_dir()
    if not paste_dir.is_dir():
        return
    cutoff_ts = cutoff_date.timestamp()
    for file_path in paste_dir.glob('*.txt'):
        try:
            if file_path.stat().st_mtime < cutoff_ts:
                file_path.unlink()
        except OSError:
            pass


class PasteStore:
    """In-process paste store with persistent disk backend.

    store(content)     → key (hash)
    retrieve(key)      → content | None
    clear()            → removes all cached pastes
    """

    def store(self, content: str) -> str:
        """Store *content* and return its hash key."""
        key = hash_pasted_text(content)
        store_pasted_text(key, content)
        return key

    def retrieve(self, key: str) -> Optional[str]:
        """Return paste content for *key*, or None if not found."""
        return retrieve_pasted_text(key)

    def clear(self) -> None:
        """Delete all paste files from the store directory."""
        paste_dir = _get_paste_store_dir()
        if paste_dir.is_dir():
            try:
                shutil.rmtree(paste_dir)
            except OSError:
                pass
