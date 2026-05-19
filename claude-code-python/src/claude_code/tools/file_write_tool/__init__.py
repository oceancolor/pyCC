"""FileWriteTool package.

Re-exports the FileWriteTool class from its implementation module.

FileWriteTool writes or overwrites a file at a given path with new content.
It should be used for creating new files or completely replacing file
contents.  For targeted line-level changes to existing files, use
``FileEditTool`` instead.

The tool creates parent directories automatically if they do not exist,
and updates the agent's file-hash cache so subsequent ``FileEditTool``
calls do not trigger the "file unexpectedly modified" error.

Ported from: tools/FileWriteTool/ (TypeScript)

Usage::

    from claude_code.tools.file_write_tool import FileWriteTool
"""
from __future__ import annotations

from claude_code.tools.file_write_tool.file_write_tool import FileWriteTool

__all__ = ["FileWriteTool"]
