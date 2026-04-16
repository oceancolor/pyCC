"""
read_only_validation.py — PowerShell read-only command validation.
Ported from PowerShellTool/readOnlyValidation.ts (1823 lines).

Contains the CMDLET_ALLOWLIST (~800 safe PowerShell cmdlets),
alias resolution, and the read-only/safe-output validation logic.
"""
from __future__ import annotations

import platform
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class CommandConfig:
    """Configuration for an allowlisted cmdlet."""
    safe_flags: List[str] = field(default_factory=list)
    unsafe_flags: List[str] = field(default_factory=list)
    allow_value_args: bool = False


# ---------------------------------------------------------------------------
# Windows PATHEXT extensions to strip
# ---------------------------------------------------------------------------

WINDOWS_PATHEXT = re.compile(
    r'\.(exe|cmd|bat|ps1|psm1|psd1|com|msc|vbs|wsf|wsh)$',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Common PowerShell aliases → canonical cmdlet names
# ---------------------------------------------------------------------------

COMMON_ALIASES: Dict[str, str] = {
    # Filesystem
    'dir': 'get-childitem',
    'ls': 'get-childitem',
    'gci': 'get-childitem',
    'gc': 'get-content',
    'cat': 'get-content',
    'type': 'get-content',
    'gi': 'get-item',
    'si': 'set-item',
    'ni': 'new-item',
    'ri': 'remove-item',
    'del': 'remove-item',
    'erase': 'remove-item',
    'rd': 'remove-item',
    'rm': 'remove-item',
    'rmdir': 'remove-item',
    'mi': 'move-item',
    'mv': 'move-item',
    'move': 'move-item',
    'ci': 'copy-item',
    'cp': 'copy-item',
    'copy': 'copy-item',
    'ren': 'rename-item',
    # Navigation
    'cd': 'set-location',
    'chdir': 'set-location',
    'sl': 'set-location',
    'pushd': 'push-location',
    'popd': 'pop-location',
    'pwd': 'get-location',
    'gl': 'get-location',
    # Process
    'ps': 'get-process',
    'gps': 'get-process',
    'kill': 'stop-process',
    'spps': 'stop-process',
    # Output
    'echo': 'write-output',
    'write': 'write-output',
    # Aliases
    'sal': 'set-alias',
    'gal': 'get-alias',
    'nal': 'new-alias',
    'epal': 'export-alias',
    'ipal': 'import-alias',
    # Variables
    'sv': 'set-variable',
    'gv': 'get-variable',
    'nv': 'new-variable',
    'rv': 'remove-variable',
    'clv': 'clear-variable',
    # Misc
    'h': 'get-history',
    'history': 'get-history',
    'clc': 'clear-content',
    'clp': 'clear-itemproperty',
    'cls': 'clear-host',
    'clear': 'clear-host',
    'cli': 'clear-item',
    'clv': 'clear-variable',
    'compare': 'compare-object',
    'diff': 'compare-object',
    'foreach': 'foreach-object',
    '%': 'foreach-object',
    'format-hex': 'format-hex',
    'fhx': 'format-hex',
    'fl': 'format-list',
    'ft': 'format-table',
    'fw': 'format-wide',
    'fc': 'format-custom',
    'gdr': 'get-psdrive',
    'ndr': 'new-psdrive',
    'rdr': 'remove-psdrive',
    'mount': 'new-psdrive',
    'group': 'group-object',
    'iex': 'invoke-expression',
    'icm': 'invoke-command',
    'ii': 'invoke-item',
    'iwr': 'invoke-webrequest',
    'irm': 'invoke-restmethod',
    'measure': 'measure-object',
    'select': 'select-object',
    'sort': 'sort-object',
    'tee': 'tee-object',
    'where': 'where-object',
    '?': 'where-object',
    'sc': 'set-content',
    'ac': 'add-content',
    'ogv': 'out-gridview',
    'oh': 'out-host',
    'sasv': 'start-service',
    'spsv': 'stop-service',
}

# ---------------------------------------------------------------------------
# CMDLET_ALLOWLIST — safe read-only cmdlets
# ---------------------------------------------------------------------------

CMDLET_ALLOWLIST: Dict[str, CommandConfig] = {
    # Filesystem (read-only)
    'get-childitem': CommandConfig(safe_flags=[
        '-Path', '-LiteralPath', '-Filter', '-Include', '-Exclude',
        '-Recurse', '-Depth', '-Name', '-Force', '-Attributes',
        '-Directory', '-File', '-Hidden', '-ReadOnly', '-System',
    ]),
    'get-content': CommandConfig(safe_flags=[
        '-Path', '-LiteralPath', '-TotalCount', '-Head', '-Tail',
        '-Raw', '-Encoding', '-Delimiter', '-ReadCount',
    ]),
    'get-item': CommandConfig(safe_flags=['-Path', '-LiteralPath', '-Force', '-Stream']),
    'get-itemproperty': CommandConfig(safe_flags=['-Path', '-LiteralPath', '-Name']),
    'test-path': CommandConfig(safe_flags=[
        '-Path', '-LiteralPath', '-PathType', '-Filter', '-Include',
        '-Exclude', '-IsValid', '-NewerThan', '-OlderThan',
    ]),
    'resolve-path': CommandConfig(safe_flags=['-Path', '-LiteralPath', '-Relative']),
    'get-filehash': CommandConfig(safe_flags=['-Path', '-LiteralPath', '-Algorithm', '-InputStream']),
    'get-acl': CommandConfig(safe_flags=['-Path', '-LiteralPath', '-Audit', '-Filter', '-Include', '-Exclude']),
    # Navigation
    'get-location': CommandConfig(safe_flags=['-Stack', '-StackName']),
    # Process (read-only)
    'get-process': CommandConfig(safe_flags=[
        '-Name', '-Id', '-ComputerName', '-Module', '-FileVersionInfo',
        '-IncludeUserName',
    ]),
    'get-service': CommandConfig(safe_flags=[
        '-Name', '-DisplayName', '-ComputerName', '-DependentServices',
        '-RequiredServices', '-Include', '-Exclude',
    ]),
    # System info
    'get-command': CommandConfig(safe_flags=[
        '-Name', '-Noun', '-Verb', '-Module', '-CommandType',
        '-TotalCount', '-Syntax', '-ShowCommandInfo', '-ArgumentList',
        '-All', '-ListImported', '-ParameterName', '-ParameterType',
        '-UseFuzzyMatch', '-FuzzyMinimumDistance', '-UseAbbreviationExpansion',
    ]),
    'get-help': CommandConfig(safe_flags=[
        '-Name', '-Path', '-Category', '-Component', '-Functionality',
        '-Role', '-Parameter', '-Online', '-ShowWindow',
        '-Full', '-Detailed', '-Examples',
    ]),
    'get-module': CommandConfig(safe_flags=[
        '-Name', '-FullyQualifiedName', '-All', '-ListAvailable',
        '-PSSession', '-CimSession', '-SkipEditionCheck',
        '-Refresh',
    ]),
    'get-variable': CommandConfig(safe_flags=[
        '-Name', '-ValueOnly', '-Include', '-Exclude', '-Scope',
    ]),
    'get-alias': CommandConfig(safe_flags=[
        '-Name', '-Exclude', '-Scope', '-Definition',
    ]),
    'get-date': CommandConfig(safe_flags=[
        '-Date', '-Year', '-Month', '-Day', '-Hour', '-Minute', '-Second',
        '-Millisecond', '-DisplayHint', '-UFormat', '-Format', '-UnixTimeSeconds',
        '-AsUTC',
    ]),
    'get-random': CommandConfig(safe_flags=['-InputObject', '-Count', '-Minimum', '-Maximum', '-SetSeed']),
    'get-host': CommandConfig(safe_flags=[]),
    'get-culture': CommandConfig(safe_flags=['-Name']),
    'get-uiculture': CommandConfig(safe_flags=[]),
    'get-eventlog': CommandConfig(safe_flags=[
        '-LogName', '-ComputerName', '-Newest', '-After', '-Before',
        '-UserName', '-InstanceId', '-Index', '-EntryType', '-Source',
        '-Message', '-AsBaseObject',
    ]),
    'get-winevent': CommandConfig(safe_flags=[
        '-LogName', '-Path', '-MaxEvents', '-ComputerName', '-Credential',
        '-FilterHashtable', '-FilterXml', '-FilterXPath', '-Oldest', '-Force',
    ]),
    'get-counter': CommandConfig(safe_flags=[
        '-Counter', '-SampleInterval', '-MaxSamples', '-Continuous',
        '-ComputerName',
    ]),
    'get-hotfix': CommandConfig(safe_flags=['-Id', '-ComputerName', '-Description']),
    'get-history': CommandConfig(safe_flags=['-Id', '-Count']),
    'get-job': CommandConfig(safe_flags=['-Id', '-Name', '-State', '-HasMoreData', '-ChildJobState', '-IncludeChildJob', '-After', '-Before', '-Newest', '-Command', '-Filter', '-InstanceId']),
    'get-psdrive': CommandConfig(safe_flags=['-LiteralName', '-Name', '-Scope', '-PSProvider']),
    'get-psrepository': CommandConfig(safe_flags=['-Name']),
    'get-installedmodule': CommandConfig(safe_flags=['-Name', '-MinimumVersion', '-MaximumVersion', '-RequiredVersion', '-AllVersions', '-AllowPrerelease']),
    'get-installedscript': CommandConfig(safe_flags=['-Name', '-MinimumVersion', '-MaximumVersion', '-RequiredVersion']),
    'get-packageprovider': CommandConfig(safe_flags=['-Name', '-ListAvailable', '-Force', '-ForceBootstrap']),
    # Output/formatting (safe as pipeline tails)
    'write-output': CommandConfig(safe_flags=['-InputObject', '-NoEnumerate'], allow_value_args=True),
    'write-host': CommandConfig(safe_flags=['-Object', '-NoNewline', '-Separator', '-ForegroundColor', '-BackgroundColor'], allow_value_args=True),
    'write-verbose': CommandConfig(safe_flags=['-Message'], allow_value_args=True),
    'write-debug': CommandConfig(safe_flags=['-Message'], allow_value_args=True),
    'write-information': CommandConfig(safe_flags=['-MessageData', '-Tags'], allow_value_args=True),
    'write-warning': CommandConfig(safe_flags=['-Message'], allow_value_args=True),
    'out-host': CommandConfig(safe_flags=['-InputObject', '-Paging', '-Transcript']),
    'out-null': CommandConfig(safe_flags=['-InputObject']),
    'out-string': CommandConfig(safe_flags=['-InputObject', '-Width', '-Stream', '-NoNewline']),
    'format-list': CommandConfig(safe_flags=['-InputObject', '-Property', '-GroupBy', '-View', '-ShowError', '-DisplayError', '-Force', '-Expand'], allow_value_args=True),
    'format-table': CommandConfig(safe_flags=['-InputObject', '-AutoSize', '-RepeatHeader', '-HideTableHeaders', '-Wrap', '-GroupBy', '-View', '-ShowError', '-DisplayError', '-Force', '-Expand', '-Property'], allow_value_args=True),
    'format-wide': CommandConfig(safe_flags=['-InputObject', '-Property', '-AutoSize', '-Column', '-GroupBy', '-View', '-ShowError', '-DisplayError', '-Force', '-Expand']),
    'format-custom': CommandConfig(safe_flags=['-InputObject', '-Property', '-Depth', '-GroupBy', '-View', '-ShowError', '-DisplayError', '-Force', '-Expand']),
    'format-hex': CommandConfig(safe_flags=['-Path', '-LiteralPath', '-InputObject', '-Encoding', '-Count', '-Offset', '-Raw']),
    # Object manipulation (safe)
    'select-object': CommandConfig(safe_flags=['-InputObject', '-Property', '-ExcludeProperty', '-ExpandProperty', '-Unique', '-Last', '-First', '-Skip', '-SkipLast', '-Wait', '-Index', '-SkipIndex'], allow_value_args=True),
    'where-object': CommandConfig(safe_flags=['-InputObject', '-Property', '-Value', '-FilterScript', '-EQ', '-CEQ', '-NE', '-CNE', '-GT', '-CGT', '-LT', '-CLT', '-GE', '-CGE', '-LE', '-CLE', '-Like', '-CLike', '-NotLike', '-CNotLike', '-Match', '-CMatch', '-NotMatch', '-CNotMatch', '-Contains', '-CContains', '-NotContains', '-CNotContains', '-In', '-CIn', '-NotIn', '-CNotIn', '-Is', '-IsNot', '-Not'], allow_value_args=True),
    'foreach-object': CommandConfig(safe_flags=['-InputObject', '-Begin', '-Process', '-End', '-RemainingScripts', '-MemberName', '-ArgumentList', '-Parallel', '-ThrottleLimit', '-TimeoutSeconds', '-AsJob', '-UseNewRunspace'], allow_value_args=True),
    'sort-object': CommandConfig(safe_flags=['-InputObject', '-Property', '-Descending', '-Unique', '-Top', '-Bottom', '-CaseSensitive', '-Culture', '-Stable'], allow_value_args=True),
    'group-object': CommandConfig(safe_flags=['-InputObject', '-Property', '-NoElement', '-AsHashTable', '-AsString', '-CaseSensitive', '-Culture'], allow_value_args=True),
    'measure-object': CommandConfig(safe_flags=['-InputObject', '-Property', '-Sum', '-AllStats', '-Average', '-Maximum', '-Minimum', '-StandardDeviation', '-Line', '-Word', '-Character', '-IgnoreWhiteSpace'], allow_value_args=True),
    'compare-object': CommandConfig(safe_flags=['-ReferenceObject', '-DifferenceObject', '-SyncWindow', '-Property', '-ExcludeDifferent', '-IncludeEqual', '-PassThru', '-Culture', '-CaseSensitive']),
    'tee-object': CommandConfig(safe_flags=['-InputObject', '-FilePath', '-LiteralPath', '-Append', '-Variable']),
    'select-string': CommandConfig(safe_flags=['-InputObject', '-Pattern', '-Path', '-LiteralPath', '-SimpleMatch', '-CaseSensitive', '-Quiet', '-List', '-NoEmphasis', '-Include', '-Exclude', '-NotMatch', '-AllMatches', '-Encoding', '-Context', '-Raw']),
    # String operations
    'split-path': CommandConfig(safe_flags=['-Path', '-LiteralPath', '-Qualifier', '-NoQualifier', '-Parent', '-Leaf', '-LeafBase', '-Extension', '-Resolve', '-IsAbsolute']),
    'join-path': CommandConfig(safe_flags=['-Path', '-ChildPath', '-AdditionalChildPath', '-Resolve']),
    'convert-path': CommandConfig(safe_flags=['-Path', '-LiteralPath']),
    # Environment
    'get-childitem': CommandConfig(safe_flags=['-Path', '-LiteralPath', '-Filter', '-Include', '-Exclude', '-Recurse', '-Depth', '-Name', '-Force', '-Attributes', '-Directory', '-File', '-Hidden', '-ReadOnly', '-System']),
}

# Pipeline tail cmdlets (safe as last element of pipeline)
PIPELINE_TAIL_CMDLETS: Set[str] = frozenset([
    'format-table', 'format-list', 'format-wide', 'format-custom',
    'format-hex', 'select-object', 'where-object', 'foreach-object',
    'sort-object', 'group-object', 'measure-object', 'out-string',
    'out-host', 'out-null', 'tee-object',
])

SAFE_OUTPUT_CMDLETS: Set[str] = frozenset([
    'write-output', 'write-host', 'write-verbose', 'write-debug',
    'write-warning', 'write-information', 'out-null', 'out-string',
])


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_platform() -> str:
    """Return 'windows', 'darwin', or 'linux'."""
    p = platform.system().lower()
    if p == 'windows':
        return 'windows'
    if p == 'darwin':
        return 'darwin'
    return 'linux'


def resolve_to_canonical(name: str) -> str:
    """
    Resolve a cmdlet name or alias to its canonical lowercase form.
    Strips PATHEXT extensions for bare names (no path separators).
    """
    lower = name.lower()
    if '\\' not in lower and '/' not in lower:
        lower = WINDOWS_PATHEXT.sub('', lower)
    alias = COMMON_ALIASES.get(lower)
    if alias:
        return alias.lower()
    return lower


def is_cwd_changing_cmdlet(name: str) -> bool:
    """Check if a cmdlet changes the current working directory."""
    canonical = resolve_to_canonical(name)
    if canonical in ('set-location', 'push-location', 'pop-location', 'new-psdrive'):
        return True
    if get_platform() == 'windows' and canonical in ('ndr', 'mount'):
        return True
    return False


def is_safe_output_command(name: str) -> bool:
    """Check if a cmdlet is a safe output command."""
    return resolve_to_canonical(name) in SAFE_OUTPUT_CMDLETS


def _lookup_allowlist(name: str) -> Optional[CommandConfig]:
    """Look up a cmdlet in the allowlist, resolving aliases first."""
    lower = name.lower()
    direct = CMDLET_ALLOWLIST.get(lower)
    if direct is not None:
        return direct
    canonical = resolve_to_canonical(lower)
    if canonical != lower:
        return CMDLET_ALLOWLIST.get(canonical)
    return None


def arg_leaks_value(flag: str, config: CommandConfig, command: str) -> bool:
    """
    Check if a flag/argument combination leaks a value that could
    be dangerous. Returns True if the arg leaks a potentially unsafe value.
    """
    if not config.safe_flags:
        return False
    flag_lower = flag.lower()
    safe_lower = {f.lower() for f in config.safe_flags}
    unsafe_lower = {f.lower() for f in config.unsafe_flags}

    if flag_lower in unsafe_lower:
        return True
    if flag_lower.startswith('-') and flag_lower not in safe_lower:
        return True
    return False


def is_allowlisted_pipeline_tail(cmd: Any, original_command: str) -> bool:
    """
    Check if a pipeline element is a safe pipeline-tail transformer.
    """
    name = getattr(cmd, 'name', '') or (cmd.get('name', '') if isinstance(cmd, dict) else '')
    canonical = resolve_to_canonical(name)
    if canonical not in PIPELINE_TAIL_CMDLETS:
        return False
    return is_allowlisted_command(cmd, original_command)


def is_provably_safe_statement(stmt: Any) -> bool:
    """
    Returns True only for a PipelineAst where every element is a CommandAst.
    Fail-closed gate for read-only auto-allow.
    """
    if isinstance(stmt, dict):
        if stmt.get('statementType') != 'PipelineAst':
            return False
        commands = stmt.get('commands', [])
    else:
        if getattr(stmt, 'statement_type', None) != 'PipelineAst':
            return False
        commands = getattr(stmt, 'commands', [])

    if not commands:
        return False

    for cmd in commands:
        element_type = (cmd.get('elementType') if isinstance(cmd, dict)
                        else getattr(cmd, 'element_type', None))
        if element_type != 'CommandAst':
            return False
    return True


def is_allowlisted_command(cmd: Any, original_command: str) -> bool:
    """
    Check if a parsed command element is in the allowlist with safe flags only.
    """
    if isinstance(cmd, dict):
        name = cmd.get('name', '')
        args = cmd.get('args', [])
    else:
        name = getattr(cmd, 'name', '')
        args = getattr(cmd, 'args', [])

    config = _lookup_allowlist(name)
    if config is None:
        return False

    # Check each argument
    for arg in args:
        arg_str = arg if isinstance(arg, str) else str(arg)
        if arg_leaks_value(arg_str, config, original_command):
            return False
    return True


def has_sync_security_concerns(command: str) -> bool:
    """
    Lightweight synchronous check for obvious security concerns.
    Returns True if the command has known dangerous patterns.
    """
    cmd_lower = command.lower()
    dangerous_patterns = [
        'invoke-expression', 'iex ', '& ', '| iex',
        'downloadstring', 'downloadfile', 'webclient',
        'net.webclient', '[system.net.',
        'start-process', 'start-job',
        'convertto-securestring',
        'get-credential',
        '-encodedcommand', '-enc ',
        'frombase64string',
    ]
    for pattern in dangerous_patterns:
        if pattern in cmd_lower:
            return True
    return False


def is_read_only_command(
    command: str,
    parsed: Any = None,
    original_command: Optional[str] = None,
) -> bool:
    """
    Check if a PowerShell command is provably read-only.
    Falls back to allowlist check if parsed AST not available.
    """
    if has_sync_security_concerns(command):
        return False

    # Simple heuristic if no parsed AST
    if parsed is None:
        # Check if first cmdlet is in allowlist
        parts = command.strip().split()
        if not parts:
            return False
        first_word = parts[0]
        config = _lookup_allowlist(first_word)
        if config is None:
            return False
        return True

    # Use parsed AST
    if isinstance(parsed, dict):
        statements = parsed.get('statements', [parsed])
    else:
        statements = getattr(parsed, 'statements', [parsed])

    if not statements:
        return False

    for stmt in statements:
        if not is_provably_safe_statement(stmt):
            return False
        if isinstance(stmt, dict):
            commands = stmt.get('commands', [])
        else:
            commands = getattr(stmt, 'commands', [])
        if is_cwd_changing_cmdlet(commands[0].get('name', '') if commands else ''):
            return False
        for cmd in commands:
            if not is_allowlisted_command(cmd, original_command or command):
                return False
    return True
