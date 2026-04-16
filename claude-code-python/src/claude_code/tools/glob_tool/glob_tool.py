"""GlobTool — fast file pattern matching."""
from __future__ import annotations
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from claude_code.tools.glob_tool.prompt import GLOB_TOOL_NAME

MAX_RESULTS = 100


class GlobTool:
    name = GLOB_TOOL_NAME
    description = "Find files by name pattern or wildcard."
    is_read_only = True

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["pattern"],
        }

    async def call(self, input: Dict[str, Any], context: Any = None) -> dict:
        pattern = input.get("pattern", "*")
        base_path = input.get("path")
        start = time.monotonic()
        base = os.path.abspath(os.path.expanduser(base_path)) if base_path else os.getcwd()

        if not os.path.isdir(base):
            return {"text": f"Error: Directory not found: {base}"}

        if "**" in pattern:
            sub = pattern.split("**/", 1)[-1] if "**/" in pattern else "*"
            matches = list(Path(base).rglob(sub))
        else:
            matches = list(Path(base).glob(pattern))

        file_matches = [m for m in matches if m.is_file()]
        file_matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        truncated = len(file_matches) > MAX_RESULTS
        file_matches = file_matches[:MAX_RESULTS]
        filenames = [str(m) for m in file_matches]

        duration_ms = int((time.monotonic() - start) * 1000)
        text = "\n".join(filenames)
        return {
            "text": text,
            "duration_ms": duration_ms,
            "num_files": len(filenames),
            "filenames": filenames,
            "truncated": truncated,
        }
