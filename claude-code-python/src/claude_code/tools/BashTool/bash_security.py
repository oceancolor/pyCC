"""
bash_security.py - Python port of bashSecurity.ts

Legacy regex/shell-quote security validation for bash commands.
Only used when tree-sitter AST parsing is unavailable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Set, Dict, Any

# ---------------------------------------------------------------------------
# Type stubs for external modules (soft imports)
# ---------------------------------------------------------------------------
try:
    from ..permissions.PermissionResult import PermissionResult  # type: ignore
except ImportError:
    # Minimal fallback dataclass so the module is self-contained
    @dataclass
    class PermissionResult:  # type: ignore[no-redef]
        behavior: str  # 'allow' | 'ask' | 'deny' | 'passthrough'
        message: str = ""
        updated_input: Optional[Dict[str, Any]] = None
        decision_reason: Optional[Dict[str, Any]] = None
        is_bash_security_check_for_misparsing: bool = False

try:
    from ...utils.bash.heredoc import extract_heredocs  # type: ignore
except ImportError:
    def extract_heredocs(command: str, *, quoted_only: bool = False):  # type: ignore
        class _R:
            processed_command = command
        return _R()

try:
    from ...utils.bash.shellQuote import (  # type: ignore
        has_malformed_tokens,
        has_shell_quote_single_quote_bug,
        try_parse_shell_command,
    )
except ImportError:
    def has_malformed_tokens(command: str, tokens) -> bool:  # type: ignore
        return False

    def has_shell_quote_single_quote_bug(command: str) -> bool:  # type: ignore
        return False

    def try_parse_shell_command(command: str):  # type: ignore
        class _R:
            success = False
            tokens = []
            error = "not implemented"
        return _R()

try:
    from ...utils.bash.ParsedCommand import ParsedCommand  # type: ignore
except ImportError:
    ParsedCommand = None  # type: ignore

try:
    from ...services.analytics.index import log_event  # type: ignore
except ImportError:
    def log_event(name: str, data: dict) -> None:  # type: ignore
        pass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEREDOC_IN_SUBSTITUTION = re.compile(r'\$\(.*<<')

COMMAND_SUBSTITUTION_PATTERNS = [
    (re.compile(r'<\('), 'process substitution <()'),
    (re.compile(r'>\('), 'process substitution >()'),
    (re.compile(r'=\('), 'Zsh process substitution =()'),
    (re.compile(r'(?:^|[\s;&|])=[a-zA-Z_]'), 'Zsh equals expansion (=cmd)'),
    (re.compile(r'\$\('), '$() command substitution'),
    (re.compile(r'\$\{'), '${} parameter substitution'),
    (re.compile(r'\$\['), '$[] legacy arithmetic expansion'),
    (re.compile(r'~\['), 'Zsh-style parameter expansion'),
    (re.compile(r'\(e:'), 'Zsh-style glob qualifiers'),
    (re.compile(r'\(\+'), 'Zsh glob qualifier with command execution'),
    (re.compile(r'\}\s*always\s*\{'), 'Zsh always block (try/always construct)'),
    (re.compile(r'<#'), 'PowerShell comment syntax'),
]

ZSH_DANGEROUS_COMMANDS: Set[str] = {
    'zmodload', 'emulate', 'sysopen', 'sysread', 'syswrite', 'sysseek',
    'zpty', 'ztcp', 'zsocket', 'mapfile',
    'zf_rm', 'zf_mv', 'zf_ln', 'zf_chmod', 'zf_chown', 'zf_mkdir',
    'zf_rmdir', 'zf_chgrp',
}

BASH_SECURITY_CHECK_IDS: Dict[str, int] = {
    'INCOMPLETE_COMMANDS': 1,
    'JQ_SYSTEM_FUNCTION': 2,
    'JQ_FILE_ARGUMENTS': 3,
    'OBFUSCATED_FLAGS': 4,
    'SHELL_METACHARACTERS': 5,
    'DANGEROUS_VARIABLES': 6,
    'NEWLINES': 7,
    'DANGEROUS_PATTERNS_COMMAND_SUBSTITUTION': 8,
    'DANGEROUS_PATTERNS_INPUT_REDIRECTION': 9,
    'DANGEROUS_PATTERNS_OUTPUT_REDIRECTION': 10,
    'IFS_INJECTION': 11,
    'GIT_COMMIT_SUBSTITUTION': 12,
    'PROC_ENVIRON_ACCESS': 13,
    'MALFORMED_TOKEN_INJECTION': 14,
    'BACKSLASH_ESCAPED_WHITESPACE': 15,
    'BRACE_EXPANSION': 16,
    'CONTROL_CHARACTERS': 17,
    'UNICODE_WHITESPACE': 18,
    'MID_WORD_HASH': 19,
    'ZSH_DANGEROUS_COMMANDS': 20,
    'BACKSLASH_ESCAPED_OPERATORS': 21,
    'COMMENT_QUOTE_DESYNC': 22,
    'QUOTED_NEWLINE': 23,
}

SHELL_OPERATORS: Set[str] = {';', '|', '&', '<', '>'}

# Non-printable control characters (excluding \t=0x09, \n=0x0A, \r=0x0D)
CONTROL_CHAR_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')

UNICODE_WS_RE = re.compile(
    r'[\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000\uFEFF]'
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

@dataclass
class ValidationContext:
    original_command: str
    base_command: str
    unquoted_content: str        # withDoubleQuotes
    fully_unquoted_content: str  # stripSafeRedirections(fullyUnquoted)
    fully_unquoted_pre_strip: str
    unquoted_keep_quote_chars: str
    tree_sitter: Optional[Any] = None


@dataclass
class QuoteExtraction:
    with_double_quotes: str
    fully_unquoted: str
    unquoted_keep_quote_chars: str


def _make_passthrough(message: str = '') -> PermissionResult:
    return PermissionResult(behavior='passthrough', message=message)


def _make_ask(message: str, *, misparsing: bool = False) -> PermissionResult:
    r = PermissionResult(behavior='ask', message=message)
    r.is_bash_security_check_for_misparsing = misparsing
    return r


def _make_allow(command: str, reason: str) -> PermissionResult:
    return PermissionResult(
        behavior='allow',
        updated_input={'command': command},
        decision_reason={'type': 'other', 'reason': reason},
    )


def extract_quoted_content(command: str, is_jq: bool = False) -> QuoteExtraction:
    with_double_quotes = ''
    fully_unquoted = ''
    unquoted_keep_quote_chars = ''
    in_single_quote = False
    in_double_quote = False
    escaped = False

    for char in command:
        if escaped:
            escaped = False
            if not in_single_quote:
                with_double_quotes += char
            if not in_single_quote and not in_double_quote:
                fully_unquoted += char
                unquoted_keep_quote_chars += char
            continue

        if char == '\\' and not in_single_quote:
            escaped = True
            if not in_single_quote:
                with_double_quotes += char
            if not in_single_quote and not in_double_quote:
                fully_unquoted += char
                unquoted_keep_quote_chars += char
            continue

        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            unquoted_keep_quote_chars += char
            continue

        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            unquoted_keep_quote_chars += char
            if not is_jq:
                continue

        if not in_single_quote:
            with_double_quotes += char
        if not in_single_quote and not in_double_quote:
            fully_unquoted += char
            unquoted_keep_quote_chars += char

    return QuoteExtraction(
        with_double_quotes=with_double_quotes,
        fully_unquoted=fully_unquoted,
        unquoted_keep_quote_chars=unquoted_keep_quote_chars,
    )


def strip_safe_redirections(content: str) -> str:
    content = re.sub(r'\s+2\s*>&\s*1(?=\s|$)', '', content)
    content = re.sub(r'[012]?\s*>\s*/dev/null(?=\s|$)', '', content)
    content = re.sub(r'\s*<\s*/dev/null(?=\s|$)', '', content)
    return content


def has_unescaped_char(content: str, char: str) -> bool:
    if len(char) != 1:
        raise ValueError('has_unescaped_char only works with single characters')
    i = 0
    while i < len(content):
        if content[i] == '\\' and i + 1 < len(content):
            i += 2
            continue
        if content[i] == char:
            return True
        i += 1
    return False


# ---------------------------------------------------------------------------
# Heredoc helpers
# ---------------------------------------------------------------------------

def _is_safe_heredoc(command: str) -> bool:
    """Check whether command contains only safe $(cat <<'DELIM'...DELIM) heredocs."""
    if not HEREDOC_IN_SUBSTITUTION.search(command):
        return False

    heredoc_pattern = re.compile(
        r"\$\(cat[ \t]*<<(-?)[ \t]*(?:'+([A-Za-z_]\w*)'+|\\([A-Za-z_]\w*))"
    )

    class HeredocMatch:
        def __init__(self, start, operator_end, delimiter, is_dash):
            self.start = start
            self.operator_end = operator_end
            self.delimiter = delimiter
            self.is_dash = is_dash

    safe_heredocs = []
    for m in heredoc_pattern.finditer(command):
        delimiter = m.group(2) or m.group(3)
        if delimiter:
            safe_heredocs.append(HeredocMatch(
                start=m.start(),
                operator_end=m.end(),
                delimiter=delimiter,
                is_dash=m.group(1) == '-',
            ))

    if not safe_heredocs:
        return False

    class Verified:
        def __init__(self, start, end):
            self.start = start
            self.end = end

    verified = []
    for hm in safe_heredocs:
        after_operator = command[hm.operator_end:]
        open_line_end = after_operator.find('\n')
        if open_line_end == -1:
            return False
        open_line_tail = after_operator[:open_line_end]
        if not re.match(r'^[ \t]*$', open_line_tail):
            return False

        body_start = hm.operator_end + open_line_end + 1
        body = command[body_start:]
        body_lines = body.split('\n')

        closing_line_idx = -1
        close_paren_line_idx = -1
        close_paren_col_idx = -1

        for i, raw_line in enumerate(body_lines):
            line = re.sub(r'^\t*', '', raw_line) if hm.is_dash else raw_line

            if line == hm.delimiter:
                closing_line_idx = i
                if i + 1 >= len(body_lines):
                    return False
                next_line = body_lines[i + 1]
                paren_match = re.match(r'^([ \t]*)\)', next_line)
                if not paren_match:
                    return False
                close_paren_line_idx = i + 1
                close_paren_col_idx = len(paren_match.group(1))
                break

            if line.startswith(hm.delimiter):
                after_delim = line[len(hm.delimiter):]
                paren_match = re.match(r'^([ \t]*)\)', after_delim)
                if paren_match:
                    closing_line_idx = i
                    close_paren_line_idx = i
                    tab_prefix = re.match(r'^\t*', raw_line).group(0) if hm.is_dash else ''
                    close_paren_col_idx = (
                        len(tab_prefix) + len(hm.delimiter) + len(paren_match.group(1))
                    )
                    break
                if re.match(r'^[)}`|&;(<>]', after_delim):
                    return False

        if closing_line_idx == -1:
            return False

        end_pos = body_start
        for i in range(close_paren_line_idx):
            end_pos += len(body_lines[i]) + 1
        end_pos += close_paren_col_idx + 1

        verified.append(Verified(hm.start, end_pos))

    # Check for nested matches
    for outer in verified:
        for inner in verified:
            if inner is outer:
                continue
            if outer.start < inner.start < outer.end:
                return False

    # Strip verified heredocs in reverse
    sorted_verified = sorted(verified, key=lambda v: v.start, reverse=True)
    remaining = command
    for v in sorted_verified:
        remaining = remaining[:v.start] + remaining[v.end:]

    trimmed_remaining = remaining.strip()
    if trimmed_remaining:
        first_heredoc_start = min(v.start for v in verified)
        prefix = command[:first_heredoc_start]
        if not prefix.strip():
            return False

    if not re.match(r'^[a-zA-Z0-9 \t"\'.\-/_@=,:+~]*$', remaining):
        return False

    if bash_command_is_safe_deprecated(remaining).behavior != 'passthrough':
        return False

    return True


def strip_safe_heredoc_substitutions(command: str) -> Optional[str]:
    """Strip safe $(cat <<'DELIM'...DELIM) heredocs. Returns modified command or None."""
    if not HEREDOC_IN_SUBSTITUTION.search(command):
        return None

    heredoc_pattern = re.compile(
        r"\$\(cat[ \t]*<<(-?)[ \t]*(?:'+([A-Za-z_]\w*)'+|\\([A-Za-z_]\w*))"
    )

    result = command
    found = False
    ranges = []

    for m in heredoc_pattern.finditer(command):
        if m.start() > 0 and command[m.start() - 1] == '\\':
            continue
        delimiter = m.group(2) or m.group(3)
        if not delimiter:
            continue
        is_dash = m.group(1) == '-'
        operator_end = m.end()

        after_operator = command[operator_end:]
        open_line_end = after_operator.find('\n')
        if open_line_end == -1:
            continue
        if not re.match(r'^[ \t]*$', after_operator[:open_line_end]):
            continue

        body_start = operator_end + open_line_end + 1
        body_lines = command[body_start:].split('\n')
        for i, raw_line in enumerate(body_lines):
            line = re.sub(r'^\t*', '', raw_line) if is_dash else raw_line
            if line.startswith(delimiter):
                after = line[len(delimiter):]
                close_pos = -1
                if re.match(r'^[ \t]*\)', after):
                    line_start = body_start + len('\n'.join(body_lines[:i])) + (1 if i > 0 else 0)
                    close_pos = command.find(')', line_start)
                elif after == '':
                    if i + 1 < len(body_lines):
                        next_line = body_lines[i + 1]
                        if re.match(r'^[ \t]*\)', next_line):
                            next_line_start = (
                                body_start + len('\n'.join(body_lines[:i + 1])) + 1
                            )
                            close_pos = command.find(')', next_line_start)
                if close_pos != -1:
                    ranges.append({'start': m.start(), 'end': close_pos + 1})
                    found = True
                break

    if not found:
        return None

    for r in reversed(ranges):
        result = result[:r['start']] + result[r['end']:]
    return result


def has_safe_heredoc_substitution(command: str) -> bool:
    return strip_safe_heredoc_substitutions(command) is not None


# ---------------------------------------------------------------------------
# Individual validators
# ---------------------------------------------------------------------------

def _validate_empty(ctx: ValidationContext) -> PermissionResult:
    if not ctx.original_command.strip():
        return _make_allow(ctx.original_command, 'Empty command is safe')
    return _make_passthrough('Command is not empty')


def _validate_incomplete_commands(ctx: ValidationContext) -> PermissionResult:
    cmd = ctx.original_command
    trimmed = cmd.strip()

    if re.match(r'^\s*\t', cmd):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['INCOMPLETE_COMMANDS'], 'subId': 1
        })
        return _make_ask('Command appears to be an incomplete fragment (starts with tab)')

    if trimmed.startswith('-'):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['INCOMPLETE_COMMANDS'], 'subId': 2
        })
        return _make_ask('Command appears to be an incomplete fragment (starts with flags)')

    if re.match(r'^\s*(&&|\|\||;|>>?|<)', cmd):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['INCOMPLETE_COMMANDS'], 'subId': 3
        })
        return _make_ask('Command appears to be a continuation line (starts with operator)')

    return _make_passthrough('Command appears complete')


def _validate_safe_command_substitution(ctx: ValidationContext) -> PermissionResult:
    if not HEREDOC_IN_SUBSTITUTION.search(ctx.original_command):
        return _make_passthrough('No heredoc in substitution')

    if _is_safe_heredoc(ctx.original_command):
        return _make_allow(
            ctx.original_command,
            'Safe command substitution: cat with quoted/escaped heredoc delimiter',
        )

    return _make_passthrough('Command substitution needs validation')


def _validate_git_commit(ctx: ValidationContext) -> PermissionResult:
    cmd = ctx.original_command
    if ctx.base_command != 'git' or not re.match(r'^git\s+commit\s+', cmd):
        return _make_passthrough('Not a git commit')

    if '\\' in cmd:
        return _make_passthrough('Git commit contains backslash, needs full validation')

    message_match = re.match(
        r'^git[ \t]+commit[ \t]+[^;&|`$<>()\n\r]*?-m[ \t]+(["\'"])([\s\S]*?)\1(.*)$',
        cmd,
    )

    if message_match:
        quote = message_match.group(1)
        message_content = message_match.group(2)
        remainder = message_match.group(3)

        if quote == '"' and message_content and re.search(r'\$\(|`|\$\{', message_content):
            log_event('tengu_bash_security_check_triggered', {
                'checkId': BASH_SECURITY_CHECK_IDS['GIT_COMMIT_SUBSTITUTION'], 'subId': 1
            })
            return _make_ask('Git commit message contains command substitution patterns')

        if remainder and re.search(r'[;|&()`]|\$\(|\$\{', remainder):
            return _make_passthrough('Git commit remainder contains shell metacharacters')

        if remainder:
            unquoted = ''
            in_sq = False
            in_dq = False
            for c in remainder:
                if c == "'" and not in_dq:
                    in_sq = not in_sq
                    continue
                if c == '"' and not in_sq:
                    in_dq = not in_dq
                    continue
                if not in_sq and not in_dq:
                    unquoted += c
            if re.search(r'[<>]', unquoted):
                return _make_passthrough('Git commit remainder contains unquoted redirect operator')

        if message_content and message_content.startswith('-'):
            log_event('tengu_bash_security_check_triggered', {
                'checkId': BASH_SECURITY_CHECK_IDS['OBFUSCATED_FLAGS'], 'subId': 5
            })
            return _make_ask('Command contains quoted characters in flag names')

        return _make_allow(cmd, 'Git commit with simple quoted message is allowed')

    return _make_passthrough('Git commit needs validation')


def _validate_jq_command(ctx: ValidationContext) -> PermissionResult:
    if ctx.base_command != 'jq':
        return _make_passthrough('Not jq')

    if re.search(r'\bsystem\s*\(', ctx.original_command):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['JQ_SYSTEM_FUNCTION'], 'subId': 1
        })
        return _make_ask('jq command contains system() function which executes arbitrary commands')

    after_jq = ctx.original_command[3:].strip()
    if re.search(
        r'(?:^|\s)(?:-f\b|--from-file|--rawfile|--slurpfile|-L\b|--library-path)',
        after_jq,
    ):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['JQ_FILE_ARGUMENTS'], 'subId': 1
        })
        return _make_ask(
            'jq command contains dangerous flags that could execute code or read arbitrary files'
        )

    return _make_passthrough('jq command is safe')


def _validate_shell_metacharacters(ctx: ValidationContext) -> PermissionResult:
    content = ctx.unquoted_content
    message = 'Command contains shell metacharacters (;, |, or &) in arguments'

    if re.search(r'(?:^|\s)["\'"][^"\']*[;&][^"\']*["\'"](?:\s|$)', content):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['SHELL_METACHARACTERS'], 'subId': 1
        })
        return _make_ask(message)

    glob_patterns = [
        re.compile(r'-name\s+["\'"][^"\']*[;|&][^"\']*["\'"]'),
        re.compile(r'-path\s+["\'"][^"\']*[;|&][^"\']*["\'"]'),
        re.compile(r'-iname\s+["\'"][^"\']*[;|&][^"\']*["\'"]'),
    ]
    if any(p.search(content) for p in glob_patterns):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['SHELL_METACHARACTERS'], 'subId': 2
        })
        return _make_ask(message)

    if re.search(r'-regex\s+["\'"][^"\']*[;&][^"\']*["\'"]', content):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['SHELL_METACHARACTERS'], 'subId': 3
        })
        return _make_ask(message)

    return _make_passthrough('No metacharacters')


def _validate_dangerous_variables(ctx: ValidationContext) -> PermissionResult:
    content = ctx.fully_unquoted_content
    if re.search(r'[<>|]\s*\$[A-Za-z_]', content) or re.search(
        r'\$[A-Za-z_][A-Za-z0-9_]*\s*[|<>]', content
    ):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['DANGEROUS_VARIABLES'], 'subId': 1
        })
        return _make_ask(
            'Command contains variables in dangerous contexts (redirections or pipes)'
        )
    return _make_passthrough('No dangerous variables')


def _validate_dangerous_patterns(ctx: ValidationContext) -> PermissionResult:
    content = ctx.unquoted_content
    if has_unescaped_char(content, '`'):
        return _make_ask('Command contains backticks (`) for command substitution')

    for pattern, msg in COMMAND_SUBSTITUTION_PATTERNS:
        if pattern.search(content):
            log_event('tengu_bash_security_check_triggered', {
                'checkId': BASH_SECURITY_CHECK_IDS['DANGEROUS_PATTERNS_COMMAND_SUBSTITUTION'],
                'subId': 1,
            })
            return _make_ask(f'Command contains {msg}')

    return _make_passthrough('No dangerous patterns')


def _validate_redirections(ctx: ValidationContext) -> PermissionResult:
    content = ctx.fully_unquoted_content
    if '<' in content:
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['DANGEROUS_PATTERNS_INPUT_REDIRECTION'],
            'subId': 1,
        })
        return _make_ask(
            'Command contains input redirection (<) which could read sensitive files'
        )

    if '>' in content:
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['DANGEROUS_PATTERNS_OUTPUT_REDIRECTION'],
            'subId': 1,
        })
        return _make_ask(
            'Command contains output redirection (>) which could write to arbitrary files'
        )

    return _make_passthrough('No redirections')


def _validate_newlines(ctx: ValidationContext) -> PermissionResult:
    content = ctx.fully_unquoted_pre_strip
    if not re.search(r'[\n\r]', content):
        return _make_passthrough('No newlines')

    if re.search(r'(?<![\s]\\)[\n\r]\s*\S', content):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['NEWLINES'], 'subId': 1
        })
        return _make_ask('Command contains newlines that could separate multiple commands')

    return _make_passthrough('Newlines appear to be within data')


def _validate_carriage_return(ctx: ValidationContext) -> PermissionResult:
    cmd = ctx.original_command
    if '\r' not in cmd:
        return _make_passthrough('No carriage return')

    in_single_quote = False
    in_double_quote = False
    escaped = False

    for c in cmd:
        if escaped:
            escaped = False
            continue
        if c == '\\' and not in_single_quote:
            escaped = True
            continue
        if c == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            continue
        if c == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            continue
        if c == '\r' and not in_double_quote:
            log_event('tengu_bash_security_check_triggered', {
                'checkId': BASH_SECURITY_CHECK_IDS['NEWLINES'], 'subId': 2
            })
            return _make_ask(
                'Command contains carriage return (\\r) which shell-quote and bash tokenize differently'
            )

    return _make_passthrough('CR only inside double quotes')


def _validate_ifs_injection(ctx: ValidationContext) -> PermissionResult:
    if re.search(r'\$IFS|\$\{[^}]*IFS', ctx.original_command):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['IFS_INJECTION'], 'subId': 1
        })
        return _make_ask(
            'Command contains IFS variable usage which could bypass security validation'
        )
    return _make_passthrough('No IFS injection detected')


def _validate_proc_environ_access(ctx: ValidationContext) -> PermissionResult:
    if re.search(r'/proc/.*/environ', ctx.original_command):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['PROC_ENVIRON_ACCESS'], 'subId': 1
        })
        return _make_ask(
            'Command accesses /proc/*/environ which could expose sensitive environment variables'
        )
    return _make_passthrough('No /proc/environ access detected')


def _validate_malformed_token_injection(ctx: ValidationContext) -> PermissionResult:
    parse_result = try_parse_shell_command(ctx.original_command)
    if not parse_result.success:
        return _make_passthrough('Parse failed, handled elsewhere')

    tokens = parse_result.tokens
    has_separator = any(
        isinstance(entry, dict) and entry.get('op') in (';', '&&', '||')
        for entry in tokens
    )
    if not has_separator:
        return _make_passthrough('No command separators')

    if has_malformed_tokens(ctx.original_command, tokens):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['MALFORMED_TOKEN_INJECTION'], 'subId': 1
        })
        return _make_ask(
            'Command contains ambiguous syntax with command separators that could be misinterpreted'
        )

    return _make_passthrough('No malformed token injection detected')


def _validate_obfuscated_flags(ctx: ValidationContext) -> PermissionResult:
    cmd = ctx.original_command
    has_shell_operators = bool(re.search(r'[|&;]', cmd))
    if ctx.base_command == 'echo' and not has_shell_operators:
        return _make_passthrough('echo command is safe and has no dangerous flags')

    # 1. ANSI-C quoting
    if re.search(r"\$'[^']*'", cmd):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['OBFUSCATED_FLAGS'], 'subId': 5
        })
        return _make_ask('Command contains ANSI-C quoting which can hide characters')

    # 2. Locale quoting
    if re.search(r'\$"[^"]*"', cmd):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['OBFUSCATED_FLAGS'], 'subId': 6
        })
        return _make_ask('Command contains locale quoting which can hide characters')

    # 3. Empty special quotes before dash
    if re.search(r'\$[\'\"]{2}\s*-', cmd):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['OBFUSCATED_FLAGS'], 'subId': 9
        })
        return _make_ask('Command contains empty special quotes before dash (potential bypass)')

    # 4. ANY sequence of empty quote pairs followed by dash
    if re.search(r"(?:^|\s)(?:''|\"\")+\s*-", cmd):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['OBFUSCATED_FLAGS'], 'subId': 7
        })
        return _make_ask('Command contains empty quotes before dash (potential bypass)')

    # 4b. Homogeneous empty pair adjacent to quoted dash
    if re.search(r'(?:""|\'\')+[\'"]-', cmd):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['OBFUSCATED_FLAGS'], 'subId': 10
        })
        return _make_ask(
            'Command contains empty quote pair adjacent to quoted dash (potential flag obfuscation)'
        )

    # 4c. 3+ consecutive quotes at word start
    if re.search(r"(?:^|\s)['\"{3,}]", cmd) or re.search(r"(?:^|\s)[\"']{3,}", cmd):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['OBFUSCATED_FLAGS'], 'subId': 11
        })
        return _make_ask(
            'Command contains consecutive quote characters at word start (potential obfuscation)'
        )

    # Character-by-character quote-aware scan for obfuscated flags
    in_single_quote = False
    in_double_quote = False
    escaped = False

    for i in range(len(cmd) - 1):
        current_char = cmd[i]
        next_char = cmd[i + 1]

        if escaped:
            escaped = False
            continue

        if current_char == '\\' and not in_single_quote:
            escaped = True
            continue

        if current_char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            continue

        if current_char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            continue

        if in_single_quote or in_double_quote:
            continue

        # Check: whitespace followed by quote that contains dash
        if re.match(r'\s', current_char) and re.match(r'[\'"`]', next_char):
            quote_char = next_char
            j = i + 2
            inside_quote = ''
            while j < len(cmd) and cmd[j] != quote_char:
                inside_quote += cmd[j]
                j += 1

            if j < len(cmd) and cmd[j] == quote_char:
                char_after_quote = cmd[j + 1] if j + 1 < len(cmd) else None
                FLAG_CONTINUATION_CHARS = re.compile(r'[a-zA-Z0-9\\${`-]')
                has_flag_chars_inside = bool(re.match(r'^-+[a-zA-Z0-9$`]', inside_quote))
                has_flag_chars_continuing = (
                    bool(re.match(r'^-+$', inside_quote)) and
                    char_after_quote is not None and
                    FLAG_CONTINUATION_CHARS.match(char_after_quote) is not None
                )

                # Check adjacent quote chaining
                has_flag_chars_in_next_quote = False
                if (inside_quote == '' or re.match(r'^-+$', inside_quote)) and \
                        char_after_quote is not None and re.match(r'[\'"`]', char_after_quote):
                    pos = j + 1
                    combined_content = inside_quote
                    while pos < len(cmd) and re.match(r'[\'"`]', cmd[pos]):
                        seg_quote = cmd[pos]
                        end = pos + 1
                        while end < len(cmd) and cmd[end] != seg_quote:
                            end += 1
                        segment = cmd[pos + 1:end]
                        combined_content += segment
                        if re.match(r'^-+[a-zA-Z0-9$`]', combined_content):
                            has_flag_chars_in_next_quote = True
                            break
                        prior_content = combined_content[:-len(segment)] if segment else combined_content
                        if re.match(r'^-+$', prior_content) and re.search(r'[a-zA-Z0-9$`]', segment):
                            has_flag_chars_in_next_quote = True
                            break
                        if end >= len(cmd):
                            break
                        pos = end + 1
                    if not has_flag_chars_in_next_quote and pos < len(cmd) and \
                            FLAG_CONTINUATION_CHARS.match(cmd[pos]):
                        if re.match(r'^-+$', combined_content) or combined_content == '':
                            nc = cmd[pos]
                            if nc == '-':
                                has_flag_chars_in_next_quote = True
                            elif re.match(r'[a-zA-Z0-9\\${`]', nc) and combined_content:
                                has_flag_chars_in_next_quote = True
                        elif re.match(r'^-', combined_content):
                            has_flag_chars_in_next_quote = True

                if has_flag_chars_inside or has_flag_chars_continuing or has_flag_chars_in_next_quote:
                    log_event('tengu_bash_security_check_triggered', {
                        'checkId': BASH_SECURITY_CHECK_IDS['OBFUSCATED_FLAGS'], 'subId': 4
                    })
                    return _make_ask('Command contains quoted characters in flag names')

        # Check: whitespace followed by dash (flag start)
        if re.match(r'\s', current_char) and next_char == '-':
            j = i + 1
            flag_content = ''
            while j < len(cmd):
                flag_char = cmd[j]
                if re.match(r'[\s=]', flag_char):
                    break
                if re.match(r'[\'"`]', flag_char):
                    if ctx.base_command == 'cut' and flag_content == '-d' and re.match(r'[\'"`]', flag_char):
                        break
                    if j + 1 < len(cmd):
                        next_flag = cmd[j + 1]
                        if not re.match(r'[a-zA-Z0-9_\'"-]', next_flag):
                            break
                flag_content += flag_char
                j += 1
            if '"' in flag_content or "'" in flag_content:
                log_event('tengu_bash_security_check_triggered', {
                    'checkId': BASH_SECURITY_CHECK_IDS['OBFUSCATED_FLAGS'], 'subId': 1
                })
                return _make_ask('Command contains quoted characters in flag names')

    # Flags starting with quotes
    if re.search(r"\s['\"`]-", ctx.fully_unquoted_content):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['OBFUSCATED_FLAGS'], 'subId': 2
        })
        return _make_ask('Command contains quoted characters in flag names')

    if re.search(r'[\'"`]{2}-', ctx.fully_unquoted_content):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['OBFUSCATED_FLAGS'], 'subId': 3
        })
        return _make_ask('Command contains quoted characters in flag names')

    return _make_passthrough('No obfuscated flags detected')


def _has_backslash_escaped_whitespace(command: str) -> bool:
    in_single_quote = False
    in_double_quote = False
    i = 0
    while i < len(command):
        char = command[i]
        if char == '\\' and not in_single_quote:
            if not in_double_quote:
                if i + 1 < len(command) and command[i + 1] in (' ', '\t'):
                    return True
            i += 2
            continue
        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        i += 1
    return False


def _validate_backslash_escaped_whitespace(ctx: ValidationContext) -> PermissionResult:
    if _has_backslash_escaped_whitespace(ctx.original_command):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['BACKSLASH_ESCAPED_WHITESPACE']
        })
        return _make_ask(
            'Command contains backslash-escaped whitespace that could alter command parsing'
        )
    return _make_passthrough('No backslash-escaped whitespace')


def _has_backslash_escaped_operator(command: str) -> bool:
    in_single_quote = False
    in_double_quote = False
    i = 0
    while i < len(command):
        char = command[i]
        if char == '\\' and not in_single_quote:
            if not in_double_quote:
                if i + 1 < len(command) and command[i + 1] in SHELL_OPERATORS:
                    return True
            i += 2
            continue
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        i += 1
    return False


def _validate_backslash_escaped_operators(ctx: ValidationContext) -> PermissionResult:
    if ctx.tree_sitter and not ctx.tree_sitter.has_actual_operator_nodes:
        return _make_passthrough('No operator nodes in AST')

    if _has_backslash_escaped_operator(ctx.original_command):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['BACKSLASH_ESCAPED_OPERATORS']
        })
        return _make_ask(
            'Command contains a backslash before a shell operator (;, |, &, <, >) which can hide command structure'
        )
    return _make_passthrough('No backslash-escaped operators')


def _is_escaped_at_position(content: str, pos: int) -> bool:
    backslash_count = 0
    i = pos - 1
    while i >= 0 and content[i] == '\\':
        backslash_count += 1
        i -= 1
    return backslash_count % 2 == 1


def _validate_brace_expansion(ctx: ValidationContext) -> PermissionResult:
    content = ctx.fully_unquoted_pre_strip

    unescaped_open = sum(
        1 for i, c in enumerate(content)
        if c == '{' and not _is_escaped_at_position(content, i)
    )
    unescaped_close = sum(
        1 for i, c in enumerate(content)
        if c == '}' and not _is_escaped_at_position(content, i)
    )

    if unescaped_open > 0 and unescaped_close > unescaped_open:
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['BRACE_EXPANSION'], 'subId': 2
        })
        return _make_ask(
            'Command has excess closing braces after quote stripping, indicating possible brace expansion obfuscation'
        )

    if unescaped_open > 0:
        orig = ctx.original_command
        if re.search(r'[\'"][{}][\'"]', orig):
            log_event('tengu_bash_security_check_triggered', {
                'checkId': BASH_SECURITY_CHECK_IDS['BRACE_EXPANSION'], 'subId': 3
            })
            return _make_ask(
                'Command contains quoted brace character inside brace context (potential brace expansion obfuscation)'
            )

    i = 0
    while i < len(content):
        if content[i] != '{':
            i += 1
            continue
        if _is_escaped_at_position(content, i):
            i += 1
            continue

        depth = 1
        matching_close = -1
        j = i + 1
        while j < len(content):
            ch = content[j]
            if ch == '{' and not _is_escaped_at_position(content, j):
                depth += 1
            elif ch == '}' and not _is_escaped_at_position(content, j):
                depth -= 1
                if depth == 0:
                    matching_close = j
                    break
            j += 1

        if matching_close == -1:
            i += 1
            continue

        inner_depth = 0
        for k in range(i + 1, matching_close):
            ch = content[k]
            if ch == '{' and not _is_escaped_at_position(content, k):
                inner_depth += 1
            elif ch == '}' and not _is_escaped_at_position(content, k):
                inner_depth -= 1
            elif inner_depth == 0:
                if ch == ',' or (
                    ch == '.' and k + 1 < matching_close and content[k + 1] == '.'
                ):
                    log_event('tengu_bash_security_check_triggered', {
                        'checkId': BASH_SECURITY_CHECK_IDS['BRACE_EXPANSION'], 'subId': 1
                    })
                    return _make_ask(
                        'Command contains brace expansion that could alter command parsing'
                    )
        i += 1

    return _make_passthrough('No brace expansion detected')


def _validate_unicode_whitespace(ctx: ValidationContext) -> PermissionResult:
    if UNICODE_WS_RE.search(ctx.original_command):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['UNICODE_WHITESPACE']
        })
        return _make_ask(
            'Command contains Unicode whitespace characters that could cause parsing inconsistencies'
        )
    return _make_passthrough('No Unicode whitespace')


def _validate_mid_word_hash(ctx: ValidationContext) -> PermissionResult:
    content = ctx.unquoted_keep_quote_chars
    joined = re.sub(
        r'\\+\n',
        lambda m: '\\' * ((len(m.group(0)) - 1 - 1)) if (len(m.group(0)) - 1) % 2 == 1 else m.group(0),
        content,
    )
    # Pattern: non-whitespace char immediately before #, not ${#
    pattern = re.compile(r'\S(?<!\$\{)#')
    if pattern.search(content) or pattern.search(joined):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['MID_WORD_HASH']
        })
        return _make_ask(
            'Command contains mid-word # which is parsed differently by shell-quote vs bash'
        )
    return _make_passthrough('No mid-word hash')


def _validate_comment_quote_desync(ctx: ValidationContext) -> PermissionResult:
    if ctx.tree_sitter:
        return _make_passthrough('Tree-sitter quote context is authoritative')

    cmd = ctx.original_command
    in_single_quote = False
    in_double_quote = False
    escaped = False

    for i, char in enumerate(cmd):
        if escaped:
            escaped = False
            continue
        if in_single_quote:
            if char == "'":
                in_single_quote = False
            continue
        if char == '\\':
            escaped = True
            continue
        if in_double_quote:
            if char == '"':
                in_double_quote = False
            continue
        if char == "'":
            in_single_quote = True
            continue
        if char == '"':
            in_double_quote = True
            continue
        if char == '#':
            line_end = cmd.find('\n', i)
            comment_text = cmd[i + 1:] if line_end == -1 else cmd[i + 1:line_end]
            if re.search(r'[\'"]', comment_text):
                log_event('tengu_bash_security_check_triggered', {
                    'checkId': BASH_SECURITY_CHECK_IDS['COMMENT_QUOTE_DESYNC']
                })
                return _make_ask(
                    'Command contains quote characters inside a # comment which can desync quote tracking'
                )
            if line_end == -1:
                break

    return _make_passthrough('No comment quote desync')


def _validate_quoted_newline(ctx: ValidationContext) -> PermissionResult:
    cmd = ctx.original_command
    if '\n' not in cmd or '#' not in cmd:
        return _make_passthrough('No newline or no hash')

    in_single_quote = False
    in_double_quote = False
    escaped = False

    for i, char in enumerate(cmd):
        if escaped:
            escaped = False
            continue
        if char == '\\' and not in_single_quote:
            escaped = True
            continue
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            continue
        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            continue
        if char == '\n' and (in_single_quote or in_double_quote):
            line_start = i + 1
            next_newline = cmd.find('\n', line_start)
            line_end = len(cmd) if next_newline == -1 else next_newline
            next_line = cmd[line_start:line_end]
            if next_line.strip().startswith('#'):
                log_event('tengu_bash_security_check_triggered', {
                    'checkId': BASH_SECURITY_CHECK_IDS['QUOTED_NEWLINE']
                })
                return _make_ask(
                    'Command contains a quoted newline followed by a #-prefixed line, '
                    'which can hide arguments from line-based permission checks'
                )

    return _make_passthrough('No quoted newline-hash pattern')


def _validate_zsh_dangerous_commands(ctx: ValidationContext) -> PermissionResult:
    ZSH_PRECOMMAND_MODIFIERS = {'command', 'builtin', 'noglob', 'nocorrect'}
    trimmed = ctx.original_command.strip()
    tokens = trimmed.split()
    base_cmd = ''
    for token in tokens:
        if re.match(r'^[A-Za-z_]\w*=', token):
            continue
        if token in ZSH_PRECOMMAND_MODIFIERS:
            continue
        base_cmd = token
        break

    if base_cmd in ZSH_DANGEROUS_COMMANDS:
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['ZSH_DANGEROUS_COMMANDS'], 'subId': 1
        })
        return _make_ask(
            f"Command uses Zsh-specific '{base_cmd}' which can bypass security checks"
        )

    if base_cmd == 'fc' and re.search(r'\s-\S*e', trimmed):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['ZSH_DANGEROUS_COMMANDS'], 'subId': 2
        })
        return _make_ask("Command uses 'fc -e' which can execute arbitrary commands via editor")

    return _make_passthrough('No Zsh dangerous commands')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def bash_command_is_safe_deprecated(command: str) -> PermissionResult:
    """
    Legacy regex/shell-quote security check.

    @deprecated Only used when tree-sitter is unavailable.
    The primary gate is parseForSecurity (ast.ts / ast.py).
    """
    if CONTROL_CHAR_RE.search(command):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['CONTROL_CHARACTERS']
        })
        r = _make_ask(
            'Command contains non-printable control characters that could be used to bypass security checks'
        )
        r.is_bash_security_check_for_misparsing = True
        return r

    if has_shell_quote_single_quote_bug(command):
        r = _make_ask(
            'Command contains single-quoted backslash pattern that could bypass security checks'
        )
        r.is_bash_security_check_for_misparsing = True
        return r

    heredoc_result = extract_heredocs(command, quoted_only=True)
    processed_command = heredoc_result.processed_command

    base_command = command.split(' ')[0] if command.strip() else ''
    extraction = extract_quoted_content(processed_command, base_command == 'jq')

    ctx = ValidationContext(
        original_command=command,
        base_command=base_command,
        unquoted_content=extraction.with_double_quotes,
        fully_unquoted_content=strip_safe_redirections(extraction.fully_unquoted),
        fully_unquoted_pre_strip=extraction.fully_unquoted,
        unquoted_keep_quote_chars=extraction.unquoted_keep_quote_chars,
    )

    early_validators = [
        _validate_empty,
        _validate_incomplete_commands,
        _validate_safe_command_substitution,
        _validate_git_commit,
    ]

    for validator in early_validators:
        result = validator(ctx)
        if result.behavior == 'allow':
            reason = ''
            if result.decision_reason and result.decision_reason.get('type') in ('other', 'safetyCheck'):
                reason = result.decision_reason.get('reason', 'Command allowed')
            return _make_passthrough(reason or 'Command allowed')
        if result.behavior != 'passthrough':
            if result.behavior == 'ask':
                result.is_bash_security_check_for_misparsing = True
            return result

    non_misparsing_validators = {_validate_newlines, _validate_redirections}

    validators = [
        _validate_jq_command,
        _validate_obfuscated_flags,
        _validate_shell_metacharacters,
        _validate_dangerous_variables,
        _validate_comment_quote_desync,
        _validate_quoted_newline,
        _validate_carriage_return,
        _validate_newlines,
        _validate_ifs_injection,
        _validate_proc_environ_access,
        _validate_dangerous_patterns,
        _validate_redirections,
        _validate_backslash_escaped_whitespace,
        _validate_backslash_escaped_operators,
        _validate_unicode_whitespace,
        _validate_mid_word_hash,
        _validate_brace_expansion,
        _validate_zsh_dangerous_commands,
        _validate_malformed_token_injection,
    ]

    deferred_non_misparsing: Optional[PermissionResult] = None
    for validator in validators:
        result = validator(ctx)
        if result.behavior == 'ask':
            if validator in non_misparsing_validators:
                if deferred_non_misparsing is None:
                    deferred_non_misparsing = result
                continue
            result.is_bash_security_check_for_misparsing = True
            return result

    if deferred_non_misparsing is not None:
        return deferred_non_misparsing

    return _make_passthrough('Command passed all security checks')


async def bash_command_is_safe_async_deprecated(
    command: str,
    on_divergence=None,
) -> PermissionResult:
    """
    Async version of bash_command_is_safe_deprecated.
    Uses tree-sitter when available, falls back to sync regex version.

    @deprecated Use parseForSecurity (ast) as primary gate.
    """
    if ParsedCommand is None:
        return bash_command_is_safe_deprecated(command)

    try:
        parsed = await ParsedCommand.parse(command)
        ts_analysis = parsed.get_tree_sitter_analysis() if parsed else None
    except Exception:
        ts_analysis = None

    if not ts_analysis:
        return bash_command_is_safe_deprecated(command)

    # Run with tree-sitter enriched context
    if CONTROL_CHAR_RE.search(command):
        log_event('tengu_bash_security_check_triggered', {
            'checkId': BASH_SECURITY_CHECK_IDS['CONTROL_CHARACTERS']
        })
        r = _make_ask(
            'Command contains non-printable control characters that could be used to bypass security checks'
        )
        r.is_bash_security_check_for_misparsing = True
        return r

    if has_shell_quote_single_quote_bug(command):
        r = _make_ask(
            'Command contains single-quoted backslash pattern that could bypass security checks'
        )
        r.is_bash_security_check_for_misparsing = True
        return r

    heredoc_result = extract_heredocs(command, quoted_only=True)
    processed_command = heredoc_result.processed_command

    base_command = command.split(' ')[0] if command.strip() else ''
    extraction = extract_quoted_content(processed_command, base_command == 'jq')

    # Build context with tree-sitter analysis
    ctx_sync = ValidationContext(
        original_command=command,
        base_command=base_command,
        unquoted_content=extraction.with_double_quotes,
        fully_unquoted_content=strip_safe_redirections(extraction.fully_unquoted),
        fully_unquoted_pre_strip=extraction.fully_unquoted,
        unquoted_keep_quote_chars=extraction.unquoted_keep_quote_chars,
        tree_sitter=ts_analysis,
    )

    # Check for divergence between tree-sitter and legacy for telemetry
    legacy_result = bash_command_is_safe_deprecated(command)

    # Build same context without tree-sitter for divergence comparison
    ctx_ts = ValidationContext(
        original_command=command,
        base_command=base_command,
        unquoted_content=extraction.with_double_quotes,
        fully_unquoted_content=strip_safe_redirections(extraction.fully_unquoted),
        fully_unquoted_pre_strip=extraction.fully_unquoted,
        unquoted_keep_quote_chars=extraction.unquoted_keep_quote_chars,
        tree_sitter=ts_analysis,
    )

    # Run full validator chain with tree-sitter context
    early_validators = [
        _validate_empty,
        _validate_incomplete_commands,
        _validate_safe_command_substitution,
        _validate_git_commit,
    ]
    for validator in early_validators:
        result = validator(ctx_ts)
        if result.behavior == 'allow':
            return _make_passthrough('Command allowed')
        if result.behavior != 'passthrough':
            if result.behavior == 'ask':
                result.is_bash_security_check_for_misparsing = True
            return result

    non_misparsing_validators = {_validate_newlines, _validate_redirections}
    validators = [
        _validate_jq_command,
        _validate_obfuscated_flags,
        _validate_shell_metacharacters,
        _validate_dangerous_variables,
        _validate_comment_quote_desync,
        _validate_quoted_newline,
        _validate_carriage_return,
        _validate_newlines,
        _validate_ifs_injection,
        _validate_proc_environ_access,
        _validate_dangerous_patterns,
        _validate_redirections,
        _validate_backslash_escaped_whitespace,
        _validate_backslash_escaped_operators,
        _validate_unicode_whitespace,
        _validate_mid_word_hash,
        _validate_brace_expansion,
        _validate_zsh_dangerous_commands,
        _validate_malformed_token_injection,
    ]

    deferred_non_misparsing: Optional[PermissionResult] = None
    ts_result: Optional[PermissionResult] = None
    for validator in validators:
        result = validator(ctx_ts)
        if result.behavior == 'ask':
            if validator in non_misparsing_validators:
                if deferred_non_misparsing is None:
                    deferred_non_misparsing = result
                continue
            result.is_bash_security_check_for_misparsing = True
            ts_result = result
            break

    if ts_result is None:
        ts_result = deferred_non_misparsing or _make_passthrough('Command passed all security checks')

    # Divergence telemetry
    if on_divergence and legacy_result.behavior != ts_result.behavior:
        on_divergence()

    return ts_result
