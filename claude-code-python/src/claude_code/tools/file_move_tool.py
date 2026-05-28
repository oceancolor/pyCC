# 原始 TS: tools/FileMoveTool (推断，源码中未独立存在；对应 mv 语义)
"""
FileMoveTool — 移动或重命名文件/目录。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ..tool import Tool as ToolBase, ToolInputJSONSchema, ToolUseContext

ToolResult = dict  # compat alias

_DESCRIPTION = (
    "Move or rename a file or directory. The destination path must not "
    "already exist unless overwrite is set to true."
)

_PROMPT = """\
Move or rename a file or directory on the local filesystem.

Usage:
- Both source and destination must be absolute paths.
- If the destination already exists the tool will return an error unless \
overwrite is set to true.
- Parent directories of the destination are created automatically.
- Works for both files and directories."""

_INPUT_SCHEMA: ToolInputJSONSchema = {
    "type": "object",
    "properties": {
        "source": {
            "type": "string",
            "description": "The absolute path of the source file or directory.",
        },
        "destination": {
            "type": "string",
            "description": "The absolute path of the destination.",
        },
        "overwrite": {
            "type": "boolean",
            "description": "If true, overwrite destination if it exists. Default false.",
            "default": False,
        },
    },
    "required": ["source", "destination"],
}


class FileMoveTool(ToolBase):
    """Move or rename a file or directory."""

    name = "FileMove"
    search_hint = "move rename file directory"

    # ── Abstract method implementations ──────────────────────────────────

    async def description(self) -> str:
        return _DESCRIPTION

    async def prompt(self) -> str:
        return _PROMPT

    def input_schema(self) -> ToolInputJSONSchema:
        return _INPUT_SCHEMA

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        source: str = input_data["source"]
        destination: str = input_data["destination"]
        overwrite: bool = input_data.get("overwrite", False)

        src = Path(source)
        dst = Path(destination)

        if not src.exists():
            return {"type": "text", "text": f"Error: Source not found: {source}", "is_error": True}

        if dst.exists() and not overwrite:
            return {
                "type": "text",
                "text": (
                    f"Error: Destination already exists: {destination}. "
                    "Set overwrite=true to replace it."
                ),
                "is_error": True,
            }

        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        except (OSError, shutil.Error) as e:
            return {"type": "text", "text": f"Error moving file: {e}", "is_error": True}

        return {"type": "text", "text": f"Moved: {source} → {destination}"}
