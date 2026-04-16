# 原始 TS: tools/FileMoveTool (推断，源码中未独立存在；对应 mv 语义)
"""
FileMoveTool — 移动或重命名文件/目录。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ..tool import Tool as ToolBase, ToolUseContext
ToolResult = dict  # compat alias


class FileMoveTool(ToolBase):
    """Move or rename a file or directory."""

    name: str = "FileMove"
    description: str = (
        "Move or rename a file or directory. The destination path must not "
        "already exist unless overwrite is set to true."
    )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
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

    def run(
        self,
        source: str,
        destination: str,
        overwrite: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        src = Path(source)
        dst = Path(destination)

        if not src.exists():
            return ToolResult(
                content=[{"type": "text", "text": f"Error: Source not found: {source}"}],
                is_error=True,
            )

        if dst.exists() and not overwrite:
            return ToolResult(
                content=[
                    {
                        "type": "text",
                        "text": f"Error: Destination already exists: {destination}. "
                                "Set overwrite=true to replace it.",
                    }
                ],
                is_error=True,
            )

        try:
            # Ensure parent directory exists
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        except (OSError, shutil.Error) as e:
            return ToolResult(
                content=[{"type": "text", "text": f"Error moving file: {e}"}],
                is_error=True,
            )

        return ToolResult(
            content=[
                {
                    "type": "text",
                    "text": f"Moved: {source} → {destination}",
                }
            ]
        )
