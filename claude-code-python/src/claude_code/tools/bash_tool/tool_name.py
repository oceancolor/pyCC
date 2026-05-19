"""BashTool canonical tool name constant.

Ported from: tools/BashTool/toolName.ts

Keeping the tool name in its own module avoids circular imports between
the main ``BashTool`` implementation (which imports many helpers) and the
helper modules that only need the string name to avoid the circular chain.

This pattern is used consistently across the tool implementations:
each tool has a ``tool_name.py`` or ``constants.py`` that holds only
the name string so it can be imported without pulling in the full tool.

See also
--------
``claude_code.tools.bash_tool.comment_label`` : Uses this name indirectly.
``claude_code.constants.tools`` : Central registry of all tool names.
"""
from __future__ import annotations

#: The API-level tool name used to identify the Bash tool.
#: This is the value sent in ``tool_use`` blocks and checked in permission rules.
BASH_TOOL_NAME: str = "Bash"

__all__ = ["BASH_TOOL_NAME"]
