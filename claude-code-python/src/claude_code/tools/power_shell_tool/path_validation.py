"""
PowerShell-specific path validation for command arguments.
Ported from PowerShellTool/pathValidation.ts (2049 lines).

Extracts file paths from PowerShell commands and validates them against
allowed project directories. Follows the same patterns as BashTool/pathValidation.py.
"""
from __future__ import annotations

import os
import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Dict, List, Optional, Set, Tuple

# ─── Type aliases ─────────────────────────────────────────────────────────────

ParsedCommandElement = Dict[str, Any]
ParsedPowerShellCommand = Dict[str, Any]
PermissionResult = Dict[str, Any]
ToolPermissionContext = Any

# ─── Constants ────────────────────────────────────────────────────────────────

MAX_DIRS_TO_LIST = 5
# PowerShell wildcards: * ? [ ] (braces are LITERAL)
GLOB_PATTERN_REGEX = re.compile(r'[*?\[\]]')

# Dangerous paths regex (mirrors BashTool)
DANGEROUS_PATHS_RE = re.compile(
    r'(?:^|/)(?:etc/passwd|etc/shadow|etc/sudoers|\.ssh/|\.gnupg/|proc/|sys/|dev/)'
)

# ─── CMDLET_PATH_CONFIG ───────────────────────────────────────────────────────

# Per-cmdlet parameter configuration.
# Each entry declares:
#   operationType: 'read' | 'write' | 'create'
#   pathParams: parameters that accept file paths
#   knownSwitches: switch parameters (take NO value)
#   knownValueParams: value-taking parameters that are NOT paths
#   leafOnlyPathParams: parameters for leaf filenames resolved relative to another param
#   positionalSkip: number of leading positional args to skip
#   optionalWrite: if True, write only when a pathParam is present

CmdletPathConfig = Dict[str, Any]

CMDLET_PATH_CONFIG: Dict[str, CmdletPathConfig] = {
    # ── Write/create operations ───────────────────────────────────────────
    'set-content': {
        'operationType': 'write',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': [
            '-passthru', '-force', '-whatif', '-confirm',
            '-usetransaction', '-nonewline', '-asbytestream',
        ],
        'knownValueParams': [
            '-value', '-filter', '-include', '-exclude',
            '-credential', '-encoding', '-stream',
        ],
    },
    'add-content': {
        'operationType': 'write',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': [
            '-passthru', '-force', '-whatif', '-confirm',
            '-usetransaction', '-nonewline', '-asbytestream',
        ],
        'knownValueParams': [
            '-value', '-filter', '-include', '-exclude',
            '-credential', '-encoding', '-stream',
        ],
    },
    'remove-item': {
        'operationType': 'write',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-recurse', '-force', '-whatif', '-confirm', '-usetransaction'],
        'knownValueParams': ['-filter', '-include', '-exclude', '-credential', '-stream'],
    },
    'clear-content': {
        'operationType': 'write',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-force', '-whatif', '-confirm', '-usetransaction'],
        'knownValueParams': ['-filter', '-include', '-exclude', '-credential', '-stream'],
    },
    'out-file': {
        'operationType': 'write',
        'pathParams': ['-filepath', '-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-append', '-force', '-noclobber', '-nonewline', '-whatif', '-confirm'],
        'knownValueParams': ['-inputobject', '-encoding', '-width'],
    },
    'tee-object': {
        'operationType': 'write',
        'pathParams': ['-filepath', '-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-append'],
        'knownValueParams': ['-inputobject', '-variable', '-encoding'],
    },
    'export-csv': {
        'operationType': 'write',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': [
            '-append', '-force', '-noclobber', '-notypeinformation',
            '-includetypeinformation', '-useculture', '-noheader', '-whatif', '-confirm',
        ],
        'knownValueParams': [
            '-inputobject', '-delimiter', '-encoding', '-quotefields', '-usequotes',
        ],
    },
    'export-clixml': {
        'operationType': 'write',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-force', '-noclobber', '-whatif', '-confirm'],
        'knownValueParams': ['-inputobject', '-depth', '-encoding'],
    },
    'new-item': {
        'operationType': 'write',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'leafOnlyPathParams': ['-name'],
        'knownSwitches': ['-force', '-whatif', '-confirm', '-usetransaction'],
        'knownValueParams': ['-itemtype', '-value', '-credential', '-type'],
    },
    'copy-item': {
        'operationType': 'write',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp', '-destination'],
        'knownSwitches': [
            '-container', '-force', '-passthru', '-recurse', '-whatif', '-confirm',
            '-usetransaction',
        ],
        'knownValueParams': [
            '-filter', '-include', '-exclude', '-credential',
            '-fromsession', '-tosession',
        ],
    },
    'move-item': {
        'operationType': 'write',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp', '-destination'],
        'knownSwitches': ['-force', '-passthru', '-whatif', '-confirm', '-usetransaction'],
        'knownValueParams': ['-filter', '-include', '-exclude', '-credential'],
    },
    'rename-item': {
        'operationType': 'write',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-force', '-passthru', '-whatif', '-confirm', '-usetransaction'],
        'knownValueParams': ['-newname', '-credential', '-filter', '-include', '-exclude'],
    },
    'set-item': {
        'operationType': 'write',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-force', '-passthru', '-whatif', '-confirm', '-usetransaction'],
        'knownValueParams': ['-value', '-credential', '-filter', '-include', '-exclude'],
    },

    # ── Read operations ───────────────────────────────────────────────────
    'get-content': {
        'operationType': 'read',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-force', '-usetransaction', '-wait', '-raw', '-asbytestream'],
        'knownValueParams': [
            '-readcount', '-totalcount', '-tail', '-first', '-head', '-last',
            '-filter', '-include', '-exclude', '-credential', '-delimiter',
            '-encoding', '-stream',
        ],
    },
    'get-childitem': {
        'operationType': 'read',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': [
            '-recurse', '-force', '-name', '-usetransaction', '-followsymlink',
            '-directory', '-file', '-hidden', '-readonly', '-system',
        ],
        'knownValueParams': [
            '-filter', '-include', '-exclude', '-depth', '-attributes', '-credential',
        ],
    },
    'get-item': {
        'operationType': 'read',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-force', '-usetransaction'],
        'knownValueParams': ['-filter', '-include', '-exclude', '-credential', '-stream'],
    },
    'get-itemproperty': {
        'operationType': 'read',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-usetransaction'],
        'knownValueParams': ['-name', '-filter', '-include', '-exclude', '-credential'],
    },
    'get-itempropertyvalue': {
        'operationType': 'read',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-usetransaction'],
        'knownValueParams': ['-name', '-filter', '-include', '-exclude', '-credential'],
    },
    'get-filehash': {
        'operationType': 'read',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': [],
        'knownValueParams': ['-algorithm', '-inputstream'],
    },
    'get-acl': {
        'operationType': 'read',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-audit', '-allcentralaccesspolicies', '-usetransaction'],
        'knownValueParams': ['-inputobject', '-filter', '-include', '-exclude'],
    },
    'format-hex': {
        'operationType': 'read',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-raw'],
        'knownValueParams': ['-inputobject', '-encoding', '-count', '-offset'],
    },
    'test-path': {
        'operationType': 'read',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-isvalid', '-usetransaction'],
        'knownValueParams': [
            '-filter', '-include', '-exclude', '-pathtype',
            '-credential', '-olderthan', '-newerthan',
        ],
    },
    'resolve-path': {
        'operationType': 'read',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-relative', '-usetransaction', '-force'],
        'knownValueParams': ['-credential', '-relativebasepath'],
    },
    'convert-path': {
        'operationType': 'read',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-usetransaction'],
        'knownValueParams': [],
    },
    'select-string': {
        'operationType': 'read',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': [
            '-simplematch', '-casesensitive', '-quiet', '-list', '-notmatch',
            '-allmatches', '-noemphasis', '-raw',
        ],
        'knownValueParams': [
            '-inputobject', '-pattern', '-include', '-exclude',
            '-encoding', '-context', '-culture',
        ],
    },
    'set-location': {
        'operationType': 'read',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-passthru', '-usetransaction'],
        'knownValueParams': ['-stackname'],
    },
    'push-location': {
        'operationType': 'read',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-passthru', '-usetransaction'],
        'knownValueParams': ['-stackname'],
    },
    'pop-location': {
        'operationType': 'read',
        'pathParams': [],
        'knownSwitches': ['-passthru', '-usetransaction'],
        'knownValueParams': ['-stackname'],
    },
    'select-xml': {
        'operationType': 'read',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': [],
        'knownValueParams': ['-xml', '-content', '-xpath', '-namespace'],
    },
    'get-winevent': {
        'operationType': 'read',
        'pathParams': ['-path'],
        'knownSwitches': ['-force', '-oldest'],
        'knownValueParams': [
            '-listlog', '-logname', '-listprovider', '-providername',
            '-maxevents', '-computername', '-credential',
            '-filterxpath', '-filterxml', '-filterhashtable',
        ],
    },

    # ── Write-path cmdlets with output parameters ──────────────────────────
    'invoke-webrequest': {
        'operationType': 'write',
        'pathParams': ['-outfile', '-infile'],
        'positionalSkip': 1,
        'optionalWrite': True,
        'knownSwitches': [
            '-allowinsecureredirect', '-allowunencryptedauthentication',
            '-disablekeepalive', '-nobodyprogress', '-passthru',
            '-preservefileauthorizationmetadata', '-resume',
            '-skipcertificatecheck', '-skipheadervalidation',
            '-skiphttperrorcheck', '-usebasicparsing', '-usedefaultcredentials',
        ],
        'knownValueParams': [
            '-uri', '-method', '-body', '-contenttype', '-headers',
            '-maximumredirection', '-maximumretrycount', '-proxy',
            '-proxycredential', '-retryintervalsec', '-sessionvariable',
            '-timeoutsec', '-token', '-transferencoding', '-useragent',
            '-websession', '-credential', '-authentication', '-certificate',
            '-certificatethumbprint', '-form', '-httpversion',
        ],
    },
    'invoke-restmethod': {
        'operationType': 'write',
        'pathParams': ['-outfile', '-infile'],
        'positionalSkip': 1,
        'optionalWrite': True,
        'knownSwitches': [
            '-allowinsecureredirect', '-allowunencryptedauthentication',
            '-disablekeepalive', '-followrellink', '-nobodyprogress', '-passthru',
            '-preservefileauthorizationmetadata', '-resume',
            '-skipcertificatecheck', '-skipheadervalidation',
            '-skiphttperrorcheck', '-usebasicparsing', '-usedefaultcredentials',
        ],
        'knownValueParams': [
            '-uri', '-method', '-body', '-contenttype', '-headers',
            '-maximumfollowrellink', '-maximumredirection', '-maximumretrycount',
            '-proxy', '-proxycredential', '-responseheaderstvariable',
            '-retryintervalsec', '-sessionvariable', '-statuscodevariable',
            '-timeoutsec', '-token', '-transferencoding', '-useragent',
            '-websession', '-credential', '-authentication', '-certificate',
            '-certificatethumbprint', '-form', '-httpversion',
        ],
    },
    'expand-archive': {
        'operationType': 'write',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp', '-destinationpath'],
        'knownSwitches': ['-force', '-passthru', '-whatif', '-confirm'],
        'knownValueParams': [],
    },
    'compress-archive': {
        'operationType': 'write',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp', '-destinationpath'],
        'knownSwitches': ['-force', '-update', '-passthru', '-whatif', '-confirm'],
        'knownValueParams': ['-compressionlevel'],
    },

    # ── Registry/property write cmdlets ───────────────────────────────────
    'set-itemproperty': {
        'operationType': 'write',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-passthru', '-force', '-whatif', '-confirm', '-usetransaction'],
        'knownValueParams': [
            '-name', '-value', '-type', '-filter', '-include',
            '-exclude', '-credential', '-inputobject',
        ],
    },
    'new-itemproperty': {
        'operationType': 'write',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-force', '-whatif', '-confirm', '-usetransaction'],
        'knownValueParams': [
            '-name', '-value', '-propertytype', '-type',
            '-filter', '-include', '-exclude', '-credential',
        ],
    },
    'remove-itemproperty': {
        'operationType': 'write',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-force', '-whatif', '-confirm', '-usetransaction'],
        'knownValueParams': ['-name', '-filter', '-include', '-exclude', '-credential'],
    },
    'clear-item': {
        'operationType': 'write',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': ['-force', '-whatif', '-confirm', '-usetransaction'],
        'knownValueParams': ['-filter', '-include', '-exclude', '-credential'],
    },
    'export-alias': {
        'operationType': 'write',
        'pathParams': ['-path', '-literalpath', '-pspath', '-lp'],
        'knownSwitches': [
            '-append', '-force', '-noclobber', '-passthru', '-whatif', '-confirm',
        ],
        'knownValueParams': ['-name', '-description', '-scope', '-as'],
    },
}

# Common switches (no value) shared across all cmdlets
COMMON_SWITCHES: Set[str] = {
    '-verbose', '-debug', '-whatif', '-confirm',
    '-vb', '-db',
}

# Common value-taking parameters (not paths) shared across all cmdlets
COMMON_VALUE_PARAMS: Set[str] = {
    '-erroraction', '-errorvariable', '-warningaction', '-warningvariable',
    '-informationaction', '-informationvariable', '-outvariable', '-outbuffer',
    '-pipelinesupport',
    '-ea', '-ev', '-wa', '-wv', '-ia', '-iv', '-ov', '-ob',
}


# ─── matchesParam helper ─────────────────────────────────────────────────────

def _matches_param(param_lower: str, param_list: List[str]) -> bool:
    """
    Returns True if param_lower matches any entry in param_list,
    accounting for PowerShell prefix-matching (e.g. '-lit' matches '-literalpath').
    """
    for p in param_list:
        if p == param_lower or (len(param_lower) > 1 and p.startswith(param_lower)):
            return True
    return False


# ─── hasComplexColonValue ─────────────────────────────────────────────────────

def _has_complex_colon_value(raw_value: str) -> bool:
    """
    Returns True if a colon-syntax value contains expression constructs
    that mask the real runtime path.
    """
    return (
        ',' in raw_value or
        raw_value.startswith('(') or
        raw_value.startswith('[') or
        '`' in raw_value or
        '@(' in raw_value or
        raw_value.startswith('@{') or
        '$' in raw_value
    )


# ─── expandTilde ─────────────────────────────────────────────────────────────

def _expand_tilde(file_path: str) -> str:
    if file_path == '~' or file_path.startswith('~/') or file_path.startswith('~\\'):
        return os.path.expanduser('~') + file_path[1:]
    return file_path


# ─── formatDirectoryList ──────────────────────────────────────────────────────

def _format_directory_list(directories: List[str]) -> str:
    dir_count = len(directories)
    if dir_count <= MAX_DIRS_TO_LIST:
        return ', '.join(f"'{d}'" for d in directories)
    first_dirs = ', '.join(f"'{d}'" for d in directories[:MAX_DIRS_TO_LIST])
    return f"{first_dirs}, and {dir_count - MAX_DIRS_TO_LIST} more"


# ─── isDangerousRemovalRawPath ────────────────────────────────────────────────

def is_dangerous_removal_raw_path(file_path: str) -> bool:
    """
    Checks the raw user-provided path for dangerous removal targets.
    Checks the tilde-expanded, backslash-normalized form.
    """
    expanded = _expand_tilde(file_path.strip("'\"")).replace('\\', '/')
    return _is_dangerous_removal_path(expanded)


def _is_dangerous_removal_path(normalized_path: str) -> bool:
    """Returns True if the path is a dangerous removal target."""
    home = os.path.expanduser('~').replace('\\', '/')
    # Exact dangerous paths
    dangerous_exact = {'/', '/etc', '/usr', '/bin', '/sbin', '/lib', '/lib64',
                       '/boot', '/root', '/var', '/tmp', '/home', '/sys', '/proc',
                       '/dev', '/run', '/srv', '/opt'}
    if normalized_path.rstrip('/') in dangerous_exact or normalized_path == home:
        return True
    # Dangerous prefixes
    dangerous_prefixes = ['/etc/', '/usr/', '/bin/', '/sbin/', '/lib/', '/boot/',
                          '/root/', '/var/', '/sys/', '/proc/', '/dev/', '/run/']
    for prefix in dangerous_prefixes:
        if normalized_path.startswith(prefix):
            return True
    return False


def dangerous_removal_deny(path: str) -> PermissionResult:
    """Returns a deny PermissionResult for dangerous removal."""
    return {
        'behavior': 'deny',
        'message': (
            f"Remove-Item on system path '{path}' is blocked. "
            "This path is protected from removal."
        ),
        'decisionReason': {
            'type': 'other',
            'reason': 'Removal targets a protected system path',
        },
    }


# ─── validatePath ─────────────────────────────────────────────────────────────

def _validate_path(
    file_path: str,
    cwd: str,
    tool_permission_context: ToolPermissionContext,
    operation_type: str,
) -> Dict[str, Any]:
    """
    Validates a filesystem path, handling tilde expansion, backtick escapes,
    provider paths, and UNC paths.

    Returns dict: {allowed: bool, resolved_path: str, decision_reason?: dict}
    """
    clean_path = _expand_tilde(file_path.strip("'\""))
    normalized_path = clean_path.replace('\\', '/')

    # SECURITY: backtick escape characters
    if '`' in normalized_path:
        backtick_stripped = normalized_path.replace('`', '')
        deny_hit = _check_deny_rule_for_guessed_path(
            backtick_stripped, cwd, tool_permission_context, operation_type
        )
        if deny_hit:
            return {
                'allowed': False,
                'resolved_path': deny_hit['resolved_path'],
                'decision_reason': {'type': 'rule', 'rule': deny_hit['rule']},
            }
        return {
            'allowed': False,
            'resolved_path': normalized_path,
            'decision_reason': {
                'type': 'other',
                'reason': 'Backtick escape characters in paths cannot be statically validated',
            },
        }

    # SECURITY: provider paths (::)
    if '::' in normalized_path:
        after_provider = normalized_path[normalized_path.index('::') + 2:]
        deny_hit = _check_deny_rule_for_guessed_path(
            after_provider, cwd, tool_permission_context, operation_type
        )
        if deny_hit:
            return {
                'allowed': False,
                'resolved_path': deny_hit['resolved_path'],
                'decision_reason': {'type': 'rule', 'rule': deny_hit['rule']},
            }
        return {
            'allowed': False,
            'resolved_path': normalized_path,
            'decision_reason': {
                'type': 'other',
                'reason': 'Module-qualified provider paths (::) cannot be statically validated',
            },
        }

    # SECURITY: UNC paths
    if normalized_path.startswith('//') or normalized_path.startswith('\\\\'):
        return {
            'allowed': False,
            'resolved_path': normalized_path,
            'decision_reason': {
                'type': 'other',
                'reason': 'UNC paths can trigger network requests and are not allowed',
            },
        }

    # SECURITY: provider-qualified paths like HKLM:\, HKCU:\, Env:\
    _provider_path_re = re.compile(r'^[a-z]{2,}:', re.IGNORECASE)
    if _provider_path_re.match(normalized_path):
        # Skip filesystem provider paths that are just drive letters (C:/)
        if not re.match(r'^[a-zA-Z]:/', normalized_path) and \
                not re.match(r'^[a-zA-Z]:$', normalized_path):
            return {
                'allowed': False,
                'resolved_path': normalized_path,
                'decision_reason': {
                    'type': 'other',
                    'reason': f'Non-filesystem provider path requires manual approval',
                },
            }

    # Resolve path
    if os.path.isabs(normalized_path):
        abs_path = normalized_path
    else:
        abs_path = os.path.normpath(os.path.join(cwd, normalized_path))

    resolved_path = os.path.realpath(abs_path)

    # Check if path is allowed
    result = _is_path_allowed(resolved_path, tool_permission_context, operation_type)
    return {
        'allowed': result['allowed'],
        'resolved_path': resolved_path,
        'decision_reason': result.get('decision_reason'),
    }


def _check_deny_rule_for_guessed_path(
    stripped_path: str,
    cwd: str,
    tool_permission_context: ToolPermissionContext,
    operation_type: str,
) -> Optional[Dict[str, Any]]:
    """Best-effort deny check for obscured paths. ONLY checks deny rules."""
    if not stripped_path or '\0' in stripped_path:
        return None
    tilde_expanded = _expand_tilde(stripped_path)
    if os.path.isabs(tilde_expanded):
        abs_path = tilde_expanded
    else:
        abs_path = os.path.normpath(os.path.join(cwd, tilde_expanded))
    resolved_path = os.path.realpath(abs_path)
    rule = _get_deny_rule(resolved_path, tool_permission_context, operation_type)
    if rule:
        return {'resolved_path': resolved_path, 'rule': rule}
    return None


def _get_deny_rule(
    path: str,
    tool_permission_context: ToolPermissionContext,
    operation_type: str,
) -> Optional[Any]:
    """Returns a matching deny rule for the path, or None."""
    # Try to use the permission context's deny rules
    if tool_permission_context is None:
        return None
    permission_type = 'read' if operation_type == 'read' else 'edit'
    try:
        from claude_code.utils.permissions.permissions import matching_rule_for_input
        return matching_rule_for_input(path, tool_permission_context, permission_type, 'deny')
    except (ImportError, Exception):
        return None


def _is_path_allowed(
    resolved_path: str,
    tool_permission_context: ToolPermissionContext,
    operation_type: str,
) -> Dict[str, Any]:
    """
    Checks if a resolved path is allowed for the given operation type.
    Returns dict: {allowed: bool, decision_reason?: dict}
    """
    if tool_permission_context is None:
        return {'allowed': True}

    permission_type = 'read' if operation_type == 'read' else 'edit'

    try:
        from claude_code.utils.permissions.permissions import (
            matching_rule_for_input, path_in_allowed_working_path
        )
        # 1. Check deny rules
        deny_rule = matching_rule_for_input(
            resolved_path, tool_permission_context, permission_type, 'deny'
        )
        if deny_rule is not None:
            return {
                'allowed': False,
                'decision_reason': {'type': 'rule', 'rule': deny_rule},
            }

        # 2. Check if path is in working directory
        in_working_dir = path_in_allowed_working_path(
            resolved_path, tool_permission_context
        )
        if in_working_dir:
            if operation_type == 'read' or getattr(tool_permission_context, 'mode', '') == 'acceptEdits':
                return {'allowed': True}

        # 3. Check allow rules
        allow_rule = matching_rule_for_input(
            resolved_path, tool_permission_context, permission_type, 'allow'
        )
        if allow_rule is not None:
            return {
                'allowed': True,
                'decision_reason': {'type': 'rule', 'rule': allow_rule},
            }

        return {'allowed': False}
    except (ImportError, Exception):
        return {'allowed': True}


# ─── lookupCmdletPathConfig ───────────────────────────────────────────────────

def _lookup_cmdlet_path_config(name: str) -> Optional[CmdletPathConfig]:
    """Looks up the path config for a cmdlet, resolving aliases."""
    from claude_code.tools.power_shell_tool.read_only_validation import resolve_to_canonical
    lower = name.lower()
    direct = CMDLET_PATH_CONFIG.get(lower)
    if direct is not None:
        return direct
    canonical = resolve_to_canonical(lower)
    if canonical != lower:
        return CMDLET_PATH_CONFIG.get(canonical)
    return None


# ─── extractPathsFromCommand ─────────────────────────────────────────────────

def extract_paths_from_command(
    cmd: ParsedCommandElement,
) -> Dict[str, Any]:
    """
    Extracts filesystem paths from a parsed command element based on CMDLET_PATH_CONFIG.

    Returns:
        {
            'paths': List[str],
            'operationType': str,
            'hasUnvalidatablePathArg': bool,
        }
    """
    name = cmd.get('name', '')
    config = _lookup_cmdlet_path_config(name)
    if config is None:
        return {'paths': [], 'operationType': 'read', 'hasUnvalidatablePathArg': False}

    paths: List[str] = []
    has_unvalidatable = False
    args = cmd.get('args') or []
    elem_types = cmd.get('elementTypes') or []
    operation_type = config['operationType']
    path_params = config.get('pathParams') or []
    known_switches = config.get('knownSwitches') or []
    known_value_params = config.get('knownValueParams') or []
    leaf_only_path_params = config.get('leafOnlyPathParams') or []
    positional_skip = config.get('positionalSkip', 0)

    # Build effective known_switches and known_value_params (including common ones)
    eff_switches = set(known_switches) | COMMON_SWITCHES
    eff_value_params = set(known_value_params) | COMMON_VALUE_PARAMS

    positional_index = 0
    i = 0
    while i < len(args):
        arg = args[i]
        elem_type = elem_types[i + 1] if i + 1 < len(elem_types) else None

        # Check if this is a parameter (flag)
        is_flag = (elem_type == 'Parameter') or (arg.startswith('-') and arg != '-')
        is_slash_flag = (os.name == 'nt' and arg.startswith('/') and not arg.startswith('//'))

        if is_flag or is_slash_flag:
            # Normalize parameter name
            param_lower = arg.lower()
            # Strip colon-bound value
            colon_idx = param_lower.find(':')
            if colon_idx > 0:
                param_name = param_lower[:colon_idx]
                colon_value = arg[colon_idx + 1:]
            else:
                param_name = param_lower
                colon_value = None

            if _matches_param(param_name, [p.lower() for p in path_params]):
                # This is a path parameter
                if colon_value is not None:
                    # Colon-bound syntax: -Path:/some/path
                    if _has_complex_colon_value(colon_value):
                        has_unvalidatable = True
                    else:
                        paths.append(colon_value)
                elif i + 1 < len(args):
                    # Next arg is the path value
                    next_arg = args[i + 1]
                    next_type = elem_types[i + 2] if i + 2 < len(elem_types) else None
                    if next_type not in ('StringConstant', 'Parameter', None):
                        has_unvalidatable = True
                    elif next_arg.startswith('-'):
                        # Next arg is another flag, no value
                        pass
                    else:
                        # Could be multiple comma-separated paths
                        for p in next_arg.split(','):
                            p = p.strip()
                            if p:
                                paths.append(p)
                        i += 1
                i += 1
                continue

            if _matches_param(param_name, [p.lower() for p in leaf_only_path_params]):
                # Leaf-only path parameter
                if colon_value is not None:
                    if _has_complex_colon_value(colon_value):
                        has_unvalidatable = True
                    elif re.search(r'[/\\.]', colon_value):
                        # Non-leaf (has path separators or dots) — unvalidatable
                        has_unvalidatable = True
                    else:
                        paths.append(colon_value)
                elif i + 1 < len(args):
                    next_arg = args[i + 1]
                    if not next_arg.startswith('-'):
                        if re.search(r'[/\\.]', next_arg):
                            has_unvalidatable = True
                        else:
                            paths.append(next_arg)
                        i += 1
                i += 1
                continue

            if _matches_param(param_name, list(eff_switches)):
                # Switch parameter: no value consumed
                i += 1
                continue

            if _matches_param(param_name, list(eff_value_params)):
                # Value parameter: skip the next arg
                if colon_value is None and i + 1 < len(args):
                    next_arg = args[i + 1]
                    if not next_arg.startswith('-'):
                        i += 1
                i += 1
                continue

            # Unknown parameter — could trap a path arg
            if colon_value is None and i + 1 < len(args):
                next_arg = args[i + 1]
                if not next_arg.startswith('-'):
                    # Unknown param consumed this arg; we can't validate it
                    has_unvalidatable = True
                    i += 1
            i += 1
            continue

        # Positional argument
        skip = positional_skip
        if positional_index < skip:
            positional_index += 1
            i += 1
            continue

        # This could be a path positional
        if elem_type not in ('StringConstant', None):
            has_unvalidatable = True
        elif arg and not arg.startswith('-'):
            # Comma-separated values
            for p in arg.split(','):
                p = p.strip()
                if p:
                    paths.append(p)
        positional_index += 1
        i += 1

    return {
        'paths': paths,
        'operationType': operation_type,
        'hasUnvalidatablePathArg': has_unvalidatable,
    }


# ─── checkPathConstraints ────────────────────────────────────────────────────

def check_path_constraints(
    cmd: ParsedCommandElement,
    cwd: str,
    tool_permission_context: ToolPermissionContext,
    original_command: str,
) -> PermissionResult:
    """
    Validates path arguments in a parsed command against allowed directories.

    Returns a PermissionResult dict:
    - {'behavior': 'allow'} if all paths are allowed
    - {'behavior': 'ask', 'message': ...} if paths need approval
    - {'behavior': 'deny', 'message': ...} if a path is explicitly denied
    """
    config = _lookup_cmdlet_path_config(cmd.get('name', ''))
    if config is None:
        # No path config — not a path-sensitive cmdlet
        return {'behavior': 'allow'}

    extracted = extract_paths_from_command(cmd)
    paths = extracted['paths']
    operation_type = extracted['operationType']
    has_unvalidatable = extracted['hasUnvalidatablePathArg']

    # Check for redirection targets (these are always file writes)
    redirections = cmd.get('redirections') or []
    for redir in redirections:
        target = redir.get('target', '')
        if not redir.get('isMerging') and not _is_null_redirection_target(target):
            paths.append(target)
            if operation_type == 'read':
                operation_type = 'write'

    # If unvalidatable, ask
    if has_unvalidatable:
        return {
            'behavior': 'ask',
            'message': (
                f'Cannot statically validate all path arguments for {cmd.get("name", "")}. '
                'Manual approval required.'
            ),
        }

    # For write cmdlets with optionalWrite, if no paths found it's effectively read
    if not paths and config.get('optionalWrite'):
        return {'behavior': 'allow'}

    # For write cmdlets with no path args at all — ask (can't validate)
    if not paths and operation_type != 'read':
        return {
            'behavior': 'ask',
            'message': f'Cannot determine write target for {cmd.get("name", "")}',
        }

    # Validate each path
    denied_paths = []
    ask_paths = []

    for raw_path in paths:
        # Glob patterns: skip validation (wildcard expansion is runtime-only)
        if GLOB_PATTERN_REGEX.search(raw_path):
            # Still check dangerous removal
            if resolve_to_canonical_name(cmd) in ('remove-item',) and \
                    is_dangerous_removal_raw_path(raw_path):
                return dangerous_removal_deny(raw_path)
            continue

        # Check dangerous removal for remove-item
        canonical = resolve_to_canonical_name(cmd)
        if canonical in ('remove-item',) and is_dangerous_removal_raw_path(raw_path):
            return dangerous_removal_deny(raw_path)

        result = _validate_path(raw_path, cwd, tool_permission_context, operation_type)
        if not result['allowed']:
            decision = result.get('decision_reason') or {}
            if decision.get('type') == 'rule':
                # Explicit deny rule
                return {
                    'behavior': 'deny',
                    'message': (
                        f"Access to '{result['resolved_path']}' is denied by rule."
                    ),
                    'decisionReason': decision,
                }
            else:
                ask_paths.append(result['resolved_path'])

    if ask_paths:
        dirs_str = _format_directory_list(ask_paths)
        return {
            'behavior': 'ask',
            'message': (
                f'Path(s) {dirs_str} are outside allowed working directories. '
                'Manual approval required.'
            ),
        }

    return {'behavior': 'allow'}


def resolve_to_canonical_name(cmd: ParsedCommandElement) -> str:
    """Helper to get canonical cmdlet name from a command element."""
    from claude_code.tools.power_shell_tool.read_only_validation import resolve_to_canonical
    return resolve_to_canonical(cmd.get('name', ''))


def _is_null_redirection_target(target: str) -> bool:
    return target.lower() in ('$null', 'nul', '/dev/null', '')


# TODO: checkPathConstraints and related - see part 2
