"""
Grep tool implementation
原始 TS: src/tools/GrepTool/GrepTool.ts

Uses ripgrep (rg) for content search. Falls back to Python if rg not available.
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
from pathlib import Path
from typing import Any, Literal, Optional

from claude_code.constants.tools import GREP_TOOL_NAME, AGENT_TOOL_NAME, BASH_TOOL_NAME
from claude_code.tool import Tool, ToolInputJSONSchema, ToolUseContext, ValidationResult, ValidationResultFail, ValidationResultOk
from claude_code.utils.shell import exec_command

# VCS directories to exclude
_VCS_DIRS = {"git", ".svn", ".hg", ".bzr", ".jj"}

DEFAULT_HEAD_LIMIT = 250

OutputMode = Literal["content", "files_with_matches", "count"]


def _has_ripgrep() -> bool:
    return shutil.which("rg") is not None


async def _run_ripgrep(
    pattern: str,
    path: str,
    *,
    glob: Optional[str] = None,
    output_mode: OutputMode = "files_with_matches",
    before: int = 0,
    after: int = 0,
    context: int = 0,
    line_numbers: bool = True,
    case_insensitive: bool = False,
    file_type: Optional[str] = None,
    head_limit: int = DEFAULT_HEAD_LIMIT,
    offset: int = 0,
    multiline: bool = False,
) -> str:
    """Run ripgrep and return its output."""
    cmd_parts = ["rg"]

    if case_insensitive:
        cmd_parts.append("-i")
    if multiline:
        cmd_parts.extend(["-U", "--multiline-dotall"])

    # Output mode flags
    if output_mode == "files_with_matches":
        cmd_parts.append("-l")
    elif output_mode == "count":
        cmd_parts.append("-c")
    elif output_mode == "content":
        if line_numbers:
            cmd_parts.append("-n")
        if context:
            cmd_parts.extend(["-C", str(context)])
        else:
            if before:
                cmd_parts.extend(["-B", str(before)])
            if after:
                cmd_parts.extend(["-A", str(after)])

    # File type filter
    if file_type:
        cmd_parts.extend(["--type", file_type])
    if glob:
        cmd_parts.extend(["--glob", glob])

    # Exclude VCS dirs
    for vcs in _VCS_DIRS:
        cmd_parts.extend(["--glob", f"!{vcs}/**"])

    cmd_parts.extend(["--", pattern, path])

    full_cmd = " ".join(f"'{p}'" if " " in p else p for p in cmd_parts)
    result = await exec_command(full_cmd, timeout_ms=30_000)

    lines = result.stdout.splitlines()
    if offset:
        lines = lines[offset:]
    if head_limit > 0:
        lines = lines[:head_limit]
    return "\n".join(lines)


async def _fallback_grep(
    pattern: str,
    path: str,
    *,
    glob: Optional[str] = None,
    output_mode: OutputMode = "files_with_matches",
    case_insensitive: bool = False,
    head_limit: int = DEFAULT_HEAD_LIMIT,
    offset: int = 0,
) -> str:
    """Python fallback when ripgrep is not available."""
    try:
        flags = re.IGNORECASE if case_insensitive else 0
        regex = re.compile(pattern, flags)
    except re.error as e:
        return f"Error: invalid regex pattern: {e}"

    matches: list[str] = []

    # Build file list
    if os.path.isfile(path):
        files = [path]
    else:
        files = []
        for root, dirs, fnames in os.walk(path):
            # Exclude VCS dirs
            dirs[:] = [d for d in dirs if d not in _VCS_DIRS]
            for fname in fnames:
                full = os.path.join(root, fname)
                if glob:
                    import fnmatch
                    if not fnmatch.fnmatch(fname, glob.lstrip("*/")):
                        continue
                files.append(full)

    matched_files: list[str] = []
    counts: dict[str, int] = {}

    for file_path in files:
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            continue

        file_matches = list(regex.finditer(content))
        if not file_matches:
            continue

        matched_files.append(file_path)
        counts[file_path] = len(file_matches)

        if output_mode == "content":
            for i, line in enumerate(content.splitlines(), 1):
                if regex.search(line):
                    matches.append(f"{file_path}:{i}:{line}")

    if output_mode == "files_with_matches":
        result_lines = matched_files
    elif output_mode == "count":
        result_lines = [f"{fp}:{cnt}" for fp, cnt in counts.items()]
    else:
        result_lines = matches

    result_lines = result_lines[offset:]
    if head_limit > 0:
        result_lines = result_lines[:head_limit]
    return "\n".join(result_lines)


class GrepTool(Tool):
    """
    Search file contents using ripgrep or Python regex fallback.
    原始 TS: src/tools/GrepTool/GrepTool.ts
    """

    name = GREP_TOOL_NAME
    search_hint = "search file contents with regex"
    max_result_size_chars = 200_000

    async def description(self) -> str:
        return "A powerful search tool built on ripgrep"

    async def prompt(self) -> str:
        return f"""A powerful search tool built on ripgrep

Usage:
- ALWAYS use {GREP_TOOL_NAME} for search tasks. NEVER invoke `grep` or `rg` as a {BASH_TOOL_NAME} command.
- Supports full regex syntax (e.g., "log.*Error", "function\\s+\\w+")
- Filter files with glob parameter (e.g., "*.js", "**/*.tsx") or type parameter (e.g., "js", "py", "rust")
- Output modes: "content" shows matching lines, "files_with_matches" shows only file paths (default), "count" shows match counts
- Use {AGENT_TOOL_NAME} tool for open-ended searches requiring multiple rounds
"""

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The regular expression pattern to search for in file contents",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory to search in. Defaults to current working directory.",
                },
                "glob": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g. '*.js', '*.{ts,tsx}')",
                },
                "output_mode": {
                    "type": "string",
                    "enum": ["content", "files_with_matches", "count"],
                    "description": "Output mode: 'content' shows matching lines, 'files_with_matches' shows file paths, 'count' shows match counts. Defaults to 'files_with_matches'.",
                },
                "-B": {"type": "integer", "description": "Lines before match"},
                "-A": {"type": "integer", "description": "Lines after match"},
                "-C": {"type": "integer", "description": "Lines around match"},
                "context": {"type": "integer", "description": "Lines around match"},
                "-n": {"type": "boolean", "description": "Show line numbers"},
                "-i": {"type": "boolean", "description": "Case insensitive search"},
                "type": {
                    "type": "string",
                    "description": "File type to search (e.g. js, py, rust)",
                },
                "head_limit": {
                    "type": "integer",
                    "description": f"Limit output to first N lines. Defaults to {DEFAULT_HEAD_LIMIT}.",
                },
                "offset": {
                    "type": "integer",
                    "description": "Skip first N lines/entries",
                },
                "multiline": {
                    "type": "boolean",
                    "description": "Enable multiline mode",
                },
            },
            "required": ["pattern"],
        }

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        pattern: str = input_data["pattern"]
        path: str = os.path.expanduser(input_data.get("path") or os.getcwd())
        glob: Optional[str] = input_data.get("glob")
        output_mode: OutputMode = input_data.get("output_mode", "files_with_matches")  # type: ignore
        before = int(input_data.get("-B") or 0)
        after = int(input_data.get("-A") or 0)
        ctx = int(input_data.get("-C") or input_data.get("context") or 0)
        line_numbers = bool(input_data.get("-n", True))
        case_insensitive = bool(input_data.get("-i", False))
        file_type: Optional[str] = input_data.get("type")
        head_limit = int(input_data.get("head_limit") or DEFAULT_HEAD_LIMIT)
        offset = int(input_data.get("offset") or 0)
        multiline = bool(input_data.get("multiline", False))

        if _has_ripgrep():
            result = await _run_ripgrep(
                pattern,
                path,
                glob=glob,
                output_mode=output_mode,
                before=before,
                after=after,
                context=ctx,
                line_numbers=line_numbers,
                case_insensitive=case_insensitive,
                file_type=file_type,
                head_limit=head_limit,
                offset=offset,
                multiline=multiline,
            )
        else:
            result = await _fallback_grep(
                pattern,
                path,
                glob=glob,
                output_mode=output_mode,
                case_insensitive=case_insensitive,
                head_limit=head_limit,
                offset=offset,
            )

        if not result:
            return {"type": "text", "text": "No matches found."}
        return {"type": "text", "text": result}

    def user_facing_name(self, input_data: Optional[dict[str, Any]] = None) -> str:
        if input_data:
            pattern = input_data.get("pattern", "")
            path = input_data.get("path", "")
            if path:
                return f"{pattern} in {path}"
            return pattern
        return "search"

    def get_tool_use_summary(self, input_data: dict[str, Any]) -> Optional[str]:
        return input_data.get("pattern", "")
