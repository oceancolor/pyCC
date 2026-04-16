"""
GrepTool — regex search via ripgrep or Python fallback.
Ported from GrepTool/GrepTool.ts (577 lines → core).
"""
from __future__ import annotations
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

from claude_code.tools.grep_tool.prompt import GREP_TOOL_NAME

MAX_RESULTS = 1000


class GrepTool:
    name = GREP_TOOL_NAME
    description = "Search file contents using regex patterns."
    is_read_only = True

    async def call(
        self,
        pattern: str,
        path: Optional[str] = None,
        glob: Optional[str] = None,
        output_mode: str = "files_with_matches",
        context_before: int = 0,
        context_after: int = 0,
        case_insensitive: bool = False,
        head_limit: Optional[int] = None,
        context: Any = None,
        **kwargs,
    ) -> dict:
        base = os.path.abspath(os.path.expanduser(path)) if path else os.getcwd()

        # Try ripgrep first
        try:
            return self._rg_search(pattern, base, glob, output_mode,
                                   context_before, context_after,
                                   case_insensitive, head_limit)
        except FileNotFoundError:
            # rg not found, fall back to Python
            return self._python_search(pattern, base, glob, output_mode,
                                       case_insensitive, head_limit)

    def _rg_search(self, pattern, base, glob, output_mode,
                   ctx_before, ctx_after, case_insensitive, head_limit) -> dict:
        cmd = ["rg", "--no-heading"]
        if output_mode == "files_with_matches":
            cmd.append("-l")
        elif output_mode == "count":
            cmd.append("-c")
        else:  # content
            if ctx_before:
                cmd += ["-B", str(ctx_before)]
            if ctx_after:
                cmd += ["-A", str(ctx_after)]
            cmd.append("-n")
        if case_insensitive:
            cmd.append("-i")
        if glob:
            cmd += ["--glob", glob]
        if head_limit:
            cmd += ["--max-count", str(head_limit)]
        cmd += [pattern, str(base)]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        lines = [l for l in result.stdout.splitlines() if l]
        truncated = len(lines) > MAX_RESULTS
        lines = lines[:MAX_RESULTS]
        return {"type": "success", "output": "\n".join(lines),
                "num_matches": len(lines), "truncated": truncated}

    def _python_search(self, pattern, base, glob_pattern, output_mode,
                       case_insensitive, head_limit) -> dict:
        flags = re.IGNORECASE if case_insensitive else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return {"type": "error", "error": f"Invalid regex: {e}"}

        import fnmatch
        results = []
        count = 0

        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fname in files:
                if glob_pattern and not fnmatch.fnmatch(fname, glob_pattern.lstrip("**/")):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        file_lines = f.readlines()
                    for i, line in enumerate(file_lines):
                        if regex.search(line):
                            if output_mode == "files_with_matches":
                                results.append(fpath)
                                break
                            elif output_mode == "content":
                                results.append(f"{fpath}:{i+1}:{line.rstrip()}")
                            count += 1
                            if head_limit and count >= head_limit:
                                break
                except (OSError, UnicodeDecodeError):
                    continue
                if head_limit and count >= head_limit:
                    break
            if head_limit and count >= head_limit:
                break

        truncated = len(results) > MAX_RESULTS
        results = results[:MAX_RESULTS]
        return {"type": "success", "output": "\n".join(results),
                "num_matches": len(results), "truncated": truncated}
