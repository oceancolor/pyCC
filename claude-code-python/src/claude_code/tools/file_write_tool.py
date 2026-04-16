"""
File Write tool implementation
原始 TS: src/tools/FileWriteTool/FileWriteTool.ts

Creates or overwrites files on the filesystem.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from claude_code.constants.tools import FILE_WRITE_TOOL_NAME, FILE_READ_TOOL_NAME
from claude_code.tool import Tool, ToolInputJSONSchema, ToolUseContext, ValidationResult, ValidationResultFail, ValidationResultOk
from claude_code.utils.file import write_text_content


class FileWriteTool(Tool):
    """
    Writes a file to the local filesystem.
    原始 TS: src/tools/FileWriteTool/FileWriteTool.ts
    """

    name = FILE_WRITE_TOOL_NAME
    search_hint = "create or overwrite files"
    max_result_size_chars = 100_000

    async def description(self) -> str:
        return "Write a file to the local filesystem."

    async def prompt(self) -> str:
        return f"""Writes a file to the local filesystem.

Usage:
- This tool will overwrite the existing file if there is one at the provided path.
- If this is an existing file, you MUST use the {FILE_READ_TOOL_NAME} tool first to read the file's contents. This tool will fail if you did not read the file first.
- Prefer the Edit tool for modifying existing files — it only sends the diff. Only use this tool to create new files or for complete rewrites.
- NEVER create documentation files (*.md) or README files unless explicitly requested by the User.
- Only use emojis if the user explicitly requests it. Avoid writing emojis to files unless asked."""

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The absolute path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file",
                },
            },
            "required": ["file_path", "content"],
        }

    async def validate_input(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> ValidationResult:
        file_path = input_data.get("file_path", "")
        if not file_path or not isinstance(file_path, str):
            return ValidationResultFail(
                result=False, message="file_path must be a non-empty string", error_code=1
            )
        if not os.path.isabs(file_path):
            return ValidationResultFail(
                result=False,
                message=f"file_path must be an absolute path, got: {file_path}",
                error_code=1,
            )
        if "content" not in input_data:
            return ValidationResultFail(
                result=False, message="content is required", error_code=1
            )
        return ValidationResultOk()

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        file_path: str = os.path.expanduser(input_data["file_path"])
        content: str = input_data["content"]

        # Create parent directories if needed
        parent = os.path.dirname(file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        try:
            write_text_content(file_path, content)
        except OSError as e:
            return {"type": "text", "text": f"Error writing file: {e}"}

        num_lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        return {
            "type": "text",
            "text": f"Successfully wrote {file_path} ({num_lines} lines)",
        }

    def user_facing_name(self, input_data: Optional[dict[str, Any]] = None) -> str:
        if input_data and "file_path" in input_data:
            return input_data["file_path"]
        return "file"

    def get_tool_use_summary(self, input_data: dict[str, Any]) -> Optional[str]:
        return input_data.get("file_path", "")
