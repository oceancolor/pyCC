"""Bash/shell parsing utilities sub-package. Ported from utils/bash/.

Provides command parsing, shell quoting, shell history completion, and
bash-specific analysis helpers used by the Bash tool.
"""
from __future__ import annotations

from claude_code.utils.bash.shell_quote import (
    has_malformed_tokens,
    try_quote_shell_args,
)
from claude_code.utils.bash.parser import (
    try_parse_shell_command,
)

__all__ = [
    "try_parse_shell_command",
    "try_quote_shell_args",
    "has_malformed_tokens",
]
