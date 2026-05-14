"""PowerShell parsing utilities sub-package. Ported from utils/powershell/.

Provides command parsing and dangerous-cmdlet detection helpers for the
PowerShell tool on Windows.
"""
from __future__ import annotations

from claude_code.utils.powershell.dangerous_cmdlets import (
    is_dangerous_cmdlet,
    should_never_suggest,
)
from claude_code.utils.powershell.parser import (
    ParsedStatement,
)

__all__ = [
    "is_dangerous_cmdlet",
    "should_never_suggest",
    "ParsedStatement",
]
