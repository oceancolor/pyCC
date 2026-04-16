"""FileWriteTool — create or overwrite files."""
from __future__ import annotations
import os
from typing import Any, Dict

from claude_code.tools.file_write_tool.prompt import FILE_WRITE_TOOL_NAME


class FileWriteTool:
    name = FILE_WRITE_TOOL_NAME
    description = "Write a file to the local filesystem."
    is_read_only = False

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["file_path", "content"],
        }

    async def call(self, input: Dict[str, Any], context: Any = None) -> dict:
        file_path = input.get("file_path", "")
        content = input.get("content", "")

        path = os.path.abspath(os.path.expanduser(file_path))
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        existed = os.path.exists(path)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        verb = "wrote" if existed else "created"
        return {"text": f"Successfully wrote {file_path} ({lines} lines)"}
