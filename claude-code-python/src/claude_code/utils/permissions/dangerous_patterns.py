"""
Dangerous patterns - pattern lists for dangerous shell-tool allow-rule prefixes.
"""

from __future__ import annotations

from typing import List

# Cross-platform code-execution entry points present on both Unix and Windows.
CROSS_PLATFORM_CODE_EXEC: List[str] = [
    # Interpreters
    "python", "python3", "python2",
    "node", "deno", "tsx",
    "ruby", "perl", "php", "lua",
    # Package runners
    "npx", "bunx", "npm run", "yarn run", "pnpm run", "bun run",
    # Shells reachable from both
    "bash", "sh",
    # Remote arbitrary-command wrapper
    "ssh",
]

DANGEROUS_BASH_PATTERNS: List[str] = [
    *CROSS_PLATFORM_CODE_EXEC,
    "zsh", "fish", "eval", "exec", "env", "xargs", "sudo",
]

DANGEROUS_POWERSHELL_PATTERNS: List[str] = [
    *CROSS_PLATFORM_CODE_EXEC,
    # PowerShell-specific dangerous cmdlets
    "Invoke-Expression", "iex",
    "Invoke-Command",
    "Start-Process",
    "Set-ExecutionPolicy",
    "Add-Type",
]
