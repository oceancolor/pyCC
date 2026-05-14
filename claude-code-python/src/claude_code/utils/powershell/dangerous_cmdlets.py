"""PowerShell dangerous cmdlet lists. Ported from utils/powershell/dangerousCmdlets.ts"""

from __future__ import annotations

from typing import FrozenSet, Set

# Cmdlets that accept -FilePath and execute the file as a script.
FILEPATH_EXECUTION_CMDLETS: FrozenSet[str] = frozenset([
    "invoke-command",
    "start-job",
    "start-threadjob",
    "register-scheduledjob",
])

# Cmdlets where a scriptblock argument executes arbitrary code.
DANGEROUS_SCRIPT_BLOCK_CMDLETS: FrozenSet[str] = frozenset([
    "invoke-command",
    "invoke-expression",
    "start-job",
    "start-threadjob",
    "register-scheduledjob",
    "register-engineevent",
    "register-objectevent",
    "register-wmievent",
    "new-pssession",
    "enter-pssession",
])

# Cmdlets that load and execute module/script code.
MODULE_LOADING_CMDLETS: FrozenSet[str] = frozenset([
    "import-module",
    "ipmo",
    "install-module",
    "save-module",
    "update-module",
    "install-script",
    "save-script",
])

# Shells and process spawners.
_SHELLS_AND_SPAWNERS: FrozenSet[str] = frozenset([
    "pwsh",
    "powershell",
    "cmd",
    "bash",
    "wsl",
    "sh",
    "start-process",
    "start",
    "add-type",
    "new-object",
])

# Network cmdlets (exfil/download).
NETWORK_CMDLETS: FrozenSet[str] = frozenset([
    "invoke-webrequest",
    "invoke-restmethod",
])

# Alias/variable mutation cmdlets.
ALIAS_HIJACK_CMDLETS: FrozenSet[str] = frozenset([
    "set-alias", "sal",
    "new-alias", "nal",
    "set-variable", "sv",
    "new-variable", "nv",
])

# WMI/CIM process-spawn cmdlets.
WMI_CIM_CMDLETS: FrozenSet[str] = frozenset([
    "invoke-wmimethod", "iwmi",
    "invoke-cimmethod",
])

# Cmdlets with callback-gated arg validation in the allowlist.
ARG_GATED_CMDLETS: FrozenSet[str] = frozenset([
    "select-object",
    "sort-object",
    "group-object",
    "where-object",
    "measure-object",
    "write-output",
    "write-host",
    "start-sleep",
    "format-table",
    "format-list",
    "format-wide",
    "format-custom",
    "out-string",
    "out-host",
    # Native executables with callback-gated args
    "ipconfig",
    "hostname",
    "route",
])

# Cross-platform code-execution commands (single-word entries only)
_CROSS_PLATFORM_CODE_EXEC: FrozenSet[str] = frozenset([
    "node", "python", "python3", "ruby", "perl", "php",
    "java", "javac", "dotnet", "go", "cargo", "rustc",
    "gcc", "g++", "clang", "make",
    "eval", "exec", "source",
])

# Commands to never suggest as a wildcard prefix in the permission dialog.
NEVER_SUGGEST: FrozenSet[str] = frozenset(
    _SHELLS_AND_SPAWNERS
    | FILEPATH_EXECUTION_CMDLETS
    | DANGEROUS_SCRIPT_BLOCK_CMDLETS
    | MODULE_LOADING_CMDLETS
    | NETWORK_CMDLETS
    | ALIAS_HIJACK_CMDLETS
    | WMI_CIM_CMDLETS
    | ARG_GATED_CMDLETS
    | frozenset({"foreach-object"})
    | _CROSS_PLATFORM_CODE_EXEC
)


def is_dangerous_cmdlet(name: str) -> bool:
    """Return True if the cmdlet name is in any dangerous cmdlet list."""
    lower = name.lower()
    return (
        lower in DANGEROUS_SCRIPT_BLOCK_CMDLETS
        or lower in FILEPATH_EXECUTION_CMDLETS
        or lower in MODULE_LOADING_CMDLETS
        or lower in NETWORK_CMDLETS
        or lower in ALIAS_HIJACK_CMDLETS
        or lower in WMI_CIM_CMDLETS
    )


def should_never_suggest(name: str) -> bool:
    """Return True if the cmdlet/command should never be auto-suggested."""
    return name.lower() in NEVER_SUGGEST
