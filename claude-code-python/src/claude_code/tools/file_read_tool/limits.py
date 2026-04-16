"""File read limits. Ported from FileReadTool/limits.ts"""
from __future__ import annotations
import os
from typing import Optional, TypedDict

DEFAULT_MAX_OUTPUT_TOKENS = 25_000
MAX_OUTPUT_SIZE_BYTES = 256 * 1024  # 256 KB


class FileReadingLimits(TypedDict, total=False):
    max_tokens: int
    max_size_bytes: int
    include_max_size_in_prompt: Optional[bool]
    targeted_range_nudge: Optional[bool]


_limits_cache: Optional[FileReadingLimits] = None


def get_default_file_reading_limits() -> FileReadingLimits:
    global _limits_cache
    if _limits_cache is not None:
        return _limits_cache
    env_max = os.environ.get("CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS")
    max_tokens = DEFAULT_MAX_OUTPUT_TOKENS
    if env_max:
        try:
            parsed = int(env_max)
            if parsed > 0:
                max_tokens = parsed
        except ValueError:
            pass
    _limits_cache = {
        "max_tokens": max_tokens,
        "max_size_bytes": MAX_OUTPUT_SIZE_BYTES,
    }
    return _limits_cache
