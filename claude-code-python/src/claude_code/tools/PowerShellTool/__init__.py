"""PowerShellTool alias package.

Re-exports the PowerShellTool class from the canonical ``power_shell_tool``
sub-package.  The capital-cased ``PowerShellTool/`` directory mirrors the
original TypeScript source layout.

PowerShellTool executes PowerShell Core (``pwsh``) commands on Windows
hosts.  It mirrors the BashTool API but targets Windows environments where
``/bin/bash`` is unavailable.

Ported from: tools/PowerShellTool/ (TypeScript)

Usage::

    from claude_code.tools.PowerShellTool import PowerShellTool

Notes
-----
Prefer importing from ``claude_code.tools.power_shell_tool`` in new code.
This package exists for backward compatibility with the TS directory layout.
"""
from __future__ import annotations

from claude_code.tools.power_shell_tool import PowerShellTool

__all__ = ["PowerShellTool"]
