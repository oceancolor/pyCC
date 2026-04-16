"""
File Read tool implementation
原始 TS: src/tools/FileReadTool/FileReadTool.ts

Reads files from the filesystem, supports image viewing, PDF, notebooks.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any, Optional

from claude_code.constants.files import has_binary_extension, is_binary_content
from claude_code.constants.tools import FILE_READ_TOOL_NAME, BASH_TOOL_NAME
from claude_code.tool import Tool, ToolInputJSONSchema, ToolUseContext, ValidationResult, ValidationResultFail, ValidationResultOk
from claude_code.utils.file import add_line_numbers, FILE_NOT_FOUND_CWD_NOTE

MAX_LINES_TO_READ = 2000
FILE_UNCHANGED_STUB = (
    "File unchanged since last read. The content from the earlier Read tool_result "
    "in this conversation is still current — refer to that instead of re-reading."
)

# Device files that would hang the process
_BLOCKED_DEVICE_PATHS = frozenset({
    "/dev/zero", "/dev/random", "/dev/urandom", "/dev/full",
    "/dev/stdin", "/dev/tty", "/dev/console",
    "/dev/stdout", "/dev/stderr",
    "/dev/fd/0", "/dev/fd/1", "/dev/fd/2",
})


def _is_blocked_device_path(file_path: str) -> bool:
    if file_path in _BLOCKED_DEVICE_PATHS:
        return True
    if file_path.startswith("/proc/") and file_path.endswith(("/fd/0", "/fd/1", "/fd/2")):
        return True
    return False


IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"})
IMAGE_MIME_MAP = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


class FileReadTool(Tool):
    """
    Reads a file from the local filesystem.
    原始 TS: src/tools/FileReadTool/FileReadTool.ts
    """

    name = FILE_READ_TOOL_NAME
    search_hint = "read file contents"
    max_result_size_chars = 2_000_000

    async def description(self) -> str:
        return "Read a file from the local filesystem."

    async def prompt(self) -> str:
        return f"""Reads a file from the local filesystem. You can access any file directly by using this tool.
Assume this tool is able to read all files on the machine. If the User provides a path to a file assume that path is valid. It is okay to read a file that does not exist; an error will be returned.

Usage:
- The file_path parameter must be an absolute path, not a relative path
- By default, it reads up to {MAX_LINES_TO_READ} lines starting from the beginning of the file
- You can optionally specify a line offset and limit (especially handy for long files), but it's recommended to read the whole file by not providing these parameters
- Results are returned using cat -n format, with line numbers starting at 1
- This tool allows Claude Code to read images (eg PNG, JPG, etc). When reading an image file the contents are presented visually as Claude Code is a multimodal LLM.
- This tool can read Jupyter notebooks (.ipynb files) and returns all cells with their outputs, combining code, text, and visualizations.
- This tool can only read files, not directories. To read a directory, use an ls command via the {BASH_TOOL_NAME} tool.
- You will regularly be asked to read screenshots. If the user provides a path to a screenshot, ALWAYS use this tool to view the file at the path.
- If you read a file that exists but has empty contents you will receive a system reminder warning in place of file contents."""

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The absolute path to the file to read",
                },
                "offset": {
                    "type": "integer",
                    "description": "The line number to start reading from (1-indexed)",
                },
                "limit": {
                    "type": "integer",
                    "description": f"The number of lines to read (max {MAX_LINES_TO_READ})",
                },
            },
            "required": ["file_path"],
        }

    async def validate_input(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> ValidationResult:
        file_path = input_data.get("file_path", "")
        if not file_path or not isinstance(file_path, str):
            return ValidationResultFail(result=False, message="file_path must be a non-empty string", error_code=1)
        if not os.path.isabs(file_path):
            return ValidationResultFail(
                result=False,
                message=f"file_path must be an absolute path, got: {file_path}",
                error_code=1,
            )
        return ValidationResultOk()

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> Any:
        file_path: str = input_data["file_path"]
        offset: Optional[int] = input_data.get("offset")
        limit: Optional[int] = input_data.get("limit")

        # Expand ~ in path
        file_path = os.path.expanduser(file_path)

        # Block dangerous device paths
        if _is_blocked_device_path(file_path):
            return {"type": "text", "text": f"Error: Cannot read device file: {file_path}"}

        # Check if file exists
        if not os.path.exists(file_path):
            msg = f"File not found: {file_path}\n{FILE_NOT_FOUND_CWD_NOTE}"
            return {"type": "text", "text": msg}

        # Check if directory
        if os.path.isdir(file_path):
            return {"type": "text", "text": f"Error: {file_path} is a directory, not a file. Use the Bash tool with 'ls' to list directory contents."}

        ext = Path(file_path).suffix.lower()

        # Image files → return as base64
        if ext in IMAGE_EXTENSIONS:
            try:
                with open(file_path, "rb") as f:
                    data = f.read()
                b64 = base64.b64encode(data).decode()
                mime = IMAGE_MIME_MAP.get(ext, "image/png")
                return {
                    "type": "image",
                    "source": {"type": "base64", "media_type": mime, "data": b64},
                }
            except OSError as e:
                return {"type": "text", "text": f"Error reading image: {e}"}

        # Binary files (non-image)
        if has_binary_extension(file_path):
            return {"type": "text", "text": f"Error: Cannot read binary file: {file_path}"}

        # Text file
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError as e:
            return {"type": "text", "text": f"Error reading file: {e}"}

        # Apply offset/limit
        start = (offset - 1) if offset and offset > 0 else 0
        end = start + (limit or MAX_LINES_TO_READ)
        selected = lines[start:end]

        if not selected:
            if not lines:
                return {"type": "text", "text": "(empty file)"}
            return {"type": "text", "text": f"No lines in range offset={offset}, limit={limit}"}

        content = "".join(selected)
        numbered = add_line_numbers(content, start=start + 1)

        return {"type": "text", "text": numbered}

    def user_facing_name(self, input_data: Optional[dict[str, Any]] = None) -> str:
        if input_data and "file_path" in input_data:
            return input_data["file_path"]
        return "file"

    def get_tool_use_summary(self, input_data: dict[str, Any]) -> Optional[str]:
        return input_data.get("file_path", "")
