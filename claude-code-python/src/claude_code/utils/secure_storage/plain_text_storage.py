"""Plain-text credentials storage. Ported from utils/secureStorage/plainTextStorage.ts"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Optional, Dict, Any

SecureStorageData = Dict[str, Any]

_STORAGE_FILE_NAME = ".credentials.json"


def _get_storage_path() -> tuple[str, str]:
    """Return (storage_dir, storage_path) for the credentials file."""
    from claude_code.utils.env_utils import get_claude_config_home_dir

    storage_dir = get_claude_config_home_dir()
    storage_path = os.path.join(storage_dir, _STORAGE_FILE_NAME)
    return storage_dir, storage_path


class _PlainTextStorage:
    """Stores credentials as JSON at ``~/.claude/.credentials.json`` (mode 0600)."""

    name = "plaintext"

    def read(self) -> Optional[SecureStorageData]:
        """Read credentials synchronously."""
        _, storage_path = _get_storage_path()
        try:
            with open(storage_path, encoding="utf-8") as f:
                return json.loads(f.read())
        except Exception:
            return None

    async def read_async(self) -> Optional[SecureStorageData]:
        """Read credentials asynchronously (delegates to synchronous read)."""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.read)

    def update(self, data: SecureStorageData) -> dict:
        """Write credentials to disk. Creates parent directory if necessary."""
        try:
            storage_dir, storage_path = _get_storage_path()
            try:
                os.makedirs(storage_dir, exist_ok=True)
            except OSError as exc:
                if exc.errno != 17:  # EEXIST
                    raise

            content = json.dumps(data, indent=2)
            # Write atomically: write to temp, then rename
            tmp_path = storage_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, storage_path)
            return {
                "success": True,
                "warning": "Warning: Storing credentials in plaintext.",
            }
        except Exception:
            return {"success": False}

    def delete(self) -> bool:
        """Delete the credentials file."""
        _, storage_path = _get_storage_path()
        try:
            os.unlink(storage_path)
            return True
        except FileNotFoundError:
            return True
        except Exception:
            return False


# Module-level singleton (matches TS ``export const plainTextStorage``)
plain_text_storage = _PlainTextStorage()
