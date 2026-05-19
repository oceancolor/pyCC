"""FileEditTool constants.

Ported from: tools/FileEditTool/constants.ts

Kept in its own module to avoid circular imports between the tool
implementation and other modules that only need the name string or
permission pattern constants.
"""
from __future__ import annotations

#: The API-level tool name used to identify the FileEdit tool.
FILE_EDIT_TOOL_NAME: str = "Edit"

#: Permission pattern that grants session-level access to the project's
#: ``.claude/`` folder (relative path form used in per-project settings).
CLAUDE_FOLDER_PERMISSION_PATTERN: str = "/.claude/**"

#: Permission pattern that grants session-level access to the global
#: ``~/.claude/`` folder (used in global settings and tests).
GLOBAL_CLAUDE_FOLDER_PERMISSION_PATTERN: str = "~/.claude/**"

#: Error message emitted when the target file was modified between the
#: last Read and the current Edit call.
FILE_UNEXPECTEDLY_MODIFIED_ERROR: str = (
    "File has been unexpectedly modified. "
    "Read it again before attempting to write it."
)

__all__ = [
    "FILE_EDIT_TOOL_NAME",
    "CLAUDE_FOLDER_PERMISSION_PATTERN",
    "GLOBAL_CLAUDE_FOLDER_PERMISSION_PATTERN",
    "FILE_UNEXPECTEDLY_MODIFIED_ERROR",
]
