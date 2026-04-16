"""
FileReadTool — reads text, images, notebooks, PDFs.
Ported from FileReadTool/FileReadTool.ts (1183 lines → core logic).
"""
from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

from claude_code.tools.file_read_tool.limits import get_default_file_reading_limits
from claude_code.tools.file_read_tool.prompt import FILE_READ_TOOL_NAME, MAX_LINES_TO_READ

BLOCKED_DEVICE_PATHS = {
    "/dev/zero", "/dev/random", "/dev/urandom", "/dev/full",
    "/dev/stdin", "/dev/tty", "/dev/console",
    "/dev/stdout", "/dev/stderr",
    "/dev/fd/0", "/dev/fd/1", "/dev/fd/2",
}

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


def is_blocked_device_path(path: str) -> bool:
    if path in BLOCKED_DEVICE_PATHS:
        return True
    if re.match(r"^/proc/.+/fd/[012]$", path):
        return True
    return False


class MaxFileReadTokenExceededError(Exception):
    def __init__(self, token_count: int, max_tokens: int):
        super().__init__(
            f"File content ({token_count} tokens) exceeds maximum allowed tokens ({max_tokens})."
        )
        self.token_count = token_count
        self.max_tokens = max_tokens


class FileReadTool:
    name = FILE_READ_TOOL_NAME
    description = "Read a file from the local filesystem."
    is_read_only = True

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the file"},
                "offset": {"type": "integer", "minimum": 1},
                "limit": {"type": "integer", "minimum": 1},
            },
            "required": ["file_path"],
        }

    async def call(self, input: Dict[str, Any], context: Any = None) -> dict:
        file_path = input.get("file_path", "")
        offset = input.get("offset")
        limit = input.get("limit")
        return await self._read(file_path, offset, limit)

    async def _read(self, file_path: str, offset: Optional[int], limit: Optional[int]) -> dict:
        path = os.path.abspath(os.path.expanduser(file_path))

        if is_blocked_device_path(path):
            return {"text": f"Error: Reading {file_path} is not allowed (blocked device)."}

        if not os.path.exists(path):
            return {"text": f"Error: File not found: {file_path}"}

        if os.path.isdir(path):
            return {"text": f"Error: {file_path} is a directory."}

        limits = get_default_file_reading_limits()
        file_size = os.path.getsize(path)
        if file_size > limits["max_size_bytes"]:
            return {"text": (
                f"Error: File is too large ({file_size:,} bytes). "
                "Use offset and limit to read specific portions."
            )}

        ext = Path(path).suffix.lstrip(".").lower()
        if ext in IMAGE_EXTENSIONS:
            return await self._read_image(path)
        if ext == "ipynb":
            return self._read_notebook(path)

        return self._read_text(path, offset, limit)

    def _read_text(self, path: str, offset: Optional[int], limit: Optional[int]) -> dict:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total_lines = len(lines)
        start = max(0, (offset or 1) - 1)
        end = min(total_lines, start + (limit or MAX_LINES_TO_READ))
        slice_lines = lines[start:end]

        # cat -n format
        numbered = "".join(
            f"{i + start + 1}\t{line}" for i, line in enumerate(slice_lines)
        )

        return {
            "text": numbered,
            "file_path": path,
            "num_lines": len(slice_lines),
            "start_line": start + 1,
            "total_lines": total_lines,
        }

    async def _read_image(self, path: str) -> dict:
        import base64
        ext = Path(path).suffix.lstrip(".").lower()
        mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "png": "image/png", "gif": "image/gif", "webp": "image/webp"}
        mime = mime_map.get(ext, "image/png")
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        return {"text": f"[Image: {path}]", "base64": data,
                "mime_type": mime, "original_size": os.path.getsize(path)}

    def _read_notebook(self, path: str) -> dict:
        import json
        with open(path, "r", encoding="utf-8") as f:
            nb = json.load(f)
        cells = nb.get("cells", [])
        text = "\n\n".join(
            f"[{c.get('cell_type', 'code')}]\n{''.join(c.get('source', []))}"
            for c in cells
        )
        return {"text": text, "file_path": path, "cells": cells}
