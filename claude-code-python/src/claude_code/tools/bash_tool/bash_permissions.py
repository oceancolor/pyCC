"""
Bash permission rule matching and permission checking.
Ported from BashTool/bashPermissions.ts (2621 lines).

Provides permission rule parsing, matching, and the main bash permission check
pipeline for the BashTool.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import (
    Any, Dict, List, Literal, Optional, Set, Tuple, Union, TYPE_CHECKING
)

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
PermissionResult = Dict[str, Any]
PermissionRule = Dict[str, Any]
PermissionUpdate = Dict[str, Any]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# CC-643: On complex compound commands, splitCommand_DEPRECATED can produce a
# very large subcommands array (possible exponential growth). Fifty is
# generous: legitimate user commands don't split that wide. Above the cap we
# fall back to 'ask' (safe default — we can't prove safety, so we prompt).
MAX_SUBCOMMANDS_FOR_SECURITY_CHECK = 50

# GH#11380: Cap the number of per-subcommand rules suggested for compound
# commands. Beyond this, the "Yes, and don't ask again for X, Y, Z…" label
# degrades to "similar commands" anyway.
MAX_SUGGESTED_RULES_FOR_COMPOUND = 5

# Env-var assignment prefix (VAR=value). Shared across three while-loops that
# skip safe env vars before extracting the command name.
ENV_VAR_ASSIGN_RE = re.compile(r'^[A-Za-z_]\w*=')

# ---------------------------------------------------------------------------
# Safe env vars
# ---------------------------------------------------------------------------

# Whitelist of environment variables that are safe to strip from commands.
# These variables CANNOT execute code or load libraries.
#
# SECURITY: These must NEVER be added to the whitelist:
# - PATH, LD_PRELOAD, LD_LIBRARY_PATH, DYLD_* (execution/library loading)
# - PYTHONPATH, NODE_PATH, CLASSPATH, RUBYLIB (module loading)
# - GOFLAGS, RUSTFLAGS, NODE_OPTIONS (can contain code execution flags)
# - HOME, TMPDIR, SHELL, BASH_ENV (affect system behavior)
SAFE_ENV_VARS: Set[str] = frozenset([
    # Go - build/runtime settings only
    'GOEXPERIMENT', 'GOOS', 'GOARCH', 'CGO_ENABLED', 'GO111MODULE',
    # Rust - logging/debugging only
    'RUST_BACKTRACE', 'RUST_LOG',
    # Node - environment name only (not NODE_OPTIONS!)
    'NODE_ENV',
    # Python - behavior flags only (not PYTHONPATH!)
    'PYTHONUNBUFFERED', 'PYTHONDONTWRITEBYTECODE',
    # Pytest - test configuration
    'PYTEST_DISABLE_PLUGIN_AUTOLOAD', 'PYTEST_DEBUG',
    # API keys and authentication
    'ANTHROPIC_API_KEY',
    # Locale and character encoding
    'LANG', 'LANGUAGE', 'LC_ALL', 'LC_CTYPE', 'LC_TIME', 'CHARSET',
    # Terminal and display
    'TERM', 'COLORTERM', 'NO_COLOR', 'FORCE_COLOR', 'TZ',
    # Color configuration for various tools
    'LS_COLORS', 'LSCOLORS', 'GREP_COLOR', 'GREP_COLORS', 'GCC_COLORS',
    # Display formatting
    'TIME_STYLE', 'BLOCK_SIZE', 'BLOCKSIZE',
])

# ANT-ONLY environment variables that are safe to strip from commands.
# SECURITY: These are gated to internal users and MUST NEVER ship to external users.
ANT_ONLY_SAFE_ENV_VARS: Set[str] = frozenset([
    # Kubernetes and container config (config file pointers, not execution)
    'KUBECONFIG', 'DOCKER_HOST',
    # Cloud provider project/profile selection
    'AWS_PROFILE', 'CLOUDSDK_CORE_PROJECT', 'CLUSTER',
    # Anthropic internal cluster selection
    'COO_CLUSTER', 'COO_CLUSTER_NAME', 'COO_NAMESPACE', 'COO_LAUNCH_YAML_DRY_RUN',
    # Feature flags
    'SKIP_NODE_VERSION_CHECK', 'EXPECTTEST_ACCEPT', 'CI', 'GIT_LFS_SKIP_SMUDGE',
    # GPU/Device selection
    'CUDA_VISIBLE_DEVICES', 'JAX_PLATFORMS',
    # Display/terminal settings
    'COLUMNS', 'TMUX',
    # Test/debug configuration
    'POSTGRESQL_VERSION', 'FIRESTORE_EMULATOR_HOST', 'HARNESS_QUIET',
    'TEST_CROSSCHECK_LISTS_MATCH_UPDATE', 'DBT_PER_DEVELOPER_ENVIRONMENTS',
    'STATSIG_FORD_DB_CHECKS',
    # Build configuration
    'ANT_ENVIRONMENT', 'ANT_SERVICE', 'MONOREPO_ROOT_DIR',
    # Version selectors
    'PYENV_VERSION',
    # Credentials (approved subset)
    'PGPASSWORD', 'GH_TOKEN', 'GROWTHBOOK_API_KEY',
])

# Env vars that make a *different binary* run (injection or resolution hijack).
BINARY_HIJACK_VARS = re.compile(r'^(LD_|DYLD_|PATH$)')

# Bare-prefix suggestions like `bash:*` or `sh:*` would allow arbitrary code via `-c`.
BARE_SHELL_PREFIXES: Set[str] = frozenset([
    'sh', 'bash', 'zsh', 'fish', 'csh', 'tcsh', 'ksh', 'dash', 'cmd',
    'powershell', 'pwsh',
    # wrappers that exec their args as a command
    'env', 'xargs',
    # SECURITY: checkSemantics strips these wrappers to check the wrapped command.
    # Suggesting `Bash(nice:*)` would be ≈ `Bash(*)`
    'nice', 'stdbuf', 'nohup', 'timeout', 'time',
    # privilege escalation
    'sudo', 'doas', 'pkexec',
])

# ---------------------------------------------------------------------------
# Permission rule types
# ---------------------------------------------------------------------------

@dataclass
class PrefixRule:
    """Permission rule that matches by prefix (e.g., 'git commit:*' → prefix='git commit ')."""
    type: Literal['prefix'] = 'prefix'
    prefix: str = ''
    tool_name: str = 'Bash'


@dataclass
class ExactRule:
    """Permission rule that matches exactly (e.g., 'ls -la')."""
    type: Literal['exact'] = 'exact'
    command: str = ''
    tool_name: str = 'Bash'


@dataclass
class WildcardRule:
    """Permission rule with wildcard matching (e.g., 'git *')."""
    type: Literal['wildcard'] = 'wildcard'
    pattern: str = ''
    tool_name: str = 'Bash'


ShellPermissionRule = Union[PrefixRule, ExactRule, WildcardRule]

# ---------------------------------------------------------------------------
# Permission rule parsing
# ---------------------------------------------------------------------------

def parse_permission_rule(rule: str) -> ShellPermissionRule:
    """Parse a bash permission rule string into a structured rule."""
    if ':' in rule:
        colon = rule.index(':')
        suffix = rule[colon + 1:]
        prefix = rule[:colon]
        if suffix == '*':
            return PrefixRule(prefix=prefix + ' ')
        return WildcardRule(pattern=rule)
    if '*' in rule or '?' in rule:
        return WildcardRule(pattern=rule)
    return ExactRule(command=rule)


def match_wildcard_pattern(pattern: str, command: str) -> bool:
    """Match command against a wildcard pattern (* = any chars, ? = single char)."""
    import fnmatch
    return fnmatch.fnmatch(command, pattern)


def permission_rule_extract_prefix(rule: str) -> Optional[str]:
    """Extract prefix from legacy :* syntax (e.g., 'npm:*' -> 'npm')."""
    if rule.endswith(':*'):
        return rule[:-2]
    return None


def bash_permission_rule(permission_rule: str) -> ShellPermissionRule:
    """Parse a permission rule (public alias matching TS export)."""
    return parse_permission_rule(permission_rule)


# ---------------------------------------------------------------------------
# Safe wrapper stripping
# ---------------------------------------------------------------------------

def _is_ant_only_safe(var_name: str) -> bool:
    """Returns True if the var is in ANT_ONLY_SAFE_ENV_VARS (gated to ant users)."""
    return os.environ.get('USER_TYPE') == 'ant' and var_name in ANT_ONLY_SAFE_ENV_VARS


def strip_comment_lines(command: str) -> str:
    """
    Strip full-line comments from a command.
    Only strips full-line comments (lines where the entire line is a comment),
    not inline comments that appear after a command on the same line.
    """
    lines = command.split('\n')
    non_comment_lines = [
        line for line in lines
        if line.strip() and not line.strip().startswith('#')
    ]

    if not non_comment_lines:
        return command

    return '\n'.join(non_comment_lines)


# Pattern for environment variables (strict: only safe-char values)
_ENV_VAR_PATTERN_STRIP = re.compile(
    r'^([A-Za-z_][A-Za-z0-9_]*)=([A-Za-z0-9_./:-]+)[ \t]+'
)

# Safe wrapper patterns (ordered for correct application)
_SAFE_WRAPPER_PATTERNS = [
    # timeout: GNU long flags + short flags + duration
    re.compile(
        r'^timeout[ \t]+(?:(?:--(?:foreground|preserve-status|verbose)'
        r'|--(?:kill-after|signal)=[A-Za-z0-9_.+-]+'
        r'|--(?:kill-after|signal)[ \t]+[A-Za-z0-9_.+-]+'
        r'|-v|-[ks][ \t]+[A-Za-z0-9_.+-]+'
        r'|-[ks][A-Za-z0-9_.+-]+)[ \t]+)*(?:--[ \t]+)?\d+(?:\.\d+)?[smhd]?[ \t]+'
    ),
    re.compile(r'^time[ \t]+(?:--[ \t]+)?'),
    re.compile(r'^nice(?:[ \t]+-n[ \t]+-?\d+|[ \t]+-\d+)?[ \t]+(?:--[ \t]+)?'),
    re.compile(r'^stdbuf(?:[ \t]+-[ioe][LN0-9]+)+[ \t]+(?:--[ \t]+)?'),
    re.compile(r'^nohup[ \t]+(?:--[ \t]+)?'),
]


def strip_safe_wrappers(command: str) -> str:
    """
    Strip safe wrapper commands (timeout, time, nice, nohup, stdbuf) and
    safe environment variables from a command string for permission matching.
    
    SECURITY: Use [ \\t]+ not \\s+ — \\s matches \\n/\\r which are command
    separators in bash. Matching across a newline would strip the wrapper from
    one line and leave a different command on the next line for bash to execute.
    """
    stripped = command
    previous_stripped = ''

    # Phase 1: Strip leading env vars and comments only.
    while stripped != previous_stripped:
        previous_stripped = stripped
        stripped = strip_comment_lines(stripped)

        env_var_match = _ENV_VAR_PATTERN_STRIP.match(stripped)
        if env_var_match:
            var_name = env_var_match.group(1)
            if var_name in SAFE_ENV_VARS or _is_ant_only_safe(var_name):
                stripped = _ENV_VAR_PATTERN_STRIP.sub('', stripped, count=1)

    # Phase 2: Strip wrapper commands and comments only. Do NOT strip env vars.
    # Wrapper commands use execvp to run their arguments, so VAR=val after a
    # wrapper is treated as the COMMAND to execute, not as an env var assignment.
    previous_stripped = ''
    while stripped != previous_stripped:
        previous_stripped = stripped
        stripped = strip_comment_lines(stripped)

        for pattern in _SAFE_WRAPPER_PATTERNS:
            new = pattern.sub('', stripped, count=1)
            if new != stripped:
                stripped = new
                break

    return stripped.strip()


# Pattern for stripping ALL leading env vars (broader, for deny rules)
_ENV_VAR_PATTERN_BROAD = re.compile(
    r"""^([A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\])?)\+?="""
    r"""(?:'[^'\n\r]*'|"(?:\\.|[^"$`\\\n\r])*"|\\.|[^ \t\n\r$`;|&()<>\\\\'"])*[ \t]+"""
)


def strip_all_leading_env_vars(command: str, blocklist: Optional[re.Pattern] = None) -> str:
    """
    Strip ALL leading env var prefixes from a command, regardless of whether the
    var name is in the safe-list.
    
    Used for deny/ask rule matching: when a user denies `claude` or `rm`, the
    command should stay blocked even if prefixed with arbitrary env vars like
    `FOO=bar claude`.
    
    @param blocklist - optional regex tested against each var name; matching vars
      are NOT stripped. Pass BINARY_HIJACK_VARS for excludedCommands.
    """
    stripped = command
    previous_stripped = ''

    while stripped != previous_stripped:
        previous_stripped = stripped
        stripped = strip_comment_lines(stripped)

        m = _ENV_VAR_PATTERN_BROAD.match(stripped)
        if not m:
            continue
        if blocklist and blocklist.match(m.group(1)):
            break
        stripped = stripped[len(m.group(0)):]

    return stripped.strip()


# ---------------------------------------------------------------------------
# Command prefix extraction
# ---------------------------------------------------------------------------

def get_simple_command_prefix(command: str) -> Optional[str]:
    """
    Extract a stable command prefix (command + subcommand) from a raw command string.
    Skips leading env var assignments only if they are in SAFE_ENV_VARS.
    Returns None if a non-safe env var is encountered, or if the second token
    doesn't look like a subcommand (lowercase alphanumeric).

    Examples:
      'git commit -m "fix typo"' → 'git commit'
      'NODE_ENV=prod npm run build' → 'npm run' (NODE_ENV is safe)
      'MY_VAR=val npm run build' → None (MY_VAR is not safe)
      'ls -la' → None (flag, not a subcommand)
    """
    tokens = [t for t in command.strip().split() if t]
    if not tokens:
        return None

    i = 0
    while i < len(tokens) and ENV_VAR_ASSIGN_RE.match(tokens[i]):
        var_name = tokens[i].split('=')[0]
        if var_name not in SAFE_ENV_VARS and not _is_ant_only_safe(var_name):
            return None
        i += 1

    remaining = tokens[i:]
    if len(remaining) < 2:
        return None
    subcmd = remaining[1]
    # Second token must look like a subcommand (e.g., "commit", "run", "compose"),
    # not a flag (-rf), filename (file.txt), path (/tmp), URL, or number (755).
    if not re.match(r'^[a-z][a-z0-9]*(-[a-z0-9]+)*$', subcmd):
        return None
    return ' '.join(remaining[:2])


def get_first_word_prefix(command: str) -> Optional[str]:
    """
    UI-only fallback: extract the first word alone when get_simple_command_prefix
    declines. Used as an editable starting point in the permission dialog.
    
    Reuses the same SAFE_ENV_VARS gate as get_simple_command_prefix.
    """
    tokens = [t for t in command.strip().split() if t]

    i = 0
    while i < len(tokens) and ENV_VAR_ASSIGN_RE.match(tokens[i]):
        var_name = tokens[i].split('=')[0]
        if var_name not in SAFE_ENV_VARS and not _is_ant_only_safe(var_name):
            return None
        i += 1

    if i >= len(tokens):
        return None
    cmd = tokens[i]
    # Same shape check as the subcommand regex in get_simple_command_prefix:
    # rejects paths (./script.sh, /usr/bin/python), flags, numbers, filenames.
    if not re.match(r'^[a-z][a-z0-9]*(-[a-z0-9]+)*$', cmd):
        return None
    if cmd in BARE_SHELL_PREFIXES:
        return None
    return cmd


# ---------------------------------------------------------------------------
# Suggestion helpers
# ---------------------------------------------------------------------------

def _suggestion_for_prefix(tool_name: str, prefix: str) -> List[PermissionUpdate]:
    """Create a prefix-rule suggestion."""
    return [{'type': 'add', 'toolName': tool_name, 'value': f'{prefix}:*', 'ruleType': 'allow'}]


def _suggestion_for_exact_command(tool_name: str, command: str) -> List[PermissionUpdate]:
    """Create an exact-match rule suggestion."""
    return [{'type': 'add', 'toolName': tool_name, 'value': command, 'ruleType': 'allow'}]


def extract_prefix_before_heredoc(command: str) -> Optional[str]:
    """
    If the command contains a heredoc (<<), extract the command prefix before it.
    Returns the first word(s) before the heredoc operator as a stable prefix,
    or None if the command doesn't contain a heredoc.
    """
    if '<<' not in command:
        return None

    idx = command.find('<<')
    if idx <= 0:
        return None

    before = command[:idx].strip()
    if not before:
        return None

    prefix = get_simple_command_prefix(before)
    if prefix:
        return prefix

    tokens = [t for t in before.split() if t]
    i = 0
    while i < len(tokens) and ENV_VAR_ASSIGN_RE.match(tokens[i]):
        var_name = tokens[i].split('=')[0]
        if var_name not in SAFE_ENV_VARS and not _is_ant_only_safe(var_name):
            return None
        i += 1
    if i >= len(tokens):
        return None
    return ' '.join(tokens[i:i + 2]) or None


def suggestion_for_exact_command(command: str) -> List[PermissionUpdate]:
    """
    Suggest a permission update for an exact command.
    Prefers prefix rules over exact-match for heredoc and multiline commands.
    """
    tool_name = 'Bash'

    # Heredoc commands contain multi-line content that changes each invocation,
    # making exact-match rules useless.
    heredoc_prefix = extract_prefix_before_heredoc(command)
    if heredoc_prefix:
        return _suggestion_for_prefix(tool_name, heredoc_prefix)

    # Multiline commands without heredoc also make poor exact-match rules.
    if '\n' in command:
        first_line = command.split('\n')[0].strip()
        if first_line:
            return _suggestion_for_prefix(tool_name, first_line)

    # Single-line commands: extract a 2-word prefix for reusable rules.
    prefix = get_simple_command_prefix(command)
    if prefix:
        return _suggestion_for_prefix(tool_name, prefix)

    return _suggestion_for_exact_command(tool_name, command)


def suggestion_for_prefix(prefix: str) -> List[PermissionUpdate]:
    """Create a suggestion for a prefix-based permission rule."""
    return _suggestion_for_prefix('Bash', prefix)


# ---------------------------------------------------------------------------
# Rule matching
# ---------------------------------------------------------------------------

def check_rule_matches(rule: ShellPermissionRule, command: str) -> bool:
    """Return True if the command matches the given permission rule."""
    if isinstance(rule, ExactRule):
        return command.strip() == rule.command
    if isinstance(rule, PrefixRule):
        cmd = command.strip()
        prefix = rule.prefix
        return cmd == prefix.rstrip() or cmd.startswith(prefix)
    if isinstance(rule, WildcardRule):
        return match_wildcard_pattern(rule.pattern, command.strip())
    return False


def _split_command(command: str) -> List[str]:
    """
    Split a compound command into individual subcommands.
    This is a simplified implementation of splitCommand_DEPRECATED.
    Handles: &&, ||, ;, |, and newline separators.
    """
    # Import from bash_command_helpers if available, else use simple split
    try:
        from claude_code.tools.bash_tool.bash_command_helpers import split_command
        return split_command(command)
    except (ImportError, AttributeError):
        pass

    # Fallback: simple regex-based split
    # Split on && || ; | but not inside quotes
    parts = []
    current = ''
    in_sq = False
    in_dq = False
    escaped = False
    i = 0

    while i < len(command):
        c = command[i]

        if escaped:
            current += c
            escaped = False
            i += 1
            continue

        if c == '\\' and not in_sq:
            current += c
            escaped = True
            i += 1
            continue

        if c == "'" and not in_dq:
            in_sq = not in_sq
            current += c
            i += 1
            continue

        if c == '"' and not in_sq:
            in_dq = not in_dq
            current += c
            i += 1
            continue

        if not in_sq and not in_dq:
            # Check for operators
            remaining = command[i:]
            if remaining.startswith('&&'):
                if current.strip():
                    parts.append(current.strip())
                current = ''
                i += 2
                continue
            if remaining.startswith('||'):
                if current.strip():
                    parts.append(current.strip())
                current = ''
                i += 2
                continue
            if c in ';|\n':
                if current.strip():
                    parts.append(current.strip())
                current = ''
                i += 1
                continue

        current += c
        i += 1

    if current.strip():
        parts.append(current.strip())

    return parts if parts else [command]


def _extract_output_redirections(command: str) -> dict:
    """
    Extract output redirections from a command string.
    Returns dict with: command_without_redirections.
    """
    try:
        from claude_code.tools.bash_tool.bash_command_helpers import extract_output_redirections
        return extract_output_redirections(command)
    except (ImportError, AttributeError):
        pass

    # Simplified: strip common output redirections
    # Note: security validation of redirection targets happens separately
    result = re.sub(r'\s*[12]?>\s*\S+', '', command)
    return {'commandWithoutRedirections': result.strip()}


def filter_rules_by_contents_matching_input(
    command: str,
    rules: Dict[str, Any],  # map of rule_content -> PermissionRule
    match_mode: Literal['exact', 'prefix'],
    strip_all_env_vars: bool = False,
    skip_compound_check: bool = False,
) -> List[Any]:
    """
    Filter permission rules to those that match the given command.
    
    SECURITY: For prefix/wildcard matching, compound commands (e.g., `cmd1 && cmd2`)
    are NOT matched by prefix/wildcard rules. This prevents Bash(cd:*) from matching
    "cd /path && python3 evil.py".
    """
    cmd = command.strip()

    # Strip output redirections for permission matching
    # This allows rules like Bash(python:*) to match "python script.py > output.txt"
    # Security validation of redirection targets happens separately
    redir_result = _extract_output_redirections(cmd)
    cmd_without_redirections = redir_result.get('commandWithoutRedirections', cmd)

    # For exact matching, try both the original command and the command without redirections
    # For prefix matching, only use the command without redirections
    if match_mode == 'exact':
        commands_for_matching = [cmd, cmd_without_redirections]
    else:
        commands_for_matching = [cmd_without_redirections]

    # Strip safe wrapper commands (timeout, time, nice, nohup) and env vars for matching
    commands_to_try = []
    for c in commands_for_matching:
        stripped = strip_safe_wrappers(c)
        if stripped != c:
            commands_to_try.extend([c, stripped])
        else:
            commands_to_try.append(c)

    # SECURITY: For deny/ask rules, also try matching after stripping ALL leading
    # env var prefixes. This prevents bypass via `FOO=bar denied_command`.
    if strip_all_env_vars:
        seen = set(commands_to_try)
        start_idx = 0
        while start_idx < len(commands_to_try):
            end_idx = len(commands_to_try)
            for i in range(start_idx, end_idx):
                c = commands_to_try[i]
                if not c:
                    continue
                env_stripped = strip_all_leading_env_vars(c)
                if env_stripped not in seen:
                    commands_to_try.append(env_stripped)
                    seen.add(env_stripped)
                wrapper_stripped = strip_safe_wrappers(c)
                if wrapper_stripped not in seen:
                    commands_to_try.append(wrapper_stripped)
                    seen.add(wrapper_stripped)
            start_idx = end_idx

    # Precompute compound-command status for each candidate
    is_compound_command: Dict[str, bool] = {}
    if match_mode == 'prefix' and not skip_compound_check:
        for c in commands_to_try:
            if c not in is_compound_command:
                is_compound_command[c] = len(_split_command(c)) > 1

    matching = []
    for rule_content, rule in rules.items():
        bash_rule = bash_permission_rule(rule_content)

        matched = False
        for cmd_to_match in commands_to_try:
            if isinstance(bash_rule, ExactRule):
                if bash_rule.command == cmd_to_match:
                    matched = True
                    break

            elif isinstance(bash_rule, PrefixRule):
                if match_mode == 'exact':
                    if bash_rule.prefix == cmd_to_match:
                        matched = True
                        break
                else:  # prefix mode
                    # SECURITY: Don't allow prefix rules to match compound commands.
                    if is_compound_command.get(cmd_to_match, False):
                        continue
                    # Ensure word boundary
                    if cmd_to_match == bash_rule.prefix.rstrip():
                        matched = True
                        break
                    if cmd_to_match.startswith(bash_rule.prefix):
                        matched = True
                        break
                    # Also match "xargs <prefix>" for bare xargs with no flags.
                    xargs_prefix = 'xargs ' + bash_rule.prefix
                    if cmd_to_match == xargs_prefix.rstrip():
                        matched = True
                        break
                    if cmd_to_match.startswith(xargs_prefix):
                        matched = True
                        break

            elif isinstance(bash_rule, WildcardRule):
                # SECURITY FIX: In exact match mode, wildcards must NOT match
                # because we're checking the full unparsed command.
                if match_mode == 'exact':
                    continue
                # SECURITY: Same as prefix rules — don't allow wildcard rules
                # to match compound commands.
                if is_compound_command.get(cmd_to_match, False):
                    continue
                if match_wildcard_pattern(bash_rule.pattern, cmd_to_match):
                    matched = True
                    break

        if matched:
            matching.append(rule)

    return matching


def _get_rules_by_type(
    tool_permission_context: Dict[str, Any],
    rule_type: str,
) -> Dict[str, Any]:
    """
    Extract rules of a given type from the permission context.
    Returns a dict mapping rule_content -> rule.
    """
    if not tool_permission_context:
        return {}

    rules = {}
    # Try to get rules from the context in various formats
    bash_rules = (
        tool_permission_context.get('toolPermissions', {})
        .get('Bash', {})
        .get(rule_type, [])
    )
    for rule in bash_rules:
        if isinstance(rule, dict):
            content = rule.get('content') or rule.get('value') or str(rule)
        else:
            content = str(rule)
        rules[content] = rule

    # Also try permissions dict format
    perms = tool_permission_context.get('permissions', {})
    if isinstance(perms, dict):
        for content in perms.get(rule_type, []):
            rules[str(content)] = {'content': str(content), 'ruleType': rule_type}

    return rules


def matching_rules_for_input(
    command: str,
    tool_permission_context: Dict[str, Any],
    match_mode: Literal['exact', 'prefix'],
    skip_compound_check: bool = False,
) -> dict:
    """Get all matching deny, ask, and allow rules for the given command."""
    deny_rules = _get_rules_by_type(tool_permission_context, 'deny')
    # SECURITY: Deny/ask rules use aggressive env var stripping so that
    # `FOO=bar denied_command` still matches a deny rule for `denied_command`.
    matching_deny_rules = filter_rules_by_contents_matching_input(
        command, deny_rules, match_mode,
        strip_all_env_vars=True, skip_compound_check=True,
    )

    ask_rules = _get_rules_by_type(tool_permission_context, 'ask')
    matching_ask_rules = filter_rules_by_contents_matching_input(
        command, ask_rules, match_mode,
        strip_all_env_vars=True, skip_compound_check=True,
    )

    allow_rules = _get_rules_by_type(tool_permission_context, 'allow')
    matching_allow_rules = filter_rules_by_contents_matching_input(
        command, allow_rules, match_mode,
        skip_compound_check=skip_compound_check,
    )

    return {
        'matchingDenyRules': matching_deny_rules,
        'matchingAskRules': matching_ask_rules,
        'matchingAllowRules': matching_allow_rules,
    }


def _create_permission_request_message(
    tool_name: str = 'Bash',
    decision_reason: Optional[Dict[str, Any]] = None,
) -> str:
    """Create a user-facing permission request message."""
    if decision_reason and decision_reason.get('reason'):
        return f"Claude wants to use {tool_name}. {decision_reason['reason']}"
    return f"Claude wants to use {tool_name}"


# ---------------------------------------------------------------------------
# Bash tool permission checks
# ---------------------------------------------------------------------------

def bash_tool_check_exact_match_permission(
    command: str,
    tool_permission_context: Dict[str, Any],
) -> PermissionResult:
    """Check if the command has an exact match permission rule."""
    cmd = command.strip()

    rules = matching_rules_for_input(command, tool_permission_context, 'exact')

    # 1. Deny if exact command was denied
    if rules['matchingDenyRules']:
        return {
            'behavior': 'deny',
            'message': f'Permission to use Bash with command {cmd} has been denied.',
            'decisionReason': {'type': 'rule', 'rule': rules['matchingDenyRules'][0]},
        }

    # 2. Ask if exact command was in ask rules
    if rules['matchingAskRules']:
        return {
            'behavior': 'ask',
            'message': _create_permission_request_message('Bash'),
            'decisionReason': {'type': 'rule', 'rule': rules['matchingAskRules'][0]},
        }

    # 3. Allow if exact command was allowed
    if rules['matchingAllowRules']:
        return {
            'behavior': 'allow',
            'updatedInput': {'command': command},
            'decisionReason': {'type': 'rule', 'rule': rules['matchingAllowRules'][0]},
        }

    # 4. Otherwise, passthrough
    decision_reason = {'type': 'other', 'reason': 'This command requires approval'}
    return {
        'behavior': 'passthrough',
        'message': _create_permission_request_message('Bash', decision_reason),
        'decisionReason': decision_reason,
        'suggestions': suggestion_for_exact_command(cmd),
    }


def bash_tool_check_permission(
    command: str,
    tool_permission_context: Dict[str, Any],
    compound_command_has_cd: Optional[bool] = None,
    ast_command: Optional[Any] = None,
) -> PermissionResult:
    """
    Main permission check for a bash subcommand.
    Applies deny/ask rules, path constraints, allow rules, mode checks, and read-only checks.
    """
    cmd = command.strip()

    # 1. Check exact match first
    exact_match_result = bash_tool_check_exact_match_permission(command, tool_permission_context)

    # 1a. Deny/ask if exact command has a rule
    if exact_match_result['behavior'] in ('deny', 'ask'):
        return exact_match_result

    # 2. Find all matching rules (prefix or exact)
    # SECURITY FIX: Check Bash deny/ask rules BEFORE path constraints to prevent bypass
    # via absolute paths outside the project directory (HackerOne report)
    rules = matching_rules_for_input(
        command,
        tool_permission_context,
        'prefix',
        skip_compound_check=(ast_command is not None),
    )

    # 2a. Deny if command has a deny rule
    if rules['matchingDenyRules']:
        return {
            'behavior': 'deny',
            'message': f'Permission to use Bash with command {cmd} has been denied.',
            'decisionReason': {'type': 'rule', 'rule': rules['matchingDenyRules'][0]},
        }

    # 2b. Ask if command has an ask rule
    if rules['matchingAskRules']:
        return {
            'behavior': 'ask',
            'message': _create_permission_request_message('Bash'),
            'decisionReason': {'type': 'rule', 'rule': rules['matchingAskRules'][0]},
        }

    # 3. Check path constraints (deferred to path_validation module)
    try:
        from claude_code.tools.bash_tool.path_validation import check_path_constraints
        path_result = check_path_constraints(
            {'command': command},
            os.getcwd(),
            tool_permission_context,
            compound_command_has_cd,
            None,  # redirects
            None,  # ast commands
        )
        if path_result['behavior'] != 'passthrough':
            return path_result
    except (ImportError, AttributeError):
        pass  # path_validation not available

    # 4. Allow if command had an exact match allow
    if exact_match_result['behavior'] == 'allow':
        return exact_match_result

    # 5. Allow if command has an allow rule
    if rules['matchingAllowRules']:
        return {
            'behavior': 'allow',
            'updatedInput': {'command': command},
            'decisionReason': {'type': 'rule', 'rule': rules['matchingAllowRules'][0]},
        }

    # 5b. Check sed constraints (blocks dangerous sed operations before mode auto-allow)
    try:
        from claude_code.tools.bash_tool.sed_validation import check_sed_constraints
        sed_result = check_sed_constraints({'command': command}, tool_permission_context)
        if sed_result['behavior'] != 'passthrough':
            return sed_result
    except (ImportError, AttributeError):
        pass

    # 6. Check for mode-specific permission handling
    try:
        from claude_code.tools.bash_tool.mode_validation import check_permission_mode
        mode_result = check_permission_mode({'command': command}, tool_permission_context)
        if mode_result['behavior'] != 'passthrough':
            return mode_result
    except (ImportError, AttributeError):
        pass

    # 7. Check read-only rules
    # (BashTool.isReadOnly equivalent - checking if command is read-only)
    # We can't easily check this without the full BashTool, so skip for now

    # 8. Passthrough since no rules match, will trigger permission prompt
    decision_reason = {'type': 'other', 'reason': 'This command requires approval'}
    return {
        'behavior': 'passthrough',
        'message': _create_permission_request_message('Bash', decision_reason),
        'decisionReason': decision_reason,
        'suggestions': suggestion_for_exact_command(command),
    }


async def check_command_and_suggest_rules(
    command: str,
    tool_permission_context: Dict[str, Any],
    command_prefix_result: Optional[Any] = None,
    compound_command_has_cd: Optional[bool] = None,
    ast_parse_succeeded: Optional[bool] = None,
) -> PermissionResult:
    """
    Processes an individual subcommand and applies prefix checks & suggestions.
    This is the async version used in the main permission pipeline.
    """
    # 1. Check exact match first
    exact_match_result = bash_tool_check_exact_match_permission(command, tool_permission_context)
    if exact_match_result['behavior'] != 'passthrough':
        return exact_match_result

    # 2. Check the command prefix
    permission_result = bash_tool_check_permission(
        command, tool_permission_context, compound_command_has_cd,
    )

    # 2a. Deny/ask if command was explicitly denied/asked
    if permission_result['behavior'] in ('deny', 'ask'):
        return permission_result

    # 3. Ask for permission if command injection is detected.
    # Skip when the AST parse already succeeded — tree-sitter has verified
    # there are no hidden substitutions or structural tricks.
    if not ast_parse_succeeded and not os.environ.get('CLAUDE_CODE_DISABLE_COMMAND_INJECTION_CHECK'):
        from claude_code.tools.bash_tool.bash_security import bash_command_is_safe_deprecated
        safety_result = bash_command_is_safe_deprecated(command)

        if safety_result['behavior'] != 'passthrough':
            decision_reason = {
                'type': 'other',
                'reason': (
                    safety_result.get('message')
                    if safety_result['behavior'] == 'ask' and safety_result.get('message')
                    else 'This command contains patterns that could pose security risks and requires approval'
                ),
            }
            return {
                'behavior': 'ask',
                'message': _create_permission_request_message('Bash', decision_reason),
                'decisionReason': decision_reason,
                'suggestions': [],  # Don't suggest saving a potentially dangerous command
            }

    # 4. Allow if command was allowed
    if permission_result['behavior'] == 'allow':
        return permission_result

    # 5. Suggest prefix if available, otherwise exact command
    prefix = None
    if command_prefix_result and isinstance(command_prefix_result, dict):
        prefix = command_prefix_result.get('commandPrefix')

    suggested_updates = (
        suggestion_for_prefix(prefix) if prefix
        else suggestion_for_exact_command(command)
    )

    return {**permission_result, 'suggestions': suggested_updates}


def check_sandbox_auto_allow(
    command: str,
    tool_permission_context: Dict[str, Any],
) -> PermissionResult:
    """
    Checks if a command should be auto-allowed when sandboxed.
    Returns early if there are explicit deny/ask rules that should be respected.
    
    NOTE: This function should only be called when sandboxing and auto-allow are enabled.
    """
    cmd = command.strip()

    # Check for explicit deny/ask rules on the full command (exact + prefix)
    rules = matching_rules_for_input(command, tool_permission_context, 'prefix')

    # Return immediately if there's an explicit deny rule on the full command
    if rules['matchingDenyRules']:
        return {
            'behavior': 'deny',
            'message': f'Permission to use Bash with command {cmd} has been denied.',
            'decisionReason': {'type': 'rule', 'rule': rules['matchingDenyRules'][0]},
        }

    # SECURITY: For compound commands, check each subcommand against deny/ask
    # rules. Prefix rules like Bash(rm:*) won't match the full compound command.
    subcommands = _split_command(cmd)
    if len(subcommands) > 1:
        first_ask_rule = None
        for sub in subcommands:
            sub_result = matching_rules_for_input(sub, tool_permission_context, 'prefix')
            # Deny takes priority — return immediately
            if sub_result['matchingDenyRules']:
                return {
                    'behavior': 'deny',
                    'message': f'Permission to use Bash with command {cmd} has been denied.',
                    'decisionReason': {'type': 'rule', 'rule': sub_result['matchingDenyRules'][0]},
                }
            # Stash first ask match
            if first_ask_rule is None and sub_result['matchingAskRules']:
                first_ask_rule = sub_result['matchingAskRules'][0]
        if first_ask_rule:
            return {
                'behavior': 'ask',
                'message': _create_permission_request_message('Bash'),
                'decisionReason': {'type': 'rule', 'rule': first_ask_rule},
            }

    # Full-command ask check (after all deny sources have been exhausted)
    if rules['matchingAskRules']:
        return {
            'behavior': 'ask',
            'message': _create_permission_request_message('Bash'),
            'decisionReason': {'type': 'rule', 'rule': rules['matchingAskRules'][0]},
        }

    # No explicit rules, so auto-allow with sandbox
    return {
        'behavior': 'allow',
        'updatedInput': {'command': command},
        'decisionReason': {
            'type': 'other',
            'reason': 'Auto-allowed with sandbox (autoAllowBashIfSandboxed enabled)',
        },
    }


def check_early_exit_deny(
    command: str,
    tool_permission_context: Dict[str, Any],
) -> Optional[PermissionResult]:
    """
    Early-exit deny enforcement. Returns the exact-match result if non-passthrough,
    then checks prefix/wildcard deny rules. Returns None if neither matched,
    meaning the caller should fall through to ask.
    """
    exact_match_result = bash_tool_check_exact_match_permission(command, tool_permission_context)
    if exact_match_result['behavior'] != 'passthrough':
        return exact_match_result

    rules = matching_rules_for_input(command, tool_permission_context, 'prefix')
    if rules['matchingDenyRules']:
        return {
            'behavior': 'deny',
            'message': f'Permission to use Bash with command {command} has been denied.',
            'decisionReason': {'type': 'rule', 'rule': rules['matchingDenyRules'][0]},
        }

    return None


def check_semantics_deny(
    command: str,
    tool_permission_context: Dict[str, Any],
    commands: List[Dict[str, str]],
) -> Optional[PermissionResult]:
    """
    checkSemantics-path deny enforcement. Calls check_early_exit_deny
    (exact-match + full-command prefix deny), then checks each individual
    SimpleCommand .text span against prefix deny rules.
    
    The per-subcommand check is needed because filter_rules_by_contents_matching_input
    has a compound-command guard that defeats `Bash(eval:*)` matching against
    a full pipeline like `echo foo | eval rm`.
    """
    full_cmd_result = check_early_exit_deny(command, tool_permission_context)
    if full_cmd_result is not None:
        return full_cmd_result

    for cmd in commands:
        text = cmd.get('text', '')
        sub_result = matching_rules_for_input(text, tool_permission_context, 'prefix')
        if sub_result['matchingDenyRules']:
            return {
                'behavior': 'deny',
                'message': f'Permission to use Bash with command {command} has been denied.',
                'decisionReason': {'type': 'rule', 'rule': sub_result['matchingDenyRules'][0]},
            }

    return None


# ---------------------------------------------------------------------------
# Main bash tool has permission
# ---------------------------------------------------------------------------

async def bash_tool_has_permission(
    input_data: Dict[str, Any],
    tool_permission_context: Dict[str, Any],
    context: Optional[Any] = None,
) -> PermissionResult:
    """
    Main entry point for bash permission checking.
    
    Applies the full permission pipeline:
    1. Sandbox auto-allow (if sandboxed)
    2. Pre-split strip safe heredocs
    3. Split compound command into subcommands
    4. Check each subcommand via check_command_and_suggest_rules
    5. Aggregate results
    """
    command = input_data.get('command', '')
    if not command:
        return {
            'behavior': 'allow',
            'updatedInput': input_data,
            'decisionReason': {'type': 'other', 'reason': 'Empty command is safe'},
        }

    # Check if we should use sandbox auto-allow
    try:
        from claude_code.tools.bash_tool.should_use_sandbox import should_use_sandbox
        use_sandbox = should_use_sandbox(tool_permission_context)
        if use_sandbox and tool_permission_context.get('autoAllowBashIfSandboxed'):
            return check_sandbox_auto_allow(command, tool_permission_context)
    except (ImportError, AttributeError):
        pass

    # Pre-split: strip safe heredocs and re-check the remainder
    from claude_code.tools.bash_tool.bash_security import (
        strip_safe_heredoc_substitutions,
        bash_command_is_safe_deprecated,
    )
    stripped = strip_safe_heredoc_substitutions(command)
    if stripped is not None:
        # Heredocs were stripped; check the remainder
        remainder_result = bash_command_is_safe_deprecated(stripped)
        if remainder_result['behavior'] == 'ask':
            decision_reason = {
                'type': 'other',
                'reason': remainder_result.get('message', 'This command requires approval'),
            }
            return {
                'behavior': 'ask',
                'message': _create_permission_request_message('Bash', decision_reason),
                'decisionReason': decision_reason,
                'suggestions': [],
            }

    # Split the command into subcommands
    subcommands = _split_command(command)

    # Cap subcommands to prevent exponential blowup (CC-643)
    if len(subcommands) > MAX_SUBCOMMANDS_FOR_SECURITY_CHECK:
        decision_reason = {
            'type': 'other',
            'reason': 'This command requires approval',
        }
        return {
            'behavior': 'ask',
            'message': _create_permission_request_message('Bash', decision_reason),
            'decisionReason': decision_reason,
            'suggestions': [],
        }

    # Check if any subcommand is a `cd` (needed for path validation context)
    compound_command_has_cd = any(
        sub.strip() == 'cd' or sub.strip().startswith('cd ') or sub.strip().startswith('cd\t')
        for sub in subcommands
    )

    # If there is only one command, no need to process subcommands
    if len(subcommands) == 1:
        return await check_command_and_suggest_rules(
            command,
            tool_permission_context,
            compound_command_has_cd=compound_command_has_cd,
        )

    # Process each subcommand
    results = []
    for sub in subcommands:
        result = await check_command_and_suggest_rules(
            sub,
            tool_permission_context,
            compound_command_has_cd=compound_command_has_cd,
        )
        results.append(result)

        # Deny takes immediate priority
        if result['behavior'] == 'deny':
            return result

    # If any result is 'ask', return the first ask result
    # with combined suggestions (up to MAX_SUGGESTED_RULES_FOR_COMPOUND)
    ask_results = [r for r in results if r['behavior'] == 'ask']
    if ask_results:
        all_suggestions = []
        for r in ask_results:
            all_suggestions.extend(r.get('suggestions', []))
        # Cap suggestions
        combined_suggestions = all_suggestions[:MAX_SUGGESTED_RULES_FOR_COMPOUND]
        result = ask_results[0].copy()
        result['suggestions'] = combined_suggestions
        return result

    # All passthrough or allow — if any is passthrough, return passthrough
    passthrough_results = [r for r in results if r['behavior'] == 'passthrough']
    if passthrough_results:
        all_suggestions = []
        for r in passthrough_results:
            all_suggestions.extend(r.get('suggestions', []))
        combined_suggestions = all_suggestions[:MAX_SUGGESTED_RULES_FOR_COMPOUND]
        result = passthrough_results[0].copy()
        result['suggestions'] = combined_suggestions
        return result

    # All allow
    return {
        'behavior': 'allow',
        'updatedInput': input_data,
        'decisionReason': {
            'type': 'other',
            'reason': 'All subcommands are allowed',
        },
    }


# ---------------------------------------------------------------------------
# Aliases matching TS exports
# ---------------------------------------------------------------------------

# match_wildcard_pattern and bash_permission_rule are already defined above
# as the primary implementations

# Permission rule extraction prefix
permission_rule_extract_prefix = permission_rule_extract_prefix


def strip_wrappers_from_argv(argv: List[str]) -> List[str]:
    """
    Argv-level counterpart to strip_safe_wrappers. Strips the same wrapper
    commands (timeout, time, nice, nohup) from AST-derived argv.
    
    KEEP IN SYNC with SAFE_WRAPPER_PATTERNS above.
    """
    a = list(argv)
    TIMEOUT_FLAG_VALUE_RE = re.compile(r'^[A-Za-z0-9_.+-]+$')

    while True:
        if not a:
            return a
        if a[0] in ('time', 'nohup'):
            a = a[2:] if (len(a) > 1 and a[1] == '--') else a[1:]
        elif a[0] == 'timeout':
            # Skip timeout flags
            i = 1
            while i < len(a):
                arg = a[i]
                next_arg = a[i + 1] if i + 1 < len(a) else None
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
                    return a  # Unknown flag, bail
                elif arg == '-v':
                    i += 1
                elif arg in ('-k', '-s') and next_arg and TIMEOUT_FLAG_VALUE_RE.match(next_arg):
                    i += 2
                elif re.match(r'^-[ks][A-Za-z0-9_.+-]+$', arg):
                    i += 1
                elif arg.startswith('-'):
                    return a  # Unknown flag, bail
                else:
                    break
            # Check duration token
            if i >= len(a) or not re.match(r'^\d+(?:\.\d+)?[smhd]?$', a[i]):
                return a
            a = a[i + 1:]
        elif a[0] == 'nice' and len(a) > 2 and a[1] == '-n' and re.match(r'^-?\d+$', a[2]):
            a = a[4:] if (len(a) > 3 and a[3] == '--') else a[3:]
        else:
            return a
