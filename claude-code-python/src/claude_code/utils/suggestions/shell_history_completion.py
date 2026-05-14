"""Shell history completion for the prompt input. Ported from utils/suggestions/shellHistoryCompletion.ts"""

from __future__ import annotations

import os
import time
from typing import List, Optional, Tuple

from dataclasses import dataclass

CACHE_TTL_MS = 60_000  # 60 seconds — history won't change while typing
MAX_HISTORY_COMMANDS = 50


@dataclass
class ShellHistoryMatch:
    """Result of a shell history completion lookup."""

    full_command: str
    """The full command from history."""
    suffix: str
    """The suffix to display as ghost text (the part after the user's input)."""


# Module-level cache
_shell_history_cache: Optional[List[str]] = None
_shell_history_cache_timestamp: float = 0.0


def clear_shell_history_cache() -> None:
    """Clear the shell history cache (e.g. after the user submits a command)."""
    global _shell_history_cache, _shell_history_cache_timestamp
    _shell_history_cache = None
    _shell_history_cache_timestamp = 0.0


def _read_history_file(history_file: str) -> List[str]:
    """Read unique commands from a shell history file (bash/zsh format)."""
    commands: List[str] = []
    seen: set = set()
    try:
        with open(history_file, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                # zsh extended history format: ': <epoch>:<elapsed>;<command>'
                if line.startswith(": ") and ";" in line:
                    line = line.split(";", 1)[1]
                if line and not line.startswith("#") and line not in seen:
                    seen.add(line)
                    commands.append(line)
                    if len(commands) >= MAX_HISTORY_COMMANDS:
                        break
    except OSError:
        pass
    # Most recent last in file → reverse so most-recent first
    return list(reversed(commands))


def get_shell_history_commands() -> List[str]:
    """Return shell history commands, reading from disk with a short TTL cache."""
    global _shell_history_cache, _shell_history_cache_timestamp

    now_ms = time.time() * 1000
    if _shell_history_cache is not None and now_ms - _shell_history_cache_timestamp < CACHE_TTL_MS:
        return _shell_history_cache

    commands: List[str] = []
    seen: set = set()

    # Look for history files in preference order
    candidates = [
        os.environ.get("HISTFILE"),
        os.path.expanduser("~/.bash_history"),
        os.path.expanduser("~/.zsh_history"),
        os.path.expanduser("~/.history"),
    ]

    for hist_file in candidates:
        if not hist_file or not os.path.isfile(hist_file):
            continue
        for cmd in _read_history_file(hist_file):
            if cmd not in seen:
                seen.add(cmd)
                commands.append(cmd)
            if len(commands) >= MAX_HISTORY_COMMANDS:
                break
        break  # Use only the first found history file

    _shell_history_cache = commands
    _shell_history_cache_timestamp = now_ms
    return commands


def find_shell_history_match(input_text: str) -> Optional[ShellHistoryMatch]:
    """Find the best matching shell history command for ghost-text completion.

    Returns the first history command whose prefix matches ``input_text``
    (case-sensitive), or None if no match is found.

    Args:
        input_text: The current prompt input text.

    Returns:
        A :class:`ShellHistoryMatch` with the full command and the suffix to
        display, or None.
    """
    if not input_text:
        return None

    for command in get_shell_history_commands():
        if command.startswith(input_text) and command != input_text:
            return ShellHistoryMatch(
                full_command=command,
                suffix=command[len(input_text):],
            )
    return None
