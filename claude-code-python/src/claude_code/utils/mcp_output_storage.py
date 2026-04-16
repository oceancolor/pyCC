"""
MCP tool output temporary storage (large-result disk cache).

Stores oversized MCP tool results to disk so they can be referenced by
path rather than inlined into the model context.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


_DEFAULT_DIR_PREFIX = "claude_mcp_output_"


class McpOutputStorage:
    """Disk-backed key/value cache for large MCP tool outputs.

    Usage::

        storage = McpOutputStorage()
        path = storage.store("my_key", {"result": [1, 2, 3]})
        data = storage.retrieve("my_key")
        storage.clear()
    """

    def __init__(self, base_dir: str | Path | None = None) -> None:
        if base_dir is not None:
            self._dir = Path(base_dir)
            self._dir.mkdir(parents=True, exist_ok=True)
            self._owns_dir = False
        else:
            self._dir = Path(tempfile.mkdtemp(prefix=_DEFAULT_DIR_PREFIX))
            self._owns_dir = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store(self, key: str, data: Any) -> str:
        """Serialize *data* to JSON and write to disk.

        Returns the absolute path of the written file.
        Overwrites any existing file for *key*.
        """
        file_path = self._path_for(key)
        serialized = json.dumps(data, ensure_ascii=False, default=str)
        file_path.write_text(serialized, encoding="utf-8")
        return str(file_path)

    def retrieve(self, key: str) -> Any:
        """Read and deserialize the stored value for *key*.

        Returns ``None`` if the key does not exist.
        """
        file_path = self._path_for(key)
        if not file_path.exists():
            return None
        text = file_path.read_text(encoding="utf-8")
        return json.loads(text)

    def clear(self) -> None:
        """Remove all stored outputs.

        If the storage directory was auto-created it is deleted entirely
        and re-created so the object remains usable after ``clear()``.
        """
        if self._owns_dir:
            shutil.rmtree(self._dir, ignore_errors=True)
            self._dir.mkdir(parents=True, exist_ok=True)
        else:
            for file in self._dir.glob("*.json"):
                try:
                    file.unlink()
                except OSError:
                    pass

    def path_for(self, key: str) -> str:
        """Return the file path that *key* maps to (may not exist yet)."""
        return str(self._path_for(key))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _path_for(self, key: str) -> Path:
        # Sanitise key so it is safe as a filename.
        safe = key.replace(os.sep, "_").replace("/", "_").replace("\\", "_")
        return self._dir / f"{safe}.json"

    def __repr__(self) -> str:  # pragma: no cover
        return f"McpOutputStorage(dir={self._dir!r})"


# ---------------------------------------------------------------------------
# Format / size helpers (ported from getLargeOutputInstructions etc.)
# ---------------------------------------------------------------------------

def get_large_output_instructions(
    raw_output_path: str,
    content_length: int,
    format_description: str,
    max_read_length: int | None = None,
) -> str:
    """Return instruction text telling the model to read from *raw_output_path*."""
    base = (
        f"Error: result ({content_length:,} characters) exceeds maximum allowed "
        f"tokens. Output has been saved to {raw_output_path}.\n"
        f"Format: {format_description}\n"
        "Use offset and limit parameters to read specific portions of the file, "
        "search within it for specific content, and jq to make structured queries.\n"
        "REQUIREMENTS FOR SUMMARIZATION/ANALYSIS/REVIEW:\n"
        f"- You MUST read the content from the file at {raw_output_path} in "
        "sequential chunks until 100% of the content has been read.\n"
    )

    if max_read_length is not None:
        truncation = (
            f"- If you receive truncation warnings when reading the file "
            f'("[N lines truncated]"), reduce the chunk size until you have read '
            f"100% of the content without truncation ***DO NOT PROCEED UNTIL YOU "
            f"HAVE DONE THIS***. Bash output is limited to "
            f"{max_read_length:,} chars.\n"
        )
    else:
        truncation = (
            "- If you receive truncation warnings when reading the file, reduce "
            "the chunk size until you have read 100% of the content without "
            "truncation.\n"
        )

    completion = (
        "- Before producing ANY summary or analysis, you MUST explicitly describe "
        "what portion of the content you have read. ***If you did not read the "
        "entire content, you MUST explicitly state this.***\n"
    )

    return base + truncation + completion
