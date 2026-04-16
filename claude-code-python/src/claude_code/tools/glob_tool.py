"""
Glob tool implementation
原始 TS: src/tools/GlobTool/GlobTool.ts

Fast file pattern matching sorted by modification time.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from claude_code.constants.tools import GLOB_TOOL_NAME
from claude_code.tool import Tool, ToolInputJSONSchema, ToolUseContext, ValidationResult, ValidationResultFail, ValidationResultOk

_MAX_RESULTS = 100

DESCRIPTION = """- Fast file pattern matching tool that works with any codebase size
- Supports glob patterns like "**/*.js" or "src/**/*.ts"
- Returns matching file paths sorted by modification time
- Use this tool when you need to find files by name patterns
- When you are doing an open ended search that may require multiple rounds of globbing and grepping, use the Agent tool instead"""


@dataclass
class GlobOutput:
    duration_ms: float
    num_files: int
    filenames: list[str]
    truncated: bool


async def _glob_files(pattern: str, base_path: str) -> GlobOutput:
    """Perform glob search and return results sorted by mtime."""
    start = time.monotonic()

    base = Path(base_path)
    try:
        matches = list(base.glob(pattern))
    except (ValueError, OSError) as e:
        return GlobOutput(
            duration_ms=0,
            num_files=0,
            filenames=[],
            truncated=False,
        )

    # Only files (not dirs)
    file_matches = [m for m in matches if m.is_file()]

    # Sort by mtime descending (most recently modified first)
    def _mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    file_matches.sort(key=_mtime, reverse=True)

    truncated = len(file_matches) > _MAX_RESULTS
    if truncated:
        file_matches = file_matches[:_MAX_RESULTS]

    duration = (time.monotonic() - start) * 1000

    return GlobOutput(
        duration_ms=duration,
        num_files=len(file_matches),
        filenames=[str(m) for m in file_matches],
        truncated=truncated,
    )


class GlobTool(Tool):
    """
    Fast file pattern matching by glob pattern.
    原始 TS: src/tools/GlobTool/GlobTool.ts
    """

    name = GLOB_TOOL_NAME
    search_hint = "find files by name pattern or wildcard"
    max_result_size_chars = 100_000

    async def description(self) -> str:
        return DESCRIPTION

    async def prompt(self) -> str:
        return DESCRIPTION

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The glob pattern to match files against (e.g. '**/*.ts', 'src/**/*.py')",
                },
                "path": {
                    "type": "string",
                    "description": (
                        "The directory to search in. If not specified, the current working "
                        "directory will be used. Must be a valid directory path if provided."
                    ),
                },
            },
            "required": ["pattern"],
        }

    async def validate_input(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> ValidationResult:
        pattern = input_data.get("pattern", "")
        if not pattern or not isinstance(pattern, str):
            return ValidationResultFail(
                result=False, message="pattern must be a non-empty string", error_code=1
            )
        path = input_data.get("path")
        if path is not None:
            expanded = os.path.expanduser(path)
            if not os.path.isdir(expanded):
                return ValidationResultFail(
                    result=False,
                    message=f"path is not a valid directory: {path}",
                    error_code=1,
                )
        return ValidationResultOk()

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        pattern: str = input_data["pattern"]
        path = input_data.get("path") or os.getcwd()
        path = os.path.expanduser(path)

        result = await _glob_files(pattern, path)

        lines: list[str] = []
        for fname in result.filenames:
            lines.append(fname)

        if result.truncated:
            lines.append(f"(results truncated to {_MAX_RESULTS} files)")

        if not lines:
            return {"type": "text", "text": "No files found matching the pattern."}

        text = "\n".join(lines)
        return {
            "type": "text",
            "text": text,
            "metadata": {
                "duration_ms": result.duration_ms,
                "num_files": result.num_files,
                "truncated": result.truncated,
            },
        }

    def user_facing_name(self, input_data: Optional[dict[str, Any]] = None) -> str:
        if input_data:
            pattern = input_data.get("pattern", "")
            path = input_data.get("path", "")
            if path:
                return f"{pattern} in {path}"
            return pattern
        return "glob"

    def get_tool_use_summary(self, input_data: dict[str, Any]) -> Optional[str]:
        return input_data.get("pattern", "")
