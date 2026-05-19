"""FileReadTool prompt constants.

Ported from: tools/FileReadTool/prompt.ts

Contains the tool name, stub message, limits, and description strings
used to build the FileReadTool system prompt at runtime.
"""
from __future__ import annotations

#: The API-level tool name used to identify the FileRead tool.
FILE_READ_TOOL_NAME: str = "Read"

#: Stub returned when the file content hasn't changed since the last Read.
#: Helps avoid re-sending large file contents when the agent reads the same
#: file twice within one conversation.
FILE_UNCHANGED_STUB: str = (
    "File unchanged since last read. The content from the earlier Read "
    "tool_result in this conversation is still current — refer to that "
    "instead of re-reading."
)

#: Maximum number of lines returned per Read call when no limit is specified.
MAX_LINES_TO_READ: int = 2000

#: Short description shown in the tool catalogue.
DESCRIPTION: str = "Read a file from the local filesystem."

#: Instruction line explaining the ``cat -n`` output format.
LINE_FORMAT_INSTRUCTION: str = (
    "- Results are returned using cat -n format, with line numbers starting at 1"
)

#: Default offset/limit instruction (recommend reading the whole file).
OFFSET_INSTRUCTION_DEFAULT: str = (
    "- You can optionally specify a line offset and limit (especially handy "
    "for long files), but it's recommended to read the whole file by not "
    "providing these parameters"
)

#: Targeted offset/limit instruction (shown when the agent already knows
#: which section of the file it needs).
OFFSET_INSTRUCTION_TARGETED: str = (
    "- When you already know which part of the file you need, only read "
    "that part. This can be important for larger files."
)

__all__ = [
    "FILE_READ_TOOL_NAME",
    "FILE_UNCHANGED_STUB",
    "MAX_LINES_TO_READ",
    "DESCRIPTION",
    "LINE_FORMAT_INSTRUCTION",
    "OFFSET_INSTRUCTION_DEFAULT",
    "OFFSET_INSTRUCTION_TARGETED",
]
