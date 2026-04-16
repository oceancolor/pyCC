"""Bash comment-label extraction. Ported from BashTool/commentLabel.ts"""
from __future__ import annotations
from typing import Optional


def extract_bash_comment_label(command: str) -> Optional[str]:
    """
    If the first line is a `# comment` (not `#!` shebang), return the text
    after the `#` prefix. Otherwise return None.
    Used as the non-verbose tool-use label in fullscreen mode.
    """
    nl = command.find('\n')
    first_line = (command if nl == -1 else command[:nl]).strip()
    if not first_line.startswith('#') or first_line.startswith('#!'):
        return None
    stripped = first_line.lstrip('#').lstrip()
    return stripped or None
