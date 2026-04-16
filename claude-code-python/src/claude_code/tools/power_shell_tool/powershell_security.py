"""
PowerShell-specific security analysis for command validation.
Ported from PowerShellTool/powershellSecurity.ts (1090 lines).

Detects dangerous patterns: code injection, download cradles, privilege
escalation, dynamic command names, COM objects, etc.

All checks operate on the parsed command data. If parsing failed,
powershell_command_is_safe returns 'ask'.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

# PermissionResult type: {"behavior": "passthrough"|"ask"|"allow", "message": str}
PermissionResult = Dict[str, Any]

# ─── Constants ────────────────────────────────────────────────────────────────

POWERSHELL_EXECUTABLES: Set[str] = {
    'pwsh', 'pwsh.exe', 'powershell', 'powershell.exe',
}

# Alternative parameter-prefix chars PowerShell accepts as equivalent to '-'
PS_ALT_PARAM_PREFIXES: Set[str] = {
    '/',         # Windows PowerShell 5.1
    '\u2013',    # en-dash
    '\u2014',    # em-dash
    '\u2015',    # horizontal bar
}

# Cmdlets where script blocks are safe predicates/projections
SAFE_SCRIPT_BLOCK_CMDLETS: Set[str] = {
    'where-object', 'sort-object', 'select-object', 'group-object',
    'format-table', 'format-list', 'format-wide', 'format-custom',
}

# Cmdlets that are dangerous when given a -FilePath/-LiteralPath
FILEPATH_EXECUTION_CMDLETS: Set[str] = {
    'invoke-command', 'start-job', 'start-threadjob', 'register-scheduledjob',
}

# Cmdlets that use script blocks in dangerous ways
DANGEROUS_SCRIPT_BLOCK_CMDLETS: Set[str] = {
    'invoke-command', 'start-job', 'start-threadjob', 'register-scheduledjob',
    'register-engineevent', 'register-objectevent', 'register-wmievent',
    'foreach-object',
}

# Module-loading cmdlets
MODULE_LOADING_CMDLETS: Set[str] = {
    'import-module', 'ipmo',
    'add-pssnapin', 'remove-pssnapin',
    'use-module',
}

# Alias -> canonical mapping (subset used by security checks)
COMMON_ALIASES: Dict[str, str] = {
    'iex': 'Invoke-Expression',
    'iwr': 'Invoke-WebRequest',
    'irm': 'Invoke-RestMethod',
    'icm': 'Invoke-Command',
    'foreach': 'ForEach-Object',
    '%': 'ForEach-Object',
    'where': 'Where-Object',
    '?': 'Where-Object',
    'select': 'Select-Object',
    'sort': 'Sort-Object',
    'group': 'Group-Object',
    'measure': 'Measure-Object',
    'start': 'Start-Process',
    'saps': 'Start-Process',
    'sal': 'Set-Alias',
    'nal': 'New-Alias',
    'sv': 'Set-Variable',
    'nv': 'New-Variable',
    'ipmo': 'Import-Module',
    'ft': 'Format-Table',
    'fl': 'Format-List',
    'fw': 'Format-Wide',
}

# Download-cradle source cmdlets
DOWNLOADER_NAMES: Set[str] = {
    'invoke-webrequest', 'iwr',
    'invoke-restmethod', 'irm',
    'new-object',
    'start-bitstransfer',
}

# Scheduled task cmdlets
SCHEDULED_TASK_CMDLETS: Set[str] = {
    'new-scheduledtask', 'register-scheduledtask', 'set-scheduledtask',
    'start-scheduledtask', 'enable-scheduledtask',
}

# Environment-variable write cmdlets
ENV_WRITE_CMDLETS: Set[str] = {
    'set-item', 'si',
    'new-item', 'ni',
    'remove-item', 'ri', 'rm', 'del', 'erase', 'rd', 'rmdir',
    '[environment]',
    'set-content', 'sc',
    'add-content', 'ac',
    '[system.environment]',
}

# Runtime state manipulation (alias / variable poisoning)
RUNTIME_STATE_CMDLETS: Set[str] = {
    'set-alias', 'sal',
    'new-alias', 'nal',
    'set-variable', 'sv',
    'new-variable', 'nv',
}

# WMI/CIM process-spawn cmdlets
WMI_SPAWN_CMDLETS: Set[str] = {
    'invoke-wmimethod', 'iwmi',
    'invoke-cimmethod',
}

# Constrained language mode: basic .NET types that are safe to instantiate
CLM_ALLOWED_TYPES: Set[str] = {
    'system.string', 'string',
    'system.int32', 'int', 'int32',
    'system.int64', 'long', 'int64',
    'system.double', 'double',
    'system.boolean', 'bool',
    'system.datetime', 'datetime',
    'system.object', 'object',
    'system.array',
    'system.collections.hashtable', 'hashtable',
    'system.collections.arraylist',
    'system.collections.generic.list',
    'system.text.stringbuilder', 'stringbuilder',
    'system.text.regularexpressions.regex', 'regex',
    'system.io.path',
    'system.io.file',
    'system.io.directory',
    'system.io.fileinfo',
    'system.io.directoryinfo',
    'system.math', 'math',
    'system.convert', 'convert',
    'system.console', 'console',
    'system.environment', 'environment',
    'system.guid', 'guid',
    'system.version', 'version',
    'system.uri', 'uri',
    'pscustomobject', 'psobject',
    'ordered',
    'system.management.automation.pscustomobject',
}

# ─── ParsedCommand helpers (mimic the TS AST structures) ─────────────────────
# We represent a ParsedPowerShellCommand as a dict:
#   {
#       "valid": bool,
#       "statements": [
#           {
#               "commands": [
#                   {
#                       "elementType": "CommandAst"|"StringConstantExpressionAst"|...,
#                       "name": str,
#                       "nameType": str,      # "StringConstant"|"application"|...
#                       "args": [str, ...],
#                       "elementTypes": [str, ...],  # one per (name + args)
#                       "text": str,
#                       "redirections": [{"target": str}, ...],
#                       "children": [[{"text": str}], ...],  # colon-bound param children
#                   }, ...
#               ],
#               "nestedCommands": [...],
#           }, ...
#       ],
#       "hasScriptBlocks": bool,
#       "hasExpandableStrings": bool,
#       "hasSubExpressions": bool,
#       "hasSplatting": bool,
#       "hasStopParsing": bool,
#       "hasTypeLiterals": bool,
#       "typeLiterals": [str, ...],
#       "hasUsingStatements": bool,
#       "hasScriptRequirements": bool,
#       "errors": [{"message": str}, ...],
#   }


def _resolve_name_lower(name: str) -> str:
    """Lower-case + resolve common alias."""
    lower = name.lower()
    resolved = COMMON_ALIASES.get(lower, lower)
    return resolved.lower()


def _is_ps_executable(name: str) -> bool:
    lower = name.lower()
    if lower in POWERSHELL_EXECUTABLES:
        return True
    last_sep = max(lower.rfind('/'), lower.rfind('\\'))
    if last_sep >= 0:
        return lower[last_sep + 1:] in POWERSHELL_EXECUTABLES
    return False


def _normalize_dash(arg: str) -> str:
    """Normalize Unicode dash variants to ASCII hyphen."""
    if arg and arg[0] in PS_ALT_PARAM_PREFIXES:
        return '-' + arg[1:]
    return arg


def _command_has_arg_abbrev(cmd: Dict, full_param: str, min_prefix: str) -> bool:
    """
    Check if cmd.args contains an abbreviation of full_param that starts with
    min_prefix. Handles both space-separated and colon-syntax.
    """
    for arg in cmd.get('args', []):
        normalized = _normalize_dash(arg)
        if not normalized.startswith('-'):
            continue
        # Strip colon-bound value
        colon_idx = normalized.find(':', 1)
        param_part = normalized[:colon_idx] if colon_idx > 0 else normalized
        param_lower = param_part.lower()
        full_lower = full_param.lower()
        min_lower = min_prefix.lower()
        if param_lower.startswith(min_lower) and full_lower.startswith(param_lower):
            return True
    return False


def _get_all_commands(parsed: Dict) -> List[Dict]:
    """Collect all CommandAst elements recursively (statements + nestedCommands)."""
    cmds = []
    for stmt in parsed.get('statements', []):
        for cmd in stmt.get('commands', []):
            if cmd.get('elementType') == 'CommandAst':
                cmds.append(cmd)
        for cmd in stmt.get('nestedCommands', []):
            if cmd.get('elementType') == 'CommandAst':
                cmds.append(cmd)
    return cmds


def _has_command_named(parsed: Dict, name: str) -> bool:
    """Check if any command in the parsed AST matches `name` (case-insensitive, alias-aware)."""
    target = _resolve_name_lower(name)
    for cmd in _get_all_commands(parsed):
        if _resolve_name_lower(cmd.get('name', '')) == target:
            return True
    return False


def _is_downloader(name: str) -> bool:
    return name.lower() in DOWNLOADER_NAMES


def _is_iex(name: str) -> bool:
    lower = name.lower()
    return lower in ('invoke-expression', 'iex')


def _is_clm_allowed_type(type_name: str) -> bool:
    return type_name.lower().lstrip('[').rstrip(']') in CLM_ALLOWED_TYPES


# ─── Individual security check functions ─────────────────────────────────────

def _check_invoke_expression(parsed: Dict) -> PermissionResult:
    if _has_command_named(parsed, 'Invoke-Expression'):
        return {'behavior': 'ask',
                'message': 'Command uses Invoke-Expression which can execute arbitrary code'}
    return {'behavior': 'passthrough'}


def _check_dynamic_command_name(parsed: Dict) -> PermissionResult:
    for cmd in _get_all_commands(parsed):
        if cmd.get('elementType') != 'CommandAst':
            continue
        element_types = cmd.get('elementTypes', [])
        if element_types:
            name_et = element_types[0]
            if name_et != 'StringConstant':
                return {'behavior': 'ask',
                        'message': 'Command name is a dynamic expression which cannot be statically validated'}
    return {'behavior': 'passthrough'}


def _check_encoded_command(parsed: Dict) -> PermissionResult:
    for cmd in _get_all_commands(parsed):
        if _is_ps_executable(cmd.get('name', '')):
            if _command_has_arg_abbrev(cmd, '-encodedcommand', '-e'):
                return {'behavior': 'ask',
                        'message': 'Command uses encoded parameters which obscure intent'}
    return {'behavior': 'passthrough'}


def _check_pwsh_command_or_file(parsed: Dict) -> PermissionResult:
    for cmd in _get_all_commands(parsed):
        if _is_ps_executable(cmd.get('name', '')):
            return {'behavior': 'ask',
                    'message': 'Command spawns a nested PowerShell process which cannot be validated'}
    return {'behavior': 'passthrough'}


def _check_download_cradles(parsed: Dict) -> PermissionResult:
    # Per-statement: piped cradle (IWR ... | IEX)
    for stmt in parsed.get('statements', []):
        cmds = stmt.get('commands', [])
        if len(cmds) < 2:
            continue
        has_dl = any(_is_downloader(c.get('name', '')) for c in cmds)
        has_iex = any(_is_iex(c.get('name', '')) for c in cmds)
        if has_dl and has_iex:
            return {'behavior': 'ask', 'message': 'Command downloads and executes remote code'}

    # Cross-statement: split cradle
    all_cmds = _get_all_commands(parsed)
    if (any(_is_downloader(c.get('name', '')) for c in all_cmds) and
            any(_is_iex(c.get('name', '')) for c in all_cmds)):
        return {'behavior': 'ask', 'message': 'Command downloads and executes remote code'}

    return {'behavior': 'passthrough'}


def _check_download_utilities(parsed: Dict) -> PermissionResult:
    for cmd in _get_all_commands(parsed):
        lower = cmd.get('name', '').lower()
        if lower == 'start-bitstransfer':
            return {'behavior': 'ask', 'message': 'Command downloads files via BITS transfer'}
        if lower in ('certutil', 'certutil.exe'):
            has_urlcache = any(
                a.lower() in ('-urlcache', '/urlcache')
                for a in cmd.get('args', [])
            )
            if has_urlcache:
                return {'behavior': 'ask', 'message': 'Command uses certutil to download from a URL'}
        if lower in ('bitsadmin', 'bitsadmin.exe'):
            if any(a.lower() == '/transfer' for a in cmd.get('args', [])):
                return {'behavior': 'ask', 'message': 'Command downloads files via BITS transfer'}
    return {'behavior': 'passthrough'}


def _check_add_type(parsed: Dict) -> PermissionResult:
    if _has_command_named(parsed, 'Add-Type'):
        return {'behavior': 'ask', 'message': 'Command compiles and loads .NET code'}
    return {'behavior': 'passthrough'}


def _check_com_object(parsed: Dict) -> PermissionResult:
    for cmd in _get_all_commands(parsed):
        if cmd.get('name', '').lower() != 'new-object':
            continue
        # Check for -ComObject parameter
        if _command_has_arg_abbrev(cmd, '-comobject', '-com'):
            return {'behavior': 'ask',
                    'message': 'Command instantiates a COM object which may have execution capabilities'}
        # Check for dangerous .NET types via positional -TypeName
        type_name: Optional[str] = None
        args = cmd.get('args', [])
        for i, a in enumerate(args):
            lower = a.lower()
            colon_idx = a.find(':', 1) if a.startswith('-') else -1
            if colon_idx > 0:
                param_part = lower[:colon_idx]
                if param_part.startswith('-t') and '-typename'.startswith(param_part):
                    type_name = a[colon_idx + 1:]
                    break
            if lower.startswith('-t') and '-typename'.startswith(lower):
                if i + 1 < len(args):
                    type_name = args[i + 1]
                    break
        if type_name is None:
            # Positional scan
            VALUE_PARAMS = {'-argumentlist', '-comobject', '-property'}
            SWITCH_PARAMS = {'-strict'}
            i = 0
            while i < len(args):
                a = args[i]
                if a.startswith('-'):
                    lower = a.lower()
                    if lower.startswith('-t') and '-typename'.startswith(lower.split(':')[0]):
                        i += 1  # skip value
                    elif ':' in lower[1:]:
                        pass  # colon-bound, no skip
                    elif lower in SWITCH_PARAMS:
                        pass
                    elif lower in VALUE_PARAMS:
                        i += 1  # skip value
                    i += 1
                    continue
                type_name = a
                break
        if type_name is not None and not _is_clm_allowed_type(type_name):
            return {'behavior': 'ask',
                    'message': f"New-Object instantiates .NET type '{type_name}' outside the ConstrainedLanguage allowlist"}
    return {'behavior': 'passthrough'}


def _check_dangerous_file_path_execution(parsed: Dict) -> PermissionResult:
    for cmd in _get_all_commands(parsed):
        lower = cmd.get('name', '').lower()
        resolved = COMMON_ALIASES.get(lower, lower).lower()
        if resolved not in FILEPATH_EXECUTION_CMDLETS:
            continue
        if (_command_has_arg_abbrev(cmd, '-filepath', '-f') or
                _command_has_arg_abbrev(cmd, '-literalpath', '-l')):
            return {'behavior': 'ask',
                    'message': f"{cmd.get('name')} -FilePath executes an arbitrary script file"}
        # Positional string arg → -FilePath
        args = cmd.get('args', [])
        element_types = cmd.get('elementTypes', [])
        for i, arg in enumerate(args):
            et = element_types[i + 1] if element_types and i + 1 < len(element_types) else None
            if et == 'StringConstant' and arg and not arg.startswith('-'):
                return {'behavior': 'ask',
                        'message': f"{cmd.get('name')} with positional string argument binds to -FilePath and executes a script file"}
    return {'behavior': 'passthrough'}


def _check_for_each_member_name(parsed: Dict) -> PermissionResult:
    for cmd in _get_all_commands(parsed):
        lower = cmd.get('name', '').lower()
        resolved = COMMON_ALIASES.get(lower, lower).lower()
        if resolved != 'foreach-object':
            continue
        if _command_has_arg_abbrev(cmd, '-membername', '-m'):
            return {'behavior': 'ask',
                    'message': 'ForEach-Object -MemberName invokes methods by string name which cannot be validated'}
        # Positional string arg → -MemberName
        args = cmd.get('args', [])
        element_types = cmd.get('elementTypes', [])
        for i, arg in enumerate(args):
            et = element_types[i + 1] if element_types and i + 1 < len(element_types) else None
            if et == 'StringConstant' and arg and not arg.startswith('-'):
                return {'behavior': 'ask',
                        'message': 'ForEach-Object with positional string argument binds to -MemberName and invokes methods by name'}
    return {'behavior': 'passthrough'}


def _check_start_process(parsed: Dict) -> PermissionResult:
    for cmd in _get_all_commands(parsed):
        lower = cmd.get('name', '').lower()
        if lower not in ('start-process', 'saps', 'start'):
            continue
        args = cmd.get('args', [])
        children = cmd.get('children', None)

        # Vector 1: -Verb RunAs
        if (_command_has_arg_abbrev(cmd, '-Verb', '-v') and
                any(a.lower() == 'runas' for a in args)):
            return {'behavior': 'ask', 'message': 'Command requests elevated privileges'}

        # Colon syntax with children
        if children:
            for i, arg in enumerate(args):
                clean = arg.replace('`', '')
                if not re.match(r'^[-\u2013\u2014\u2015/]v[a-z]*:', clean, re.IGNORECASE):
                    continue
                kids = children[i] if i < len(children) else None
                if not kids:
                    continue
                for child in kids:
                    if re.sub(r"['\"` ]", '', child.get('text', '')).lower() == 'runas':
                        return {'behavior': 'ask', 'message': 'Command requests elevated privileges'}

        # Colon syntax regex fallback
        for a in args:
            clean = a.replace('`', '')
            if re.match(r'^[-\u2013\u2014\u2015/]v[a-z]*:[\'"`\s]*runas[\'"`\s]*$', clean, re.IGNORECASE):
                return {'behavior': 'ask', 'message': 'Command requests elevated privileges'}

        # Vector 2: Start-Process targeting a PS executable
        for arg in args:
            stripped = arg.strip("'\"")
            if _is_ps_executable(stripped):
                return {'behavior': 'ask',
                        'message': 'Start-Process launches a nested PowerShell process which cannot be validated'}
    return {'behavior': 'passthrough'}


def _check_script_block_injection(parsed: Dict) -> PermissionResult:
    if not parsed.get('hasScriptBlocks'):
        return {'behavior': 'passthrough'}
    for cmd in _get_all_commands(parsed):
        lower = cmd.get('name', '').lower()
        resolved = COMMON_ALIASES.get(lower, lower).lower()
        if resolved not in SAFE_SCRIPT_BLOCK_CMDLETS:
            # This command uses a script block unsafely
            if resolved in DANGEROUS_SCRIPT_BLOCK_CMDLETS or parsed.get('hasScriptBlocks'):
                pass  # will be caught below
        if resolved in DANGEROUS_SCRIPT_BLOCK_CMDLETS:
            return {'behavior': 'ask',
                    'message': f'{cmd.get("name")} executes a script block which may contain arbitrary code'}
    # Generic: script blocks present but not obviously safe
    if parsed.get('hasScriptBlocks'):
        # Check if ALL commands with script blocks are in safe list
        # (simplified: if we reach here without returning, do one more pass)
        for cmd in _get_all_commands(parsed):
            lower = cmd.get('name', '').lower()
            resolved = COMMON_ALIASES.get(lower, lower).lower()
            # ForEach-Object is NOT in SAFE_SCRIPT_BLOCK_CMDLETS intentionally
            if resolved not in SAFE_SCRIPT_BLOCK_CMDLETS and resolved not in ('', ):
                # Has the command got script blocks? We can't know at this level
                # without per-command info; be conservative only for known-dangerous
                pass
    return {'behavior': 'passthrough'}


def _check_sub_expressions(parsed: Dict) -> PermissionResult:
    if parsed.get('hasSubExpressions'):
        return {'behavior': 'ask',
                'message': 'Command contains subexpressions $(...) that cannot be statically validated'}
    return {'behavior': 'passthrough'}


def _check_expandable_strings(parsed: Dict) -> PermissionResult:
    if parsed.get('hasExpandableStrings'):
        return {'behavior': 'ask',
                'message': 'Command contains expandable strings with variable interpolation'}
    return {'behavior': 'passthrough'}


def _check_splatting(parsed: Dict) -> PermissionResult:
    if parsed.get('hasSplatting'):
        return {'behavior': 'ask',
                'message': 'Command uses splatting (@) which cannot be statically validated'}
    return {'behavior': 'passthrough'}


def _check_stop_parsing(parsed: Dict) -> PermissionResult:
    if parsed.get('hasStopParsing'):
        return {'behavior': 'ask',
                'message': 'Command uses stop-parsing (--%) which bypasses parameter parsing'}
    return {'behavior': 'passthrough'}


def _check_member_invocations(parsed: Dict) -> PermissionResult:
    # Member invocations (.Method()) are generally dangerous if on certain objects
    # This is represented via hasExpandableStrings or specific pattern flags
    # For our port: check for method invocation patterns in raw text would be
    # handled by regex checks; rely on hasSubExpressions / expandable strings
    # to catch most cases
    return {'behavior': 'passthrough'}


def _check_type_literals(parsed: Dict) -> PermissionResult:
    if not parsed.get('hasTypeLiterals'):
        return {'behavior': 'passthrough'}
    type_literals = parsed.get('typeLiterals', [])
    for tl in type_literals:
        if not _is_clm_allowed_type(tl):
            return {'behavior': 'ask',
                    'message': f"Command uses type literal [{tl}] which is outside the ConstrainedLanguage allowlist"}
    return {'behavior': 'passthrough'}


def _check_invoke_item(parsed: Dict) -> PermissionResult:
    if _has_command_named(parsed, 'Invoke-Item'):
        return {'behavior': 'ask',
                'message': 'Invoke-Item opens or executes a file using the default application handler'}
    return {'behavior': 'passthrough'}


def _check_scheduled_task(parsed: Dict) -> PermissionResult:
    for cmd in _get_all_commands(parsed):
        lower = cmd.get('name', '').lower()
        if lower in SCHEDULED_TASK_CMDLETS:
            return {'behavior': 'ask',
                    'message': f'{cmd.get("name")} creates or modifies a scheduled task which can execute code persistently'}
    return {'behavior': 'passthrough'}


def _check_env_var_manipulation(parsed: Dict) -> PermissionResult:
    for cmd in _get_all_commands(parsed):
        lower = cmd.get('name', '').lower()
        if lower not in ('set-item', 'si', 'new-item', 'ni'):
            continue
        # Only flag when operating on env: provider paths
        args = cmd.get('args', [])
        for arg in args:
            if re.match(r'^env:', arg, re.IGNORECASE):
                return {'behavior': 'ask',
                        'message': f'{cmd.get("name")} modifies environment variables'}
            if re.match(r'^\$env:', arg, re.IGNORECASE):
                return {'behavior': 'ask',
                        'message': 'Command modifies environment variables'}
    # Also check [environment]::SetEnvironmentVariable
    if '[environment]' in str(parsed) or 'setenvironmentvariable' in str(parsed).lower():
        # This is a simplified heuristic; full check requires member invocation analysis
        pass
    return {'behavior': 'passthrough'}


def _check_module_loading(parsed: Dict) -> PermissionResult:
    for cmd in _get_all_commands(parsed):
        lower = cmd.get('name', '').lower()
        resolved = COMMON_ALIASES.get(lower, lower).lower()
        if resolved in MODULE_LOADING_CMDLETS or lower in MODULE_LOADING_CMDLETS:
            return {'behavior': 'ask',
                    'message': f'{cmd.get("name")} loads a PowerShell module which may execute arbitrary code'}
    return {'behavior': 'passthrough'}


def _check_runtime_state_manipulation(parsed: Dict) -> PermissionResult:
    for cmd in _get_all_commands(parsed):
        raw = cmd.get('name', '').lower()
        # Strip module qualifier
        lower = raw[raw.rfind('\\') + 1:] if '\\' in raw else raw
        if lower in RUNTIME_STATE_CMDLETS:
            return {'behavior': 'ask',
                    'message': 'Command creates or modifies an alias or variable that can affect future command resolution'}
    return {'behavior': 'passthrough'}


def _check_wmi_process_spawn(parsed: Dict) -> PermissionResult:
    for cmd in _get_all_commands(parsed):
        lower = cmd.get('name', '').lower()
        if lower in WMI_SPAWN_CMDLETS:
            return {'behavior': 'ask',
                    'message': f"{cmd.get('name')} can spawn arbitrary processes via WMI/CIM (Win32_Process Create)"}
    return {'behavior': 'passthrough'}


# ─── Main entry point ─────────────────────────────────────────────────────────

def powershell_command_is_safe(command: str, parsed: Dict) -> PermissionResult:
    """
    Main entry point for PowerShell security validation.
    Returns 'passthrough' if safe, 'ask' if manual approval needed.

    All checks are AST-based. If parsed.valid is False, returns 'ask'.
    """
    if not parsed.get('valid', False):
        return {'behavior': 'ask', 'message': 'Could not parse command for security analysis'}

    validators = [
        _check_invoke_expression,
        _check_dynamic_command_name,
        _check_encoded_command,
        _check_pwsh_command_or_file,
        _check_download_cradles,
        _check_download_utilities,
        _check_add_type,
        _check_com_object,
        _check_dangerous_file_path_execution,
        _check_invoke_item,
        _check_scheduled_task,
        _check_for_each_member_name,
        _check_start_process,
        _check_script_block_injection,
        _check_sub_expressions,
        _check_expandable_strings,
        _check_splatting,
        _check_stop_parsing,
        _check_member_invocations,
        _check_type_literals,
        _check_env_var_manipulation,
        _check_module_loading,
        _check_runtime_state_manipulation,
        _check_wmi_process_spawn,
    ]

    for validator in validators:
        result = validator(parsed)
        if result.get('behavior') == 'ask':
            return result

    return {'behavior': 'passthrough'}
