"""
BashTool output post-processing. Ported from BashTool/utils.ts (async image handling parts).
"""
from __future__ import annotations
import base64
import os
from typing import Optional, Tuple

from claude_code.tools.bash_tool.bash_utils import (
    parse_data_uri, is_image_output, strip_empty_lines, format_output
)

MAX_IMAGE_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


async def resize_shell_image_output(
    stdout: str,
    output_file_path: Optional[str] = None,
    output_file_size: Optional[int] = None,
) -> Optional[str]:
    """
    Re-read image from disk if output was truncated, then resize.
    Returns re-encoded data URI or None.
    """
    source = stdout
    if output_file_path:
        try:
            size = output_file_size or os.path.getsize(output_file_path)
            if size > MAX_IMAGE_FILE_SIZE:
                return None
            with open(output_file_path, 'r', encoding='utf-8') as f:
                source = f.read()
        except OSError:
            return None

    parsed = parse_data_uri(source)
    if not parsed:
        return None
    media_type, data = parsed
    # Stub: no resize — return as-is (imageResizer not ported)
    return f"data:{media_type};base64,{data}"


def build_image_tool_result(stdout: str, tool_use_id: str) -> Optional[dict]:
    """Build an image tool_result block from stdout containing a data URI."""
    parsed = parse_data_uri(stdout)
    if not parsed:
        return None
    media_type, data = parsed
    return {
        "tool_use_id": tool_use_id,
        "type": "tool_result",
        "content": [{
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": data}
        }]
    }


def stderr_append_shell_reset_message(stderr: str, original_cwd: str = "") -> str:
    return f"{stderr.rstrip()}\nShell cwd was reset to {original_cwd}"
