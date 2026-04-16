"""
FileEditTool — exact string replacement in files.
"""
from __future__ import annotations
import os
from typing import Any, Dict

from claude_code.tools.file_edit_tool.constants import FILE_EDIT_TOOL_NAME
from claude_code.tools.file_edit_tool.utils import apply_edit

_file_mtimes: dict = {}


class FileEditTool:
    name = FILE_EDIT_TOOL_NAME
    description = "Performs exact string replacements in files."
    is_read_only = False

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "replace_all": {"type": "boolean"},
            },
            "required": ["file_path", "old_string", "new_string"],
        }

    async def call(self, input: Dict[str, Any], context: Any = None) -> dict:
        file_path = input.get("file_path", "")
        old_string = input.get("old_string", "")
        new_string = input.get("new_string", "")
        replace_all = bool(input.get("replace_all", False))

        path = os.path.abspath(os.path.expanduser(file_path))
        if not os.path.exists(path):
            return {"text": f"Error: File not found: {file_path}"}
        if not os.path.isfile(path):
            return {"text": f"Error: Not a file: {file_path}"}

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            original = f.read()

        try:
            new_content, count = apply_edit(original, old_string, new_string, replace_all)
        except ValueError as e:
            return {"text": f"Error: {e}"}

        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

        _file_mtimes[path] = os.path.getmtime(path)
        return {"text": f"Successfully edited {file_path} ({count} replacement(s))"}
