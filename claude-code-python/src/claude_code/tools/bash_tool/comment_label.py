"""Bash comment-label extraction.

Ported from: tools/BashTool/commentLabel.ts

If the first line of a bash command is a ``# comment`` (not a ``#!`` shebang),
this module extracts the text after the ``#`` prefix and returns it as a
human-readable label.  This label is displayed in the non-verbose tool-use
description in fullscreen / headless modes.
"""
from __future__ import annotations

from typing import Optional


def extract_bash_comment_label(command: str) -> Optional[str]:
    """Return the first-line comment text of *command*, or ``None``.

    Parameters
    ----------
    command:
        The full bash command string, potentially multi-line.

    Returns
    -------
    str | None
        The comment text (stripped of leading ``#`` and whitespace) when the
        first line is a plain comment, otherwise ``None``.

    Examples
    --------
    >>> extract_bash_comment_label("# list files\\nls -la")
    'list files'
    >>> extract_bash_comment_label("#!/usr/bin/env bash\\necho hi")
    >>> extract_bash_comment_label("echo hello")
    """
    nl = command.find("\n")
    first_line = (command if nl == -1 else command[:nl]).strip()
    if not first_line.startswith("#") or first_line.startswith("#!"):
        return None
    stripped = first_line.lstrip("#").lstrip()
    return stripped or None


__all__ = ["extract_bash_comment_label"]
