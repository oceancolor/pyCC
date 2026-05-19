"""PowerShellTool package.

Re-exports the PowerShellTool class from its implementation module.

PowerShellTool executes PowerShell Core (``pwsh``) commands on Windows
hosts.  It mirrors the BashTool API but delegates to PowerShell instead
of ``/bin/bash``.

The tool supports the same ``timeout``, ``restart``, and
``run_in_background`` parameters as BashTool but runs in a Windows-native
PowerShell session, allowing the use of PowerShell cmdlets and the Windows
object model.

Ported from: tools/PowerShellTool/ (TypeScript)

Usage::

    from claude_code.tools.power_shell_tool import PowerShellTool
"""
from __future__ import annotations

from claude_code.tools.power_shell_tool.power_shell_tool import PowerShellTool

__all__ = ["PowerShellTool"]
