"""FileEditTool package.

Re-exports the FileEditTool class from its implementation module.

FileEditTool performs targeted, in-place edits to existing files using
an old-string / new-string replacement approach.  It is the preferred
tool for making surgical changes to code without rewriting entire files.

The tool requires that the old_string is unique in the file to avoid
ambiguous replacements.  If the file has been modified since the last
Read call, the tool will return ``FILE_UNEXPECTEDLY_MODIFIED_ERROR``.

Ported from: tools/FileEditTool/ (TypeScript)

Usage::

    from claude_code.tools.file_edit_tool import FileEditTool
"""
from __future__ import annotations

from claude_code.tools.file_edit_tool.file_edit_tool import FileEditTool

__all__ = ["FileEditTool"]
