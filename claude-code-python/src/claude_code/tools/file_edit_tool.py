"""
File Edit tool implementation
原始 TS: src/tools/FileEditTool/FileEditTool.ts

Finds and replaces text in files using exact string matching.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

from claude_code.constants.tools import FILE_EDIT_TOOL_NAME, FILE_READ_TOOL_NAME
from claude_code.tool import Tool, ToolInputJSONSchema, ToolUseContext, ValidationResult, ValidationResultFail, ValidationResultOk
from claude_code.utils.file import get_file_modification_time, write_text_content

FILE_UNEXPECTEDLY_MODIFIED_ERROR = (
    "File was unexpectedly modified between reading and editing. "
    "Please re-read the file before editing."
)

# Curly quote normalization
_QUOTE_MAP: list[tuple[str, str]] = [
    ("\u2018", "'"),  # LEFT_SINGLE_CURLY_QUOTE
    ("\u2019", "'"),  # RIGHT_SINGLE_CURLY_QUOTE
    ("\u201C", '"'),  # LEFT_DOUBLE_CURLY_QUOTE
    ("\u201D", '"'),  # RIGHT_DOUBLE_CURLY_QUOTE
]


def _normalize_quotes(s: str) -> str:
    """Normalize curly quotes to straight quotes."""
    for curly, straight in _QUOTE_MAP:
        s = s.replace(curly, straight)
    return s


def _find_actual_string(file_content: str, search_string: str) -> Optional[str]:
    """
    Find the actual string in file_content that matches search_string,
    accounting for quote normalization.
    Returns the actual string in the file, or None if not found.
    原始 TS: findActualString
    """
    # Exact match
    if search_string in file_content:
        return search_string

    # Quote-normalized match
    normalized = _normalize_quotes(search_string)
    if normalized in file_content:
        return normalized

    # Try normalizing file content quotes too
    norm_content = _normalize_quotes(file_content)
    if search_string in norm_content or normalized in norm_content:
        # Find the original text in the file at the same position
        idx = norm_content.find(normalized if normalized else search_string)
        if idx >= 0:
            return file_content[idx: idx + len(search_string)]

    return None


def _apply_edit(
    file_content: str,
    old_string: str,
    new_string: str,
) -> Optional[str]:
    """
    Apply a single string replacement.
    Returns new file content, or None if old_string not found.
    """
    actual = _find_actual_string(file_content, old_string)
    if actual is None:
        return None
    return file_content.replace(actual, new_string, 1)


class FileEditTool(Tool):
    """
    Edit a file by replacing exact text.
    原始 TS: src/tools/FileEditTool/FileEditTool.ts
    """

    name = FILE_EDIT_TOOL_NAME
    search_hint = "modify file contents in place"
    max_result_size_chars = 100_000

    async def description(self) -> str:
        return "A tool for editing files"

    async def prompt(self) -> str:
        return f"""A tool for editing files. It replaces a specified string in the file with a new string.

Usage:
- The file_path parameter must be an absolute path
- The old_string parameter must exactly match the text you want to replace (including whitespace and indentation)
- The new_string parameter is the replacement text
- If old_string appears multiple times in the file, only the FIRST occurrence will be replaced
- The file must be read with the {FILE_READ_TOOL_NAME} tool before editing

Important:
- Make sure to preserve the correct indentation in new_string
- NEVER replace with an empty new_string to delete content — use a proper replacement instead
- The file must already exist; this tool cannot create new files (use Write for that)"""

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The absolute path to the file to edit",
                },
                "old_string": {
                    "type": "string",
                    "description": "The text to replace (must be an exact match)",
                },
                "new_string": {
                    "type": "string",
                    "description": "The replacement text",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        }

    async def validate_input(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> ValidationResult:
        file_path = input_data.get("file_path", "")
        if not file_path or not os.path.isabs(file_path):
            return ValidationResultFail(
                result=False,
                message="file_path must be an absolute path",
                error_code=1,
            )
        if "old_string" not in input_data:
            return ValidationResultFail(
                result=False, message="old_string is required", error_code=1
            )
        if "new_string" not in input_data:
            return ValidationResultFail(
                result=False, message="new_string is required", error_code=1
            )
        return ValidationResultOk()

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        file_path: str = os.path.expanduser(input_data["file_path"])
        old_string: str = input_data["old_string"]
        new_string: str = input_data["new_string"]

        # File must exist
        if not os.path.exists(file_path):
            return {
                "type": "text",
                "text": f"Error: File not found: {file_path}",
            }

        if os.path.isdir(file_path):
            return {
                "type": "text",
                "text": f"Error: {file_path} is a directory",
            }

        # Read current content
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as e:
            return {"type": "text", "text": f"Error reading file: {e}"}

        # Apply edit
        new_content = _apply_edit(content, old_string, new_string)
        if new_content is None:
            # Provide helpful context: count occurrences of old_string
            # (possibly after normalization)
            norm_old = _normalize_quotes(old_string)
            norm_content = _normalize_quotes(content)
            occurrences = norm_content.count(norm_old)
            if occurrences == 0:
                hint = "The old_string was not found in the file. Make sure you are using an exact match."
            else:
                hint = f"old_string was found {occurrences} time(s). Use a more specific string."
            return {
                "type": "text",
                "text": f"Error: {hint}\n\nSearched for:\n{old_string}",
            }

        # Write updated content
        try:
            write_text_content(file_path, new_content)
        except OSError as e:
            return {"type": "text", "text": f"Error writing file: {e}"}

        # Return diff summary
        old_lines = content.count("\n")
        new_lines = new_content.count("\n")
        diff = new_lines - old_lines
        sign = "+" if diff >= 0 else ""
        return {
            "type": "text",
            "text": (
                f"Successfully edited {file_path}\n"
                f"Lines: {old_lines} → {new_lines} ({sign}{diff})"
            ),
        }

    def user_facing_name(self, input_data: Optional[dict[str, Any]] = None) -> str:
        if input_data and "file_path" in input_data:
            return input_data["file_path"]
        return "file"

    def get_tool_use_summary(self, input_data: dict[str, Any]) -> Optional[str]:
        return input_data.get("file_path", "")
