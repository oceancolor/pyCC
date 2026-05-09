"""
bash_permissions.py - Python port of bashPermissions.ts

Permission checking logic for BashTool commands.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from typing import (
    Any, Callable, Dict, List, Mapping, Optional, Set, Tuple
)

# ---------------------------------------------------------------------------
# Soft imports — graceful fallback when sibling modules aren't yet ported
# ---------------------------------------------------------------------------
try:
    from ..permissions.PermissionResult import PermissionResult  # type: ignore
except ImportError:
    @dataclass
    class PermissionResult:  # type: ignore[no-redef]
        behavior: str  # 'allow' | 'ask' | 'deny' | 'passthrough'
        message: str = ""
        updated_input: Optional[Dict[str, Any]] = None
        decision_reason: Optional[Dict[str, Any]] = None
        suggestions: Optional[List[Any]] = None
        is_bash_security_check_for_misparsing: bool = False
        pending_classifier_check: Optional[Dict[str, Any]] = None

try:
    from ..permissions.PermissionRule import PermissionRule, PermissionRuleValue  # type: ignore
except ImportError:
    PermissionRule = Any  # type: ignore
    PermissionRuleValue = Any  # type: ignore

try:
    from ..permissions.PermissionUpdate import PermissionUpdate  # type: ignore
except ImportError:
    PermissionUpdate = Any  # type: ignore

try:
    from ...utils.bash.commands import (  # type: ignore
        extract_output_redirections,
        get_command_subcommand_prefix,
        split_command_deprecated as split_command,
    )
except ImportError:
    def extract_output_redirections(cmd):  # type: ignore
        class _R:
            command_without_redirections = cmd
        return _R()

    async def get_command_subcommand_prefix(*a, **kw):  # type: ignore
        return None

    def split_command(cmd: str) -> List[str]:  # type: ignore
        return [cmd]

try:
    from ...utils.bash.parser import parse_command_raw  # type: ignore
except ImportError:
    async def parse_command_raw(cmd: str):  # type: ignore
        return None

try:
    from ...utils.bash.ast import (  # type: ignore
        check_semantics,
        node_type_id,
        parse_for_security_from_ast,
        ParseForSecurityResult,
        Redirect,
        SimpleCommand,
    )
except ImportError:
    def check_semantics(commands):  # type: ignore
        class _R:
            ok = True
            reason = ''
        return _R()

    def node_type_id(nt):  # type: ignore
        return 0

    def parse_for_security_from_ast(cmd, ast_root):  # type: ignore
        return {'kind': 'parse-unavailable'}

    ParseForSecurityResult = Any  # type: ignore
    Redirect = Any  # type: ignore
    SimpleCommand = Any  # type: ignore

try:
    from ...utils.bash.shellQuote import try_parse_shell_command  # type: ignore
except ImportError:
    def try_parse_shell_command(cmd: str):  # type: ignore
        class _R:
            success = False
            tokens: List[Any] = []
            error = 'not implemented'
        return _R()

try:
    from ...utils.cwd import get_cwd  # type: ignore
except ImportError:
    def get_cwd() -> str:  # type: ignore
        return os.getcwd()

try:
    from ...utils.debug import log_for_debugging  # type: ignore
except ImportError:
    def log_for_debugging(msg: str, **kw) -> None:  # type: ignore
        pass

try:
    from ...utils.envUtils import is_env_truthy  # type: ignore
except ImportError:
    def is_env_truthy(val: Optional[str]) -> bool:  # type: ignore
        return val is not None and val.lower() in ('1', 'true', 'yes')

try:
    from ...utils.errors import AbortError  # type: ignore
except ImportError:
    class AbortError(Exception):  # type: ignore[no-redef]
        pass

try:
    from ...utils.permissions.bash_classifier import (  # type: ignore
        classify_bash_command,
        get_bash_prompt_allow_descriptions,
        get_bash_prompt_ask_descriptions,
        get_bash_prompt_deny_descriptions,
        is_classifier_permissions_enabled,
    )
except ImportError:
    def classify_bash_command(*a, **kw):  # type: ignore
        async def _noop():
            return None
        return _noop()

    def get_bash_prompt_allow_descriptions(ctx) -> List[str]:  # type: ignore
        return []

    def get_bash_prompt_ask_descriptions(ctx) -> List[str]:  # type: ignore
        return []

    def get_bash_prompt_deny_descriptions(ctx) -> List[str]:  # type: ignore
        return []

    def is_classifier_permissions_enabled() -> bool:  # type: ignore
        return False

try:
    from ...utils.permissions.permissions import (  # type: ignore
        create_permission_request_message,
        get_rule_by_contents_for_tool,
    )
except ImportError:
    def create_permission_request_message(tool_name: str, reason=None) -> str:  # type: ignore
        return f'Permission required for {tool_name}'

    def get_rule_by_contents_for_tool(ctx, tool, behavior) -> Dict[str, Any]:  # type: ignore
        return {}

try:
    from ...utils.permissions.shell_rule_matching import (  # type: ignore
        parse_permission_rule,
        match_wildcard_pattern as shared_match_wildcard_pattern,
        permission_rule_extract_prefix as shared_permission_rule_extract_prefix,
        suggestion_for_exact_command as shared_suggestion_for_exact_command,
        suggestion_for_prefix as shared_suggestion_for_prefix,
    )
except ImportError:
    def parse_permission_rule(rule: str):  # type: ignore
        class _R:
            type = 'exact'
            command = rule
            prefix = rule
            pattern = rule
        return _R()

    def shared_match_wildcard_pattern(pattern: str, command: str) -> bool:  # type: ignore
        return False

    def shared_permission_rule_extract_prefix(rule: str) -> Optional[str]:  # type: ignore
        return None

    def shared_suggestion_for_exact_command(tool_name: str, command: str) -> List[Any]:  # type: ignore
        return []

    def shared_suggestion_for_prefix(tool_name: str, prefix: str) -> List[Any]:  # type: ignore
        return []

try:
    from ...utils.permissions.PermissionUpdate import extract_rules  # type: ignore
except ImportError:
    def extract_rules(updates) -> List[Any]:  # type: ignore
        return []

try:
    from ...utils.permissions.permissionRuleParser import permission_rule_value_to_string  # type: ignore
except ImportError:
    def permission_rule_value_to_string(rule: Any) -> str:  # type: ignore
        return str(rule)

try:
    from ...utils.platform import get_platform  # type: ignore
except ImportError:
    def get_platform() -> str:  # type: ignore
        import sys
        return 'windows' if sys.platform == 'win32' else 'posix'

try:
    from ...utils.sandbox.sandbox_adapter import SandboxManager  # type: ignore
except ImportError:
    class SandboxManager:  # type: ignore[no-redef]
        @staticmethod
        def is_sandboxing_enabled() -> bool:
            return False

        @staticmethod
        def is_auto_allow_bash_if_sandboxed_enabled() -> bool:
            return False

try:
    from ...utils.windowsPaths import windows_path_to_posix_path  # type: ignore
except ImportError:
    def windows_path_to_posix_path(path: str) -> str:  # type: ignore
        return path

try:
    from .bashCommandHelpers import check_command_operator_permissions  # type: ignore
except ImportError:
    async def check_command_operator_permissions(*a, **kw):  # type: ignore
        return PermissionResult(behavior='passthrough', message='not implemented')

try:
    from .bash_security import bash_command_is_safe_async_deprecated  # type: ignore
    from .bash_security import strip_safe_heredoc_substitutions  # type: ignore
except ImportError:
    async def bash_command_is_safe_async_deprecated(cmd: str, on_divergence=None):  # type: ignore
        return PermissionResult(behavior='passthrough', message='not implemented')

    def strip_safe_heredoc_substitutions(cmd: str) -> Optional[str]:  # type: ignore
        return None

try:
    from .modeValidation import check_permission_mode  # type: ignore
except ImportError:
    def check_permission_mode(inp, ctx) -> PermissionResult:  # type: ignore
        return PermissionResult(behavior='passthrough', message='not implemented')

try:
    from .pathValidation import check_path_constraints  # type: ignore
except ImportError:
    def check_path_constraints(*a, **kw) -> PermissionResult:  # type: ignore
        return PermissionResult(behavior='passthrough', message='not implemented')

try:
    from .sedValidation import check_sed_constraints  # type: ignore
except ImportError:
    def check_sed_constraints(inp, ctx) -> PermissionResult:  # type: ignore
        return PermissionResult(behavior='passthrough', message='not implemented')

try:
    from .shouldUseSandbox import should_use_sandbox  # type: ignore
except ImportError:
    def should_use_sandbox(inp) -> bool:  # type: ignore
        return False

try:
    from .BashTool import BashTool  # type: ignore
except ImportError:
    class BashTool:  # type: ignore[no-redef]
        name = 'Bash'

        @staticmethod
        def is_read_only(inp) -> bool:
            return False

try:
    from ...services.analytics.index import log_event  # type: ignore
except ImportError:
    def log_event(name: str, data: dict) -> None:  # type: ignore
        pass

try:
    from ...services.analytics.growthbook import get_feature_value_cached_may_be_stale  # type: ignore
    def _feature(name: str) -> bool:
        return False  # Default: features off in Python port
except ImportError:
    def _feature(name: str) -> bool:  # type: ignore
        return False

    def get_feature_value_cached_may_be_stale(key: str, default):  # type: ignore
        return default

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_SUBCOMMANDS_FOR_SECURITY_CHECK = 50
MAX_SUGGESTED_RULES_FOR_COMPOUND = 5

ENV_VAR_ASSIGN_RE = re.compile(r'^[A-Za-z_]\w*=')

BARE_SHELL_PREFIXES: Set[str] = {
    'sh', 'bash', 'zsh', 'fish', 'csh', 'tcsh', 'ksh', 'dash',
    'cmd', 'powershell', 'pwsh',
    'env', 'xargs',
    'nice', 'stdbuf', 'nohup', 'timeout', 'time',
    'sudo', 'doas', 'pkexec',
}

SAFE_ENV_VARS: Set[str] = {
    'GOEXPERIMENT', 'GOOS', 'GOARCH', 'CGO_ENABLED', 'GO111MODULE',
    'RUST_BACKTRACE', 'RUST_LOG',
    'NODE_ENV',
    'PYTHONUNBUFFERED', 'PYTHONDONTWRITEBYTECODE',
    'PYTEST_DISABLE_PLUGIN_AUTOLOAD', 'PYTEST_DEBUG',
    'ANTHROPIC_API_KEY',
    'LANG', 'LANGUAGE', 'LC_ALL', 'LC_CTYPE', 'LC_TIME', 'CHARSET',
    'TERM', 'COLORTERM', 'NO_COLOR', 'FORCE_COLOR', 'TZ',
    'LS_COLORS', 'LSCOLORS', 'GREP_COLOR', 'GREP_COLORS', 'GCC_COLORS',
    'TIME_STYLE', 'BLOCK_SIZE', 'BLOCKSIZE',
}

ANT_ONLY_SAFE_ENV_VARS: Set[str] = {
    'KUBECONFIG', 'DOCKER_HOST',
    'AWS_PROFILE', 'CLOUDSDK_CORE_PROJECT', 'CLUSTER',
    'COO_CLUSTER', 'COO_CLUSTER_NAME', 'COO_NAMESPACE', 'COO_LAUNCH_YAML_DRY_RUN',
    'SKIP_NODE_VERSION_CHECK', 'EXPECTTEST_ACCEPT', 'CI', 'GIT_LFS_SKIP_SMUDGE',
    'CUDA_VISIBLE_DEVICES', 'JAX_PLATFORMS',
    'COLUMNS', 'TMUX',
    'POSTGRESQL_VERSION', 'FIRESTORE_EMULATOR_HOST', 'HARNESS_QUIET',
    'TEST_CROSSCHECK_LISTS_MATCH_UPDATE', 'DBT_PER_DEVELOPER_ENVIRONMENTS',
    'STATSIG_FORD_DB_CHECKS',
    'ANT_ENVIRONMENT', 'ANT_SERVICE', 'MONOREPO_ROOT_DIR',
    'PYENV_VERSION',
    'PGPASSWORD', 'GH_TOKEN', 'GROWTHBOOK_API_KEY',
}

BINARY_HIJACK_VARS = re.compile(r'^(LD_|DYLD_|PATH$)')

TIMEOUT_FLAG_VALUE_RE = re.compile(r'^[A-Za-z0-9_.+-]+$')


# ---------------------------------------------------------------------------
# Helper: strip comment lines
# ---------------------------------------------------------------------------

def _strip_comment_lines(command: str) -> str:
    lines = command.split('\n')
    non_comment = [
        line for line in lines
        if line.strip() and not line.strip().startswith('#')
    ]
    if not non_comment:
        return command
    return '\n'.join(non_comment)


# ---------------------------------------------------------------------------
# getSimpleCommandPrefix
# ---------------------------------------------------------------------------

def get_simple_command_prefix(command: str) -> Optional[str]:
    """
    Extract a stable command prefix (command + subcommand) from a raw command.
    Returns None if a non-safe env var prefix is encountered or second token
    doesn't look like a subcommand.
    """
    tokens = [t for t in command.strip().split() if t]
    if not tokens:
        return None

    is_ant = os.environ.get('USER_TYPE') == 'ant'
    i = 0
    while i < len(tokens) and ENV_VAR_ASSIGN_RE.match(tokens[i]):
        var_name = tokens[i].split('=')[0]
        is_ant_only_safe = is_ant and var_name in ANT_ONLY_SAFE_ENV_VARS
        if var_name not in SAFE_ENV_VARS and not is_ant_only_safe:
            return None
        i += 1

    remaining = tokens[i:]
    if len(remaining) < 2:
        return None
    subcmd = remaining[1]
    if not re.match(r'^[a-z][a-z0-9]*(-[a-z0-9]+)*$', subcmd):
        return None
    return ' '.join(remaining[:2])


# ---------------------------------------------------------------------------
# getFirstWordPrefix
# ---------------------------------------------------------------------------

def get_first_word_prefix(command: str) -> Optional[str]:
    """
    Extract the first word (command) from a raw command string, skipping
    safe env var assignments. Returns None for bare shell prefixes, paths, etc.
    """
    tokens = [t for t in command.strip().split() if t]
    is_ant = os.environ.get('USER_TYPE') == 'ant'
    i = 0
    while i < len(tokens) and ENV_VAR_ASSIGN_RE.match(tokens[i]):
        var_name = tokens[i].split('=')[0]
        is_ant_only_safe = is_ant and var_name in ANT_ONLY_SAFE_ENV_VARS
        if var_name not in SAFE_ENV_VARS and not is_ant_only_safe:
            return None
        i += 1

    if i >= len(tokens):
        return None
    cmd = tokens[i]
    if not re.match(r'^[a-z][a-z0-9]*(-[a-z0-9]+)*$', cmd):
        return None
    if cmd in BARE_SHELL_PREFIXES:
        return None
    return cmd


# ---------------------------------------------------------------------------
# Suggestion helpers
# ---------------------------------------------------------------------------

def _extract_prefix_before_heredoc(command: str) -> Optional[str]:
    if '<<' not in command:
        return None
    idx = command.index('<<')
    if idx <= 0:
        return None
    before = command[:idx].strip()
    if not before:
        return None
    prefix = get_simple_command_prefix(before)
    if prefix:
        return prefix
    tokens = [t for t in before.split() if t]
    is_ant = os.environ.get('USER_TYPE') == 'ant'
    i = 0
    while i < len(tokens) and ENV_VAR_ASSIGN_RE.match(tokens[i]):
        var_name = tokens[i].split('=')[0]
        is_ant_only_safe = is_ant and var_name in ANT_ONLY_SAFE_ENV_VARS
        if var_name not in SAFE_ENV_VARS and not is_ant_only_safe:
            return None
        i += 1
    if i >= len(tokens):
        return None
    return ' '.join(tokens[i:i + 2]) or None


def _suggestion_for_exact_command(command: str) -> List[Any]:
    heredoc_prefix = _extract_prefix_before_heredoc(command)
    if heredoc_prefix:
        return shared_suggestion_for_prefix(BashTool.name, heredoc_prefix)
    if '\n' in command:
        first_line = command.split('\n')[0].strip()
        if first_line:
            return shared_suggestion_for_prefix(BashTool.name, first_line)
    prefix = get_simple_command_prefix(command)
    if prefix:
        return shared_suggestion_for_prefix(BashTool.name, prefix)
    return shared_suggestion_for_exact_command(BashTool.name, command)


def _suggestion_for_prefix(prefix: str) -> List[Any]:
    return shared_suggestion_for_prefix(BashTool.name, prefix)


# ---------------------------------------------------------------------------
# Public re-exports that mirror TS exports
# ---------------------------------------------------------------------------

permission_rule_extract_prefix = shared_permission_rule_extract_prefix


def match_wildcard_pattern(pattern: str, command: str) -> bool:
    return shared_match_wildcard_pattern(pattern, command)


def bash_permission_rule(permission_rule: str):
    return parse_permission_rule(permission_rule)


# ---------------------------------------------------------------------------
# stripSafeWrappers
# ---------------------------------------------------------------------------

# Regexp patterns for SAFE_WRAPPER_PATTERNS
_TIMEOUT_PATTERN = re.compile(
    r'^timeout[ \t]+(?:(?:--(?:foreground|preserve-status|verbose)'
    r'|--(?:kill-after|signal)=[A-Za-z0-9_.+-]+'
    r'|--(?:kill-after|signal)[ \t]+[A-Za-z0-9_.+-]+'
    r'|-v|-[ks][ \t]+[A-Za-z0-9_.+-]+'
    r'|-[ks][A-Za-z0-9_.+-]+)[ \t]+)*(?:--[ \t]+)?\d+(?:\.\d+)?[smhd]?[ \t]+'
)
_TIME_PATTERN = re.compile(r'^time[ \t]+(?:--[ \t]+)?')
_NICE_PATTERN = re.compile(r'^nice(?:[ \t]+-n[ \t]+-?\d+|[ \t]+-\d+)?[ \t]+(?:--[ \t]+)?')
_STDBUF_PATTERN = re.compile(r'^stdbuf(?:[ \t]+-[ioe][LN0-9]+)+[ \t]+(?:--[ \t]+)?')
_NOHUP_PATTERN = re.compile(r'^nohup[ \t]+(?:--[ \t]+)?')

SAFE_WRAPPER_PATTERNS = [
    _TIMEOUT_PATTERN,
    _TIME_PATTERN,
    _NICE_PATTERN,
    _STDBUF_PATTERN,
    _NOHUP_PATTERN,
]

_ENV_VAR_PATTERN = re.compile(
    r'^([A-Za-z_][A-Za-z0-9_]*)=([A-Za-z0-9_./:-]+)[ \t]+'
)


def strip_safe_wrappers(command: str) -> str:
    """Strip safe env var prefixes and wrapper commands (timeout, time, nice, nohup, stdbuf)."""
    is_ant = os.environ.get('USER_TYPE') == 'ant'
    stripped = command
    previous = ''

    # Phase 1: strip leading env vars and comments
    while stripped != previous:
        previous = stripped
        stripped = _strip_comment_lines(stripped)
        m = _ENV_VAR_PATTERN.match(stripped)
        if m:
            var_name = m.group(1)
            is_ant_only_safe = is_ant and var_name in ANT_ONLY_SAFE_ENV_VARS
            if var_name in SAFE_ENV_VARS or is_ant_only_safe:
                stripped = _ENV_VAR_PATTERN.sub('', stripped, count=1)

    # Phase 2: strip safe wrapper commands and comments
    previous = ''
    while stripped != previous:
        previous = stripped
        stripped = _strip_comment_lines(stripped)
        for pattern in SAFE_WRAPPER_PATTERNS:
            stripped = pattern.sub('', stripped, count=1)

    return stripped.strip()


# ---------------------------------------------------------------------------
# skipTimeoutFlags (argv level)
# ---------------------------------------------------------------------------

def _skip_timeout_flags(argv: List[str]) -> int:
    i = 1
    while i < len(argv):
        arg = argv[i]
        next_arg = argv[i + 1] if i + 1 < len(argv) else None
        if arg in ('--foreground', '--preserve-status', '--verbose'):
            i += 1
        elif re.match(r'^--(?:kill-after|signal)=[A-Za-z0-9_.+-]+$', arg):
            i += 1
        elif arg in ('--kill-after', '--signal') and next_arg and TIMEOUT_FLAG_VALUE_RE.match(next_arg):
            i += 2
        elif arg == '--':
            i += 1
            break
        elif arg.startswith('--'):
            return -1
        elif arg == '-v':
            i += 1
        elif arg in ('-k', '-s') and next_arg and TIMEOUT_FLAG_VALUE_RE.match(next_arg):
            i += 2
        elif re.match(r'^-[ks][A-Za-z0-9_.+-]+$', arg):
            i += 1
        elif arg.startswith('-'):
            return -1
        else:
            break
    return i


def strip_wrappers_from_argv(argv: List[str]) -> List[str]:
    """Argv-level counterpart to strip_safe_wrappers."""
    a = argv
    while True:
        if a and a[0] in ('time', 'nohup'):
            a = a[2:] if len(a) > 1 and a[1] == '--' else a[1:]
        elif a and a[0] == 'timeout':
            i = _skip_timeout_flags(a)
            if i < 0 or i >= len(a) or not re.match(r'^\d+(?:\.\d+)?[smhd]?$', a[i]):
                return a
            a = a[i + 1:]
        elif (
            len(a) >= 3 and a[0] == 'nice' and a[1] == '-n' and
            re.match(r'^-?\d+$', a[2])
        ):
            a = a[4:] if len(a) > 3 and a[3] == '--' else a[3:]
        else:
            return a


# ---------------------------------------------------------------------------
# stripAllLeadingEnvVars
# ---------------------------------------------------------------------------

_STRIP_ALL_ENV_VAR_PATTERN = re.compile(
    r'^([A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\])?)\+?='
    r"(?:'[^'\n\r]*'|\"(?:\\.|[^\"$`\\\n\r])*\"|\\.|[^ \t\n\r$`;|&()<>\\\\'\"]) *[ \t]+"
)


def strip_all_leading_env_vars(command: str, blocklist: Optional[re.Pattern] = None) -> str:
    """Strip ALL leading env var prefixes regardless of safe-list membership."""
    stripped = command
    previous = ''
    while stripped != previous:
        previous = stripped
        stripped = _strip_comment_lines(stripped)
        m = _STRIP_ALL_ENV_VAR_PATTERN.match(stripped)
        if not m:
            continue
        if blocklist and blocklist.match(m.group(1)):
            break
        stripped = stripped[len(m.group(0)):]
    return stripped.strip()


# ---------------------------------------------------------------------------
# filterRulesByContentsMatchingInput
# ---------------------------------------------------------------------------

def _filter_rules_by_contents_matching_input(
    input_cmd: Dict[str, Any],
    rules: Dict[str, Any],
    match_mode: str,  # 'exact' | 'prefix'
    *,
    strip_all_env_vars: bool = False,
    skip_compound_check: bool = False,
) -> List[Any]:
    command = input_cmd.get('command', '').strip()

    redir_result = extract_output_redirections(command)
    cmd_without_redirections = redir_result.command_without_redirections

    commands_for_matching = (
        [command, cmd_without_redirections] if match_mode == 'exact'
        else [cmd_without_redirections]
    )

    commands_to_try: List[str] = []
    for cmd in commands_for_matching:
        stripped = strip_safe_wrappers(cmd)
        if stripped != cmd:
            commands_to_try.extend([cmd, stripped])
        else:
            commands_to_try.append(cmd)

    if strip_all_env_vars:
        seen: Set[str] = set(commands_to_try)
        start_idx = 0
        while start_idx < len(commands_to_try):
            end_idx = len(commands_to_try)
            for i in range(start_idx, end_idx):
                cmd = commands_to_try[i]
                env_stripped = strip_all_leading_env_vars(cmd)
                if env_stripped not in seen:
                    commands_to_try.append(env_stripped)
                    seen.add(env_stripped)
                wrapper_stripped = strip_safe_wrappers(cmd)
                if wrapper_stripped not in seen:
                    commands_to_try.append(wrapper_stripped)
                    seen.add(wrapper_stripped)
            start_idx = end_idx

    is_compound: Dict[str, bool] = {}
    if match_mode == 'prefix' and not skip_compound_check:
        for cmd in commands_to_try:
            if cmd not in is_compound:
                is_compound[cmd] = len(split_command(cmd)) > 1

    result = []
    for rule_content, rule in rules.items():
        bash_rule = bash_permission_rule(rule_content)

        def _matches(cmd_to_match: str) -> bool:
            rtype = bash_rule.type
            if rtype == 'exact':
                return bash_rule.command == cmd_to_match
            if rtype == 'prefix':
                if match_mode == 'exact':
                    return bash_rule.prefix == cmd_to_match
                if match_mode == 'prefix':
                    if is_compound.get(cmd_to_match, False):
                        return False
                    if cmd_to_match == bash_rule.prefix:
                        return True
                    if cmd_to_match.startswith(bash_rule.prefix + ' '):
                        return True
                    xargs_prefix = 'xargs ' + bash_rule.prefix
                    if cmd_to_match == xargs_prefix:
                        return True
                    return cmd_to_match.startswith(xargs_prefix + ' ')
            if rtype == 'wildcard':
                if match_mode == 'exact':
                    return False
                if is_compound.get(cmd_to_match, False):
                    return False
                return match_wildcard_pattern(bash_rule.pattern, cmd_to_match)
            return False

        if any(_matches(c) for c in commands_to_try):
            result.append(rule)

    return result


# ---------------------------------------------------------------------------
# matchingRulesForInput
# ---------------------------------------------------------------------------

def _matching_rules_for_input(
    input_cmd: Dict[str, Any],
    tool_permission_context: Any,
    match_mode: str,
    *,
    skip_compound_check: bool = False,
) -> Dict[str, List[Any]]:
    deny_rules = get_rule_by_contents_for_tool(tool_permission_context, BashTool, 'deny')
    matching_deny = _filter_rules_by_contents_matching_input(
        input_cmd, deny_rules, match_mode,
        strip_all_env_vars=True, skip_compound_check=True,
    )

    ask_rules = get_rule_by_contents_for_tool(tool_permission_context, BashTool, 'ask')
    matching_ask = _filter_rules_by_contents_matching_input(
        input_cmd, ask_rules, match_mode,
        strip_all_env_vars=True, skip_compound_check=True,
    )

    allow_rules = get_rule_by_contents_for_tool(tool_permission_context, BashTool, 'allow')
    matching_allow = _filter_rules_by_contents_matching_input(
        input_cmd, allow_rules, match_mode,
        skip_compound_check=skip_compound_check,
    )

    return {
        'matchingDenyRules': matching_deny,
        'matchingAskRules': matching_ask,
        'matchingAllowRules': matching_allow,
    }


# ---------------------------------------------------------------------------
# bashToolCheckExactMatchPermission
# ---------------------------------------------------------------------------

def bash_tool_check_exact_match_permission(
    input_cmd: Dict[str, Any],
    tool_permission_context: Any,
) -> PermissionResult:
    command = input_cmd.get('command', '').strip()
    rules = _matching_rules_for_input(input_cmd, tool_permission_context, 'exact')

    if rules['matchingDenyRules']:
        return PermissionResult(
            behavior='deny',
            message=f'Permission to use {BashTool.name} with command {command} has been denied.',
            decision_reason={'type': 'rule', 'rule': rules['matchingDenyRules'][0]},
        )

    if rules['matchingAskRules']:
        return PermissionResult(
            behavior='ask',
            message=create_permission_request_message(BashTool.name),
            decision_reason={'type': 'rule', 'rule': rules['matchingAskRules'][0]},
        )

    if rules['matchingAllowRules']:
        return PermissionResult(
            behavior='allow',
            updated_input=input_cmd,
            decision_reason={'type': 'rule', 'rule': rules['matchingAllowRules'][0]},
        )

    decision_reason = {'type': 'other', 'reason': 'This command requires approval'}
    return PermissionResult(
        behavior='passthrough',
        message=create_permission_request_message(BashTool.name, decision_reason),
        decision_reason=decision_reason,
        suggestions=_suggestion_for_exact_command(command),
    )


# ---------------------------------------------------------------------------
# bashToolCheckPermission
# ---------------------------------------------------------------------------

def bash_tool_check_permission(
    input_cmd: Dict[str, Any],
    tool_permission_context: Any,
    compound_command_has_cd: bool = False,
    ast_command: Optional[Any] = None,
) -> PermissionResult:
    command = input_cmd.get('command', '').strip()

    exact_result = bash_tool_check_exact_match_permission(input_cmd, tool_permission_context)
    if exact_result.behavior in ('deny', 'ask'):
        return exact_result

    rules = _matching_rules_for_input(
        input_cmd, tool_permission_context, 'prefix',
        skip_compound_check=(ast_command is not None),
    )

    if rules['matchingDenyRules']:
        return PermissionResult(
            behavior='deny',
            message=f'Permission to use {BashTool.name} with command {command} has been denied.',
            decision_reason={'type': 'rule', 'rule': rules['matchingDenyRules'][0]},
        )

    if rules['matchingAskRules']:
        return PermissionResult(
            behavior='ask',
            message=create_permission_request_message(BashTool.name),
            decision_reason={'type': 'rule', 'rule': rules['matchingAskRules'][0]},
        )

    ast_redirects = getattr(ast_command, 'redirects', None)
    ast_cmds = [ast_command] if ast_command else None
    path_result = check_path_constraints(
        input_cmd, get_cwd(), tool_permission_context,
        compound_command_has_cd, ast_redirects, ast_cmds,
    )
    if path_result.behavior != 'passthrough':
        return path_result

    if exact_result.behavior == 'allow':
        return exact_result

    if rules['matchingAllowRules']:
        return PermissionResult(
            behavior='allow',
            updated_input=input_cmd,
            decision_reason={'type': 'rule', 'rule': rules['matchingAllowRules'][0]},
        )

    sed_result = check_sed_constraints(input_cmd, tool_permission_context)
    if sed_result.behavior != 'passthrough':
        return sed_result

    mode_result = check_permission_mode(input_cmd, tool_permission_context)
    if mode_result.behavior != 'passthrough':
        return mode_result

    if BashTool.is_read_only(input_cmd):
        return PermissionResult(
            behavior='allow',
            updated_input=input_cmd,
            decision_reason={'type': 'other', 'reason': 'Read-only command is allowed'},
        )

    decision_reason = {'type': 'other', 'reason': 'This command requires approval'}
    return PermissionResult(
        behavior='passthrough',
        message=create_permission_request_message(BashTool.name, decision_reason),
        decision_reason=decision_reason,
        suggestions=_suggestion_for_exact_command(command),
    )


# ---------------------------------------------------------------------------
# checkCommandAndSuggestRules
# ---------------------------------------------------------------------------

async def check_command_and_suggest_rules(
    input_cmd: Dict[str, Any],
    tool_permission_context: Any,
    command_prefix_result: Optional[Any],
    compound_command_has_cd: bool = False,
    ast_parse_succeeded: bool = False,
) -> PermissionResult:
    exact_result = bash_tool_check_exact_match_permission(input_cmd, tool_permission_context)
    if exact_result.behavior != 'passthrough':
        return exact_result

    permission_result = bash_tool_check_permission(
        input_cmd, tool_permission_context, compound_command_has_cd
    )
    if permission_result.behavior in ('deny', 'ask'):
        return permission_result

    if (
        not ast_parse_succeeded and
        not is_env_truthy(os.environ.get('CLAUDE_CODE_DISABLE_COMMAND_INJECTION_CHECK'))
    ):
        safety_result = await bash_command_is_safe_async_deprecated(input_cmd.get('command', ''))
        if safety_result.behavior != 'passthrough':
            decision_reason = {
                'type': 'other',
                'reason': (
                    safety_result.message
                    if safety_result.behavior == 'ask' and safety_result.message
                    else 'This command contains patterns that could pose security risks and requires approval'
                ),
            }
            return PermissionResult(
                behavior='ask',
                message=create_permission_request_message(BashTool.name, decision_reason),
                decision_reason=decision_reason,
                suggestions=[],
            )

    if permission_result.behavior == 'allow':
        return permission_result

    cmd_prefix = getattr(command_prefix_result, 'commandPrefix', None) if command_prefix_result else None
    suggested_updates = (
        _suggestion_for_prefix(cmd_prefix)
        if cmd_prefix
        else _suggestion_for_exact_command(input_cmd.get('command', ''))
    )

    return PermissionResult(
        behavior=permission_result.behavior,
        message=permission_result.message,
        decision_reason=permission_result.decision_reason,
        suggestions=suggested_updates,
    )


# ---------------------------------------------------------------------------
# checkSandboxAutoAllow
# ---------------------------------------------------------------------------

def _check_sandbox_auto_allow(
    input_cmd: Dict[str, Any],
    tool_permission_context: Any,
) -> PermissionResult:
    command = input_cmd.get('command', '').strip()
    rules = _matching_rules_for_input(input_cmd, tool_permission_context, 'prefix')

    if rules['matchingDenyRules']:
        return PermissionResult(
            behavior='deny',
            message=f'Permission to use {BashTool.name} with command {command} has been denied.',
            decision_reason={'type': 'rule', 'rule': rules['matchingDenyRules'][0]},
        )

    subcommands = split_command(command)
    if len(subcommands) > 1:
        first_ask_rule = None
        for sub in subcommands:
            sub_result = _matching_rules_for_input({'command': sub}, tool_permission_context, 'prefix')
            if sub_result['matchingDenyRules']:
                return PermissionResult(
                    behavior='deny',
                    message=f'Permission to use {BashTool.name} with command {command} has been denied.',
                    decision_reason={'type': 'rule', 'rule': sub_result['matchingDenyRules'][0]},
                )
            if first_ask_rule is None and sub_result['matchingAskRules']:
                first_ask_rule = sub_result['matchingAskRules'][0]
        if first_ask_rule:
            return PermissionResult(
                behavior='ask',
                message=create_permission_request_message(BashTool.name),
                decision_reason={'type': 'rule', 'rule': first_ask_rule},
            )

    if rules['matchingAskRules']:
        return PermissionResult(
            behavior='ask',
            message=create_permission_request_message(BashTool.name),
            decision_reason={'type': 'rule', 'rule': rules['matchingAskRules'][0]},
        )

    return PermissionResult(
        behavior='allow',
        updated_input=input_cmd,
        decision_reason={
            'type': 'other',
            'reason': 'Auto-allowed with sandbox (autoAllowBashIfSandboxed enabled)',
        },
    )


# ---------------------------------------------------------------------------
# filterCdCwdSubcommands
# ---------------------------------------------------------------------------

def _filter_cd_cwd_subcommands(
    raw_subcommands: List[str],
    ast_commands: Optional[List[Any]],
    cwd: str,
    cwd_mingw: str,
) -> Tuple[List[str], List[Optional[Any]]]:
    subcommands: List[str] = []
    ast_by_idx: List[Optional[Any]] = []
    for i, cmd in enumerate(raw_subcommands):
        if cmd == f'cd {cwd}' or cmd == f'cd {cwd_mingw}':
            continue
        subcommands.append(cmd)
        ast_by_idx.append(ast_commands[i] if ast_commands and i < len(ast_commands) else None)
    return subcommands, ast_by_idx


# ---------------------------------------------------------------------------
# checkEarlyExitDeny / checkSemanticsDeny
# ---------------------------------------------------------------------------

def _check_early_exit_deny(
    input_cmd: Dict[str, Any],
    tool_permission_context: Any,
) -> Optional[PermissionResult]:
    exact = bash_tool_check_exact_match_permission(input_cmd, tool_permission_context)
    if exact.behavior != 'passthrough':
        return exact
    deny_match = _matching_rules_for_input(input_cmd, tool_permission_context, 'prefix')['matchingDenyRules']
    if deny_match:
        return PermissionResult(
            behavior='deny',
            message=f'Permission to use {BashTool.name} with command {input_cmd.get("command", "")} has been denied.',
            decision_reason={'type': 'rule', 'rule': deny_match[0]},
        )
    return None


def _check_semantics_deny(
    input_cmd: Dict[str, Any],
    tool_permission_context: Any,
    commands: List[Any],
) -> Optional[PermissionResult]:
    full = _check_early_exit_deny(input_cmd, tool_permission_context)
    if full is not None:
        return full
    for cmd in commands:
        cmd_text = getattr(cmd, 'text', str(cmd))
        sub_deny = _matching_rules_for_input(
            {**input_cmd, 'command': cmd_text}, tool_permission_context, 'prefix'
        )['matchingDenyRules']
        if sub_deny:
            return PermissionResult(
                behavior='deny',
                message=f'Permission to use {BashTool.name} with command {input_cmd.get("command", "")} has been denied.',
                decision_reason={'type': 'rule', 'rule': sub_deny[0]},
            )
    return None


# ---------------------------------------------------------------------------
# Classifier helpers
# ---------------------------------------------------------------------------

def _build_pending_classifier_check(
    command: str,
    tool_permission_context: Any,
) -> Optional[Dict[str, Any]]:
    if not is_classifier_permissions_enabled():
        return None
    if _feature('TRANSCRIPT_CLASSIFIER') and getattr(tool_permission_context, 'mode', None) == 'auto':
        return None
    if getattr(tool_permission_context, 'mode', None) == 'bypassPermissions':
        return None
    allow_descriptions = get_bash_prompt_allow_descriptions(tool_permission_context)
    if not allow_descriptions:
        return None
    return {'command': command, 'cwd': get_cwd(), 'descriptions': allow_descriptions}


_speculative_checks: Dict[str, asyncio.Future] = {}


def peek_speculative_classifier_check(command: str):
    return _speculative_checks.get(command)


def start_speculative_classifier_check(
    command: str,
    tool_permission_context: Any,
    signal: Any,
    is_non_interactive_session: bool,
) -> bool:
    if not is_classifier_permissions_enabled():
        return False
    if _feature('TRANSCRIPT_CLASSIFIER') and getattr(tool_permission_context, 'mode', None) == 'auto':
        return False
    if getattr(tool_permission_context, 'mode', None) == 'bypassPermissions':
        return False
    allow_descriptions = get_bash_prompt_allow_descriptions(tool_permission_context)
    if not allow_descriptions:
        return False

    cwd = get_cwd()
    future = asyncio.ensure_future(
        classify_bash_command(command, cwd, allow_descriptions, 'allow', signal, is_non_interactive_session)
    )
    _speculative_checks[command] = future
    return True


def consume_speculative_classifier_check(command: str):
    return _speculative_checks.pop(command, None)


def clear_speculative_checks() -> None:
    _speculative_checks.clear()


async def await_classifier_auto_approval(
    pending_check: Dict[str, Any],
    signal: Any,
    is_non_interactive_session: bool,
) -> Optional[Dict[str, Any]]:
    command = pending_check['command']
    cwd = pending_check['cwd']
    descriptions = pending_check['descriptions']
    speculative = consume_speculative_classifier_check(command)
    classifier_result = (
        await speculative
        if speculative
        else await classify_bash_command(command, cwd, descriptions, 'allow', signal, is_non_interactive_session)
    )

    if (
        _feature('BASH_CLASSIFIER') and
        classifier_result and
        classifier_result.matches and
        classifier_result.confidence == 'high'
    ):
        return {
            'type': 'classifier',
            'classifier': 'bash_allow',
            'reason': f'Allowed by prompt rule: "{classifier_result.matchedDescription}"',
        }
    return None


async def execute_async_classifier_check(
    pending_check: Dict[str, Any],
    signal: Any,
    is_non_interactive_session: bool,
    callbacks: Dict[str, Any],
) -> None:
    command = pending_check['command']
    cwd = pending_check['cwd']
    descriptions = pending_check['descriptions']
    speculative = consume_speculative_classifier_check(command)

    try:
        classifier_result = (
            await speculative
            if speculative
            else await classify_bash_command(command, cwd, descriptions, 'allow', signal, is_non_interactive_session)
        )
    except Exception as e:
        callbacks.get('onComplete', lambda: None)()
        # Re-raise unless it's an abort error
        if not isinstance(e, AbortError):
            raise
        return

    should_continue = callbacks.get('shouldContinue', lambda: True)
    if not should_continue():
        return

    if (
        _feature('BASH_CLASSIFIER') and
        classifier_result and
        classifier_result.matches and
        classifier_result.confidence == 'high'
    ):
        on_allow = callbacks.get('onAllow')
        if on_allow:
            on_allow({
                'type': 'classifier',
                'classifier': 'bash_allow',
                'reason': f'Allowed by prompt rule: "{classifier_result.matchedDescription}"',
            })
    else:
        callbacks.get('onComplete', lambda: None)()


# ---------------------------------------------------------------------------
# isNormalizedGitCommand / isNormalizedCdCommand / commandHasAnyCd
# ---------------------------------------------------------------------------

def is_normalized_git_command(command: str) -> bool:
    """Check if command is a git command after stripping safe wrappers/env vars."""
    if command.startswith('git ') or command == 'git':
        return True
    stripped = strip_safe_wrappers(command)
    parsed = try_parse_shell_command(stripped)
    if parsed.success and parsed.tokens:
        if parsed.tokens[0] == 'git':
            return True
        if parsed.tokens[0] == 'xargs' and 'git' in parsed.tokens:
            return True
        return False
    return bool(re.match(r'^git(?:\s|$)', stripped))


def is_normalized_cd_command(command: str) -> bool:
    """Check if command is cd/pushd/popd after stripping safe wrappers."""
    stripped = strip_safe_wrappers(command)
    parsed = try_parse_shell_command(stripped)
    if parsed.success and parsed.tokens:
        return parsed.tokens[0] in ('cd', 'pushd', 'popd')
    return bool(re.match(r'^(?:cd|pushd|popd)(?:\s|$)', stripped))


def command_has_any_cd(command: str) -> bool:
    """Check if any subcommand in a compound command is cd/pushd/popd."""
    return any(
        is_normalized_cd_command(sub.strip())
        for sub in split_command(command)
    )


# ---------------------------------------------------------------------------
# bashToolHasPermission (main entry point)
# ---------------------------------------------------------------------------

async def bash_tool_has_permission(
    input_cmd: Dict[str, Any],
    context: Any,
    get_command_subcommand_prefix_fn: Optional[Callable] = None,
) -> PermissionResult:
    """
    Main permission check for BashTool.
    Checks rules, security, path constraints, and optionally runs classifier.
    """
    if get_command_subcommand_prefix_fn is None:
        get_command_subcommand_prefix_fn = get_command_subcommand_prefix

    app_state = context.get_app_state()

    injection_check_disabled = is_env_truthy(
        os.environ.get('CLAUDE_CODE_DISABLE_COMMAND_INJECTION_CHECK')
    )
    shadow_enabled = (
        get_feature_value_cached_may_be_stale('tengu_birch_trellis', True)
        if _feature('TREE_SITTER_BASH_SHADOW')
        else False
    )

    ast_root = None
    if not injection_check_disabled:
        if not (_feature('TREE_SITTER_BASH_SHADOW') and not shadow_enabled):
            try:
                ast_root = await parse_command_raw(input_cmd.get('command', ''))
            except Exception:
                ast_root = None

    ast_result = (
        parse_for_security_from_ast(input_cmd.get('command', ''), ast_root)
        if ast_root
        else {'kind': 'parse-unavailable'}
    )
    ast_subcommands: Optional[List[str]] = None
    ast_redirects = None
    ast_commands: Optional[List[Any]] = None
    shadow_legacy_subs: Optional[List[str]] = None

    # Shadow mode: record verdict then force parse-unavailable
    if _feature('TREE_SITTER_BASH_SHADOW'):
        ast_result = {'kind': 'parse-unavailable'}
        ast_root = None

    if isinstance(ast_result, dict):
        ast_kind = ast_result.get('kind', 'parse-unavailable')
    else:
        ast_kind = getattr(ast_result, 'kind', 'parse-unavailable')

    # Handle too-complex
    if ast_kind == 'too-complex':
        early_exit = _check_early_exit_deny(input_cmd, app_state.tool_permission_context)
        if early_exit is not None:
            return early_exit
        reason = ast_result.get('reason', 'Command is too complex to analyze') if isinstance(ast_result, dict) else getattr(ast_result, 'reason', 'Command is too complex to analyze')
        decision_reason = {'type': 'other', 'reason': reason}
        result = PermissionResult(
            behavior='ask',
            decision_reason=decision_reason,
            message=create_permission_request_message(BashTool.name, decision_reason),
            suggestions=[],
        )
        if _feature('BASH_CLASSIFIER'):
            result.pending_classifier_check = _build_pending_classifier_check(
                input_cmd.get('command', ''), app_state.tool_permission_context
            )
        return result

    # Handle simple
    if ast_kind == 'simple':
        commands_list = ast_result.get('commands', []) if isinstance(ast_result, dict) else getattr(ast_result, 'commands', [])
        sem = check_semantics(commands_list)
        if not sem.ok:
            early_exit = _check_semantics_deny(input_cmd, app_state.tool_permission_context, commands_list)
            if early_exit is not None:
                return early_exit
            decision_reason = {'type': 'other', 'reason': sem.reason}
            return PermissionResult(
                behavior='ask',
                decision_reason=decision_reason,
                message=create_permission_request_message(BashTool.name, decision_reason),
                suggestions=[],
            )
        ast_subcommands = [getattr(c, 'text', c) for c in commands_list]
        ast_redirects = [r for c in commands_list for r in getattr(c, 'redirects', [])]
        ast_commands = commands_list

    # Legacy shell-quote pre-check (parse-unavailable path)
    if ast_kind == 'parse-unavailable':
        log_for_debugging(
            'bash_tool_has_permission: tree-sitter unavailable, using legacy shell-quote path'
        )
        parse_result = try_parse_shell_command(input_cmd.get('command', ''))
        if not parse_result.success:
            decision_reason = {
                'type': 'other',
                'reason': f'Command contains malformed syntax that cannot be parsed: {parse_result.error}',
            }
            return PermissionResult(
                behavior='ask',
                decision_reason=decision_reason,
                message=create_permission_request_message(BashTool.name, decision_reason),
            )

    # Sandbox auto-allow
    if (
        SandboxManager.is_sandboxing_enabled() and
        SandboxManager.is_auto_allow_bash_if_sandboxed_enabled() and
        should_use_sandbox(input_cmd)
    ):
        sandbox_result = _check_sandbox_auto_allow(input_cmd, app_state.tool_permission_context)
        if sandbox_result.behavior != 'passthrough':
            return sandbox_result

    # Exact match
    exact_result = bash_tool_check_exact_match_permission(input_cmd, app_state.tool_permission_context)
    if exact_result.behavior == 'deny':
        return exact_result

    # Classifier: deny + ask in parallel
    if (
        is_classifier_permissions_enabled() and
        not (_feature('TRANSCRIPT_CLASSIFIER') and getattr(app_state.tool_permission_context, 'mode', None) == 'auto')
    ):
        deny_descriptions = get_bash_prompt_deny_descriptions(app_state.tool_permission_context)
        ask_descriptions = get_bash_prompt_ask_descriptions(app_state.tool_permission_context)
        has_deny = bool(deny_descriptions)
        has_ask = bool(ask_descriptions)

        if has_deny or has_ask:
            cwd = get_cwd()
            abort_signal = context.abort_controller.signal
            is_non_interactive = context.options.is_non_interactive_session

            deny_coro = (
                classify_bash_command(input_cmd['command'], cwd, deny_descriptions, 'deny', abort_signal, is_non_interactive)
                if has_deny else None
            )
            ask_coro = (
                classify_bash_command(input_cmd['command'], cwd, ask_descriptions, 'ask', abort_signal, is_non_interactive)
                if has_ask else None
            )

            results = await asyncio.gather(
                deny_coro if deny_coro else _noop_coro(),
                ask_coro if ask_coro else _noop_coro(),
            )
            deny_result, ask_result = results

            if deny_result and deny_result.matches and deny_result.confidence == 'high':
                msg = f'Denied by Bash prompt rule: "{deny_result.matchedDescription}"'
                return PermissionResult(
                    behavior='deny',
                    message=msg,
                    decision_reason={'type': 'other', 'reason': msg},
                )

            if ask_result and ask_result.matches and ask_result.confidence == 'high':
                if get_command_subcommand_prefix_fn == get_command_subcommand_prefix:
                    suggestions = _suggestion_for_exact_command(input_cmd.get('command', ''))
                else:
                    cmd_prefix_result = await get_command_subcommand_prefix_fn(
                        input_cmd.get('command', ''), abort_signal, is_non_interactive
                    )
                    cmd_prefix = getattr(cmd_prefix_result, 'commandPrefix', None) if cmd_prefix_result else None
                    suggestions = (
                        _suggestion_for_prefix(cmd_prefix)
                        if cmd_prefix
                        else _suggestion_for_exact_command(input_cmd.get('command', ''))
                    )
                result = PermissionResult(
                    behavior='ask',
                    message=create_permission_request_message(BashTool.name),
                    decision_reason={
                        'type': 'other',
                        'reason': f'Required by Bash prompt rule: "{ask_result.matchedDescription}"',
                    },
                    suggestions=suggestions,
                )
                if _feature('BASH_CLASSIFIER'):
                    result.pending_classifier_check = _build_pending_classifier_check(
                        input_cmd.get('command', ''), app_state.tool_permission_context
                    )
                return result

    # Check command operator permissions (pipes, etc.)
    async def _recursive_permission(sub_input: Dict[str, Any]) -> PermissionResult:
        return await bash_tool_has_permission(sub_input, context, get_command_subcommand_prefix_fn)

    operator_result = await check_command_operator_permissions(
        input_cmd, _recursive_permission,
        {'isNormalizedCdCommand': is_normalized_cd_command, 'isNormalizedGitCommand': is_normalized_git_command},
        ast_root,
    )

    if operator_result.behavior != 'passthrough':
        if operator_result.behavior == 'allow':
            safety_result = (
                await bash_command_is_safe_async_deprecated(input_cmd.get('command', ''))
                if ast_subcommands is None
                else None
            )
            if (
                safety_result is not None and
                safety_result.behavior not in ('passthrough', 'allow')
            ):
                app_state = context.get_app_state()
                result = PermissionResult(
                    behavior='ask',
                    message=create_permission_request_message(BashTool.name, {
                        'type': 'other',
                        'reason': safety_result.message or 'Command contains patterns that require approval',
                    }),
                    decision_reason={
                        'type': 'other',
                        'reason': safety_result.message or 'Command contains patterns that require approval',
                    },
                )
                if _feature('BASH_CLASSIFIER'):
                    result.pending_classifier_check = _build_pending_classifier_check(
                        input_cmd.get('command', ''), app_state.tool_permission_context
                    )
                return result

            app_state = context.get_app_state()
            path_result = check_path_constraints(
                input_cmd, get_cwd(), app_state.tool_permission_context,
                command_has_any_cd(input_cmd.get('command', '')),
                ast_redirects, ast_commands,
            )
            if path_result.behavior != 'passthrough':
                return path_result

        if operator_result.behavior == 'ask':
            app_state = context.get_app_state()
            result = PermissionResult(
                behavior='ask',
                message=operator_result.message,
                decision_reason=operator_result.decision_reason,
                suggestions=operator_result.suggestions,
            )
            if _feature('BASH_CLASSIFIER'):
                result.pending_classifier_check = _build_pending_classifier_check(
                    input_cmd.get('command', ''), app_state.tool_permission_context
                )
            return result

        return operator_result

    # Legacy misparsing gate (only when ast_subcommands is None)
    if (
        ast_subcommands is None and
        not is_env_truthy(os.environ.get('CLAUDE_CODE_DISABLE_COMMAND_INJECTION_CHECK'))
    ):
        original_safety = await bash_command_is_safe_async_deprecated(input_cmd.get('command', ''))
        if (
            original_safety.behavior == 'ask' and
            getattr(original_safety, 'is_bash_security_check_for_misparsing', False)
        ):
            remainder = strip_safe_heredoc_substitutions(input_cmd.get('command', ''))
            remainder_result = (
                await bash_command_is_safe_async_deprecated(remainder)
                if remainder is not None
                else None
            )
            if remainder is None or (
                remainder_result and
                remainder_result.behavior == 'ask' and
                getattr(remainder_result, 'is_bash_security_check_for_misparsing', False)
            ):
                app_state = context.get_app_state()
                exact_again = bash_tool_check_exact_match_permission(
                    input_cmd, app_state.tool_permission_context
                )
                if exact_again.behavior == 'allow':
                    return exact_again
                decision_reason = {'type': 'other', 'reason': original_safety.message}
                result = PermissionResult(
                    behavior='ask',
                    message=create_permission_request_message(BashTool.name, decision_reason),
                    decision_reason=decision_reason,
                    suggestions=[],
                )
                if _feature('BASH_CLASSIFIER'):
                    result.pending_classifier_check = _build_pending_classifier_check(
                        input_cmd.get('command', ''), app_state.tool_permission_context
                    )
                return result

    # Split into subcommands
    cwd = get_cwd()
    cwd_mingw = windows_path_to_posix_path(cwd) if get_platform() == 'windows' else cwd
    raw_subcommands = ast_subcommands or shadow_legacy_subs or split_command(input_cmd.get('command', ''))
    subcommands, ast_commands_by_idx = _filter_cd_cwd_subcommands(
        raw_subcommands, ast_commands, cwd, cwd_mingw
    )

    # Cap subcommand fanout
    if ast_subcommands is None and len(subcommands) > MAX_SUBCOMMANDS_FOR_SECURITY_CHECK:
        log_for_debugging(
            f'bash_permissions: {len(subcommands)} subcommands exceeds cap '
            f'({MAX_SUBCOMMANDS_FOR_SECURITY_CHECK}) — returning ask',
            level='debug',
        )
        decision_reason = {
            'type': 'other',
            'reason': f'Command splits into {len(subcommands)} subcommands, too many to safety-check individually',
        }
        return PermissionResult(
            behavior='ask',
            message=create_permission_request_message(BashTool.name, decision_reason),
            decision_reason=decision_reason,
        )

    # Multiple cd check
    cd_commands = [sub for sub in subcommands if is_normalized_cd_command(sub)]
    if len(cd_commands) > 1:
        decision_reason = {
            'type': 'other',
            'reason': 'Multiple directory changes in one command require approval for clarity',
        }
        return PermissionResult(
            behavior='ask',
            decision_reason=decision_reason,
            message=create_permission_request_message(BashTool.name, decision_reason),
        )

    compound_command_has_cd = len(cd_commands) > 0

    # cd + git security check
    if compound_command_has_cd:
        has_git = any(is_normalized_git_command(sub.strip()) for sub in subcommands)
        if has_git:
            decision_reason = {
                'type': 'other',
                'reason': 'Compound commands with cd and git require approval to prevent bare repository attacks',
            }
            return PermissionResult(
                behavior='ask',
                decision_reason=decision_reason,
                message=create_permission_request_message(BashTool.name, decision_reason),
            )

    app_state = context.get_app_state()

    # Per-subcommand permission decisions
    subcommand_permission_decisions = [
        bash_tool_check_permission(
            {'command': sub},
            app_state.tool_permission_context,
            compound_command_has_cd,
            ast_commands_by_idx[i],
        )
        for i, sub in enumerate(subcommands)
    ]

    # Deny if any subcommand denied
    denied = next((r for r in subcommand_permission_decisions if r.behavior == 'deny'), None)
    if denied:
        return PermissionResult(
            behavior='deny',
            message=f'Permission to use {BashTool.name} with command {input_cmd.get("command", "")} has been denied.',
            decision_reason={
                'type': 'subcommandResults',
                'reasons': dict(zip(subcommands, subcommand_permission_decisions)),
            },
        )

    # Validate output redirections on original command
    path_result = check_path_constraints(
        input_cmd, get_cwd(), app_state.tool_permission_context,
        compound_command_has_cd, ast_redirects, ast_commands,
    )
    if path_result.behavior == 'deny':
        return path_result

    ask_subresult = next((r for r in subcommand_permission_decisions if r.behavior == 'ask'), None)
    non_allow_count = sum(1 for r in subcommand_permission_decisions if r.behavior != 'allow')

    if path_result.behavior == 'ask' and ask_subresult is None:
        return path_result

    if ask_subresult is not None and non_allow_count == 1:
        result = PermissionResult(
            behavior='ask',
            message=ask_subresult.message,
            decision_reason=ask_subresult.decision_reason,
            suggestions=ask_subresult.suggestions,
        )
        if _feature('BASH_CLASSIFIER'):
            result.pending_classifier_check = _build_pending_classifier_check(
                input_cmd.get('command', ''), app_state.tool_permission_context
            )
        return result

    if exact_result.behavior == 'allow':
        return exact_result

    # Check command injection per subcommand (legacy path only)
    has_possible_injection = False
    if (
        ast_subcommands is None and
        not is_env_truthy(os.environ.get('CLAUDE_CODE_DISABLE_COMMAND_INJECTION_CHECK'))
    ):
        divergence_count = 0

        def on_divergence():
            nonlocal divergence_count
            divergence_count += 1

        safety_results = await asyncio.gather(*[
            bash_command_is_safe_async_deprecated(sub, on_divergence)
            for sub in subcommands
        ])
        has_possible_injection = any(r.behavior != 'passthrough' for r in safety_results)
        if divergence_count > 0:
            log_event('tengu_tree_sitter_security_divergence', {
                'quoteContextDivergence': True,
                'count': divergence_count,
            })

    if (
        all(r.behavior == 'allow' for r in subcommand_permission_decisions) and
        not has_possible_injection
    ):
        return PermissionResult(
            behavior='allow',
            updated_input=input_cmd,
            decision_reason={
                'type': 'subcommandResults',
                'reasons': dict(zip(subcommands, subcommand_permission_decisions)),
            },
        )

    # Query command prefix (skip unless custom fn)
    command_subcommand_prefix = None
    if get_command_subcommand_prefix_fn != get_command_subcommand_prefix:
        command_subcommand_prefix = await get_command_subcommand_prefix_fn(
            input_cmd.get('command', ''),
            context.abort_controller.signal,
            context.options.is_non_interactive_session,
        )

    app_state = context.get_app_state()

    # Single subcommand path
    if len(subcommands) == 1:
        result = await check_command_and_suggest_rules(
            {'command': subcommands[0]},
            app_state.tool_permission_context,
            command_subcommand_prefix,
            compound_command_has_cd,
            ast_subcommands is not None,
        )
        if result.behavior in ('ask', 'passthrough'):
            if _feature('BASH_CLASSIFIER'):
                result.pending_classifier_check = _build_pending_classifier_check(
                    input_cmd.get('command', ''), app_state.tool_permission_context
                )
        return result

    # Multiple subcommands
    subcommand_results: Dict[str, PermissionResult] = {}
    for sub in subcommands:
        sub_prefix = None
        if command_subcommand_prefix:
            sub_prefixes = getattr(command_subcommand_prefix, 'subcommandPrefixes', {})
            sub_prefix = sub_prefixes.get(sub) if sub_prefixes else None
        subcommand_results[sub] = await check_command_and_suggest_rules(
            {**input_cmd, 'command': sub},
            app_state.tool_permission_context,
            sub_prefix,
            compound_command_has_cd,
            ast_subcommands is not None,
        )

    # Allow if all subcommands allowed
    if all(subcommand_results[sub].behavior == 'allow' for sub in subcommands):
        return PermissionResult(
            behavior='allow',
            updated_input=input_cmd,
            decision_reason={
                'type': 'subcommandResults',
                'reasons': subcommand_results,
            },
        )

    # Collect rules for permission prompt
    collected_rules: Dict[str, Any] = {}
    for sub, perm_result in subcommand_results.items():
        if perm_result.behavior in ('ask', 'passthrough'):
            updates = getattr(perm_result, 'suggestions', None)
            for rule in extract_rules(updates):
                rule_key = permission_rule_value_to_string(rule)
                collected_rules[rule_key] = rule

            if (
                perm_result.behavior == 'ask' and
                not collected_rules and
                (not perm_result.decision_reason or perm_result.decision_reason.get('type') != 'rule')
            ):
                for rule in extract_rules(_suggestion_for_exact_command(sub)):
                    rule_key = permission_rule_value_to_string(rule)
                    collected_rules[rule_key] = rule

    decision_reason = {
        'type': 'subcommandResults',
        'reasons': subcommand_results,
    }

    capped_rules = list(collected_rules.values())[:MAX_SUGGESTED_RULES_FOR_COMPOUND]
    suggested_updates = (
        [{'type': 'addRules', 'rules': capped_rules, 'behavior': 'allow', 'destination': 'localSettings'}]
        if capped_rules
        else None
    )

    final_behavior = 'ask' if ask_subresult is not None else 'passthrough'
    result = PermissionResult(
        behavior=final_behavior,
        message=create_permission_request_message(BashTool.name, decision_reason),
        decision_reason=decision_reason,
        suggestions=suggested_updates,
    )
    if _feature('BASH_CLASSIFIER'):
        result.pending_classifier_check = _build_pending_classifier_check(
            input_cmd.get('command', ''), app_state.tool_permission_context
        )
    return result


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

async def _noop_coro():
    return None
