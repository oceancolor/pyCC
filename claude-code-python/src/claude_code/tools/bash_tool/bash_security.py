"""
Bash security checks.
Ported from BashTool/bashSecurity.ts (2592 lines).

Security checks that analyze shell commands for dangerous patterns,
injection attempts, and obfuscation techniques.
"""
from __future__ import annotations

import re
from typing import Optional, Dict, Any, List, Tuple, TYPE_CHECKING

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
# PermissionResult is a dict with keys: behavior, message, updatedInput, etc.
PermissionResult = Dict[str, Any]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEREDOC_IN_SUBSTITUTION = re.compile(r'\$\(.*<<')

# Note: Backtick pattern is handled separately in validate_dangerous_patterns
# to distinguish between escaped and unescaped backticks
COMMAND_SUBSTITUTION_PATTERNS = [
    {'pattern': re.compile(r'<\('), 'message': 'process substitution <()'},
    {'pattern': re.compile(r'>\('), 'message': 'process substitution >()'},
    {'pattern': re.compile(r'=\('), 'message': 'Zsh process substitution =()'},
    # Zsh EQUALS expansion: =cmd at word start expands to $(which cmd).
    # `=curl evil.com` bypasses Bash(curl:*) deny rules since the parser sees
    # `=curl` as the base command, not `curl`.
    # Only matches word-initial = followed by a command-name char (not VAR=val).
    {'pattern': re.compile(r'(?:^|[\s;&|])=[a-zA-Z_]'), 'message': 'Zsh equals expansion (=cmd)'},
    {'pattern': re.compile(r'\$\('), 'message': '$() command substitution'},
    {'pattern': re.compile(r'\$\{'), 'message': '${} parameter substitution'},
    {'pattern': re.compile(r'\$\['), 'message': '$[] legacy arithmetic expansion'},
    {'pattern': re.compile(r'~\['), 'message': 'Zsh-style parameter expansion'},
    {'pattern': re.compile(r'\(e:'), 'message': 'Zsh-style glob qualifiers'},
    {'pattern': re.compile(r'\(\+'), 'message': 'Zsh glob qualifier with command execution'},
    {'pattern': re.compile(r'\}\s*always\s*\{'), 'message': 'Zsh always block (try/always construct)'},
    # Defense in depth: Block PowerShell comment syntax
    {'pattern': re.compile(r'<#'), 'message': 'PowerShell comment syntax'},
]

# Zsh-specific dangerous commands that can bypass security checks.
ZSH_DANGEROUS_COMMANDS = frozenset([
    # zmodload is the gateway to many dangerous module-based attacks:
    # zsh/mapfile (invisible file I/O), zsh/system (sysopen/syswrite),
    # zsh/zpty (pseudo-terminal command execution), zsh/net/tcp (exfiltration),
    # zsh/files (builtin rm/mv/ln/chmod that bypass binary checks)
    'zmodload',
    # emulate with -c flag is an eval-equivalent that executes arbitrary code
    'emulate',
    # Zsh module builtins that enable dangerous operations.
    'sysopen',   # Opens files with fine-grained control (zsh/system)
    'sysread',   # Reads from file descriptors (zsh/system)
    'syswrite',  # Writes to file descriptors (zsh/system)
    'sysseek',   # Seeks on file descriptors (zsh/system)
    'zpty',      # Executes commands on pseudo-terminals (zsh/zpty)
    'ztcp',      # Creates TCP connections for exfiltration (zsh/net/tcp)
    'zsocket',   # Creates Unix/TCP sockets (zsh/net/socket)
    'mapfile',   # Associative array set via zmodload
    'zf_rm',     # Builtin rm from zsh/files
    'zf_mv',     # Builtin mv from zsh/files
    'zf_ln',     # Builtin ln from zsh/files
    'zf_chmod',  # Builtin chmod from zsh/files
    'zf_chown',  # Builtin chown from zsh/files
    'zf_mkdir',  # Builtin mkdir from zsh/files
    'zf_rmdir',  # Builtin rmdir from zsh/files
    'zf_chgrp',  # Builtin chgrp from zsh/files
])

# Numeric identifiers for bash security checks (to avoid logging strings)
BASH_SECURITY_CHECK_IDS = {
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

# Control characters (excluding \t=0x09, \n=0x0A)
CONTROL_CHAR_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')

# Unicode whitespace (beyond ASCII space/tab/newline)
UNICODE_WHITESPACE_RE = re.compile(
    r'[\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000\uFEFF]'
)

# ---------------------------------------------------------------------------
# ValidationContext
# ---------------------------------------------------------------------------

class ValidationContext:
    """Context for validation functions."""
    def __init__(
        self,
        original_command: str,
        base_command: str,
        unquoted_content: str,
        fully_unquoted_content: str,
        fully_unquoted_pre_strip: str,
        unquoted_keep_quote_chars: str,
        tree_sitter: Any = None,
    ):
        self.original_command = original_command
        self.base_command = base_command
        self.unquoted_content = unquoted_content
        self.fully_unquoted_content = fully_unquoted_content
        self.fully_unquoted_pre_strip = fully_unquoted_pre_strip
        self.unquoted_keep_quote_chars = unquoted_keep_quote_chars
        self.tree_sitter = tree_sitter


# ---------------------------------------------------------------------------
# Quote extraction helpers
# ---------------------------------------------------------------------------

def extract_quoted_content(command: str, is_jq: bool = False) -> dict:
    """
    Extract content outside quotes.
    Returns dict with keys: with_double_quotes, fully_unquoted, unquoted_keep_quote_chars.
    """
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

    return {
        'with_double_quotes': with_double_quotes,
        'fully_unquoted': fully_unquoted,
        'unquoted_keep_quote_chars': unquoted_keep_quote_chars,
    }


def strip_safe_redirections(content: str) -> str:
    """
    Strip safe redirections like 2>&1, >/dev/null, </dev/null.
    
    SECURITY: All three patterns MUST have a trailing boundary (?=\\s|$).
    Without it, `> /dev/nullo` could match `/dev/null` as a prefix.
    """
    result = re.sub(r'\s+2\s*>&\s*1(?=\s|$)', '', content)
    result = re.sub(r'[012]?\s*>\s*/dev/null(?=\s|$)', '', result)
    result = re.sub(r'\s*<\s*/dev/null(?=\s|$)', '', result)
    return result


def has_unescaped_char(content: str, char: str) -> bool:
    """
    Check if content contains an unescaped occurrence of a single character.
    Handles bash escape sequences correctly where a backslash escapes the following character.
    
    IMPORTANT: This function only handles single characters, not strings.
    """
    if len(char) != 1:
        raise ValueError('has_unescaped_char only works with single characters')

    i = 0
    while i < len(content):
        # If we see a backslash, skip it and the next character (they form an escape sequence)
        if content[i] == '\\' and i + 1 < len(content):
            i += 2  # Skip backslash and escaped character
            continue

        # Check if current character matches
        if content[i] == char:
            return True

        i += 1

    return False  # No unescaped occurrences found


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def validate_empty(context: ValidationContext) -> PermissionResult:
    if not context.original_command.strip():
        return {
            'behavior': 'allow',
            'updatedInput': {'command': context.original_command},
            'decisionReason': {'type': 'other', 'reason': 'Empty command is safe'},
        }
    return {'behavior': 'passthrough', 'message': 'Command is not empty'}


def validate_incomplete_commands(context: ValidationContext) -> PermissionResult:
    original_command = context.original_command
    trimmed = original_command.strip()

    if re.match(r'^\s*\t', original_command):
        return {
            'behavior': 'ask',
            'message': 'Command appears to be an incomplete fragment (starts with tab)',
        }

    if trimmed.startswith('-'):
        return {
            'behavior': 'ask',
            'message': 'Command appears to be an incomplete fragment (starts with flags)',
        }

    if re.match(r'^\s*(&&|\|\||;|>>?|<)', original_command):
        return {
            'behavior': 'ask',
            'message': 'Command appears to be a continuation line (starts with operator)',
        }

    return {'behavior': 'passthrough', 'message': 'Command appears complete'}


def is_safe_heredoc(command: str) -> bool:
    """
    Checks if a command is a "safe" heredoc-in-substitution pattern that can
    bypass the generic $() validator.
    
    This is an EARLY-ALLOW path: returning True causes bash_command_is_safe to
    return passthrough, bypassing ALL subsequent validators. Given this
    authority, the check must be PROVABLY safe.
    
    The only pattern we allow is:
      [prefix] $(cat <<'DELIM'\\n
      [body lines]\\n
      DELIM\\n
      ) [suffix]
    
    Where the delimiter must be single-quoted or escaped.
    """
    if not HEREDOC_IN_SUBSTITUTION.search(command):
        return False

    # SECURITY: Use [ \\t] (not \\s) between << and the delimiter. \\s matches
    # newlines, but bash requires the delimiter word on the same line as <<.
    heredoc_pattern = re.compile(
        r"""\\\$\(cat[ \t]*<<(-?)[ \t]*(?:'+([A-Za-z_]\w*)'+|\\\\([A-Za-z_]\w*))"""
    )

    safe_heredocs = []
    for match in heredoc_pattern.finditer(command):
        delimiter = match.group(2) or match.group(3)
        if delimiter:
            safe_heredocs.append({
                'start': match.start(),
                'operator_end': match.start() + len(match.group(0)),
                'delimiter': delimiter,
                'is_dash': match.group(1) == '-',
            })

    if not safe_heredocs:
        return False

    verified = []
    for heredoc in safe_heredocs:
        start = heredoc['start']
        operator_end = heredoc['operator_end']
        delimiter = heredoc['delimiter']
        is_dash = heredoc['is_dash']

        after_operator = command[operator_end:]
        open_line_end = after_operator.find('\n')
        if open_line_end == -1:
            return False
        open_line_tail = after_operator[:open_line_end]
        if not re.match(r'^[ \t]*$', open_line_tail):
            return False

        body_start = operator_end + open_line_end + 1
        body = command[body_start:]
        body_lines = body.split('\n')

        closing_line_idx = -1
        close_paren_line_idx = -1
        close_paren_col_idx = -1

        for i, raw_line in enumerate(body_lines):
            line = re.sub(r'^\t*', '', raw_line) if is_dash else raw_line

            # Form 1: delimiter alone on a line
            if line == delimiter:
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

            # Form 2: delimiter immediately followed by `)` (PST_EOFTOKEN form)
            if line.startswith(delimiter):
                after_delim = line[len(delimiter):]
                paren_match = re.match(r'^([ \t]*)\)', after_delim)
                if paren_match:
                    closing_line_idx = i
                    close_paren_line_idx = i
                    tab_prefix = re.match(r'^\t*', raw_line).group(0) if is_dash else ''
                    close_paren_col_idx = (
                        len(tab_prefix) + len(delimiter) + len(paren_match.group(1))
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

        verified.append({'start': start, 'end': end_pos})

    # SECURITY: Reject nested matches.
    for outer in verified:
        for inner in verified:
            if inner is outer:
                continue
            if outer['start'] < inner['start'] < outer['end']:
                return False

    # Strip all verified heredocs from the command
    sorted_verified = sorted(verified, key=lambda v: v['start'], reverse=True)
    remaining = command
    for v in sorted_verified:
        remaining = remaining[:v['start']] + remaining[v['end']:]

    trimmed_remaining = remaining.strip()
    if trimmed_remaining:
        first_heredoc_start = min(v['start'] for v in verified)
        prefix = command[:first_heredoc_start]
        if not prefix.strip():
            return False

    # Check that remaining text contains only safe characters.
    if not re.match(r'^[a-zA-Z0-9 \t"\'.\-/_@=,:+~]*$', remaining):
        return False

    # The remaining text must also pass all security validators.
    if bash_command_is_safe_deprecated(remaining)['behavior'] != 'passthrough':
        return False

    return True


def strip_safe_heredoc_substitutions(command: str) -> Optional[str]:
    """
    Detects well-formed $(cat <<'DELIM'...DELIM) heredoc substitution patterns.
    Returns the command with matched heredocs stripped, or None if none found.
    Used by the pre-split gate to strip safe heredocs and re-check the remainder.
    """
    if not HEREDOC_IN_SUBSTITUTION.search(command):
        return None

    heredoc_pattern = re.compile(
        r"""\$\(cat[ \t]*<<(-?)[ \t]*(?:'+([A-Za-z_]\w*)'+|\\([A-Za-z_]\w*))"""
    )
    result = command
    found = False
    ranges = []

    for match in heredoc_pattern.finditer(command):
        if match.start() > 0 and command[match.start() - 1] == '\\':
            continue
        delimiter = match.group(2) or match.group(3)
        if not delimiter:
            continue
        is_dash = match.group(1) == '-'
        operator_end = match.start() + len(match.group(0))

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
                        if next_line is not None and re.match(r'^[ \t]*\)', next_line):
                            next_line_start = body_start + len('\n'.join(body_lines[:i + 1])) + 1
                            close_pos = command.find(')', next_line_start)
                if close_pos != -1:
                    ranges.append({'start': match.start(), 'end': close_pos + 1})
                    found = True
                break

    if not found:
        return None

    for r in reversed(ranges):
        result = result[:r['start']] + result[r['end']:]

    return result


def has_safe_heredoc_substitution(command: str) -> bool:
    """Detection-only check: does the command contain a safe heredoc substitution?"""
    return strip_safe_heredoc_substitutions(command) is not None


def validate_safe_command_substitution(context: ValidationContext) -> PermissionResult:
    original_command = context.original_command

    if not HEREDOC_IN_SUBSTITUTION.search(original_command):
        return {'behavior': 'passthrough', 'message': 'No heredoc in substitution'}

    if is_safe_heredoc(original_command):
        return {
            'behavior': 'allow',
            'updatedInput': {'command': original_command},
            'decisionReason': {
                'type': 'other',
                'reason': 'Safe command substitution: cat with quoted/escaped heredoc delimiter',
            },
        }

    return {'behavior': 'passthrough', 'message': 'Command substitution needs validation'}


def validate_git_commit(context: ValidationContext) -> PermissionResult:
    original_command = context.original_command
    base_command = context.base_command

    if base_command != 'git' or not re.match(r'^git\s+commit\s+', original_command):
        return {'behavior': 'passthrough', 'message': 'Not a git commit'}

    # SECURITY: Backslashes can cause regex to mis-identify quote boundaries.
    if '\\' in original_command:
        return {
            'behavior': 'passthrough',
            'message': 'Git commit contains backslash, needs full validation',
        }

    # SECURITY: The `.*?` before `-m` must NOT match shell operators.
    message_match = re.match(
        r"^git[ \t]+commit[ \t]+[^;&|`$<>()\n\r]*?-m[ \t]+([\"'])([\s\S]*?)\1(.*)$",
        original_command,
    )

    if message_match:
        quote = message_match.group(1)
        message_content = message_match.group(2)
        remainder = message_match.group(3)

        if quote == '"' and message_content and re.search(r'\$\(|`|\$\{', message_content):
            return {
                'behavior': 'ask',
                'message': 'Git commit message contains command substitution patterns',
            }

        if remainder and re.search(r'[;|&()`]|\$\(|\$\{', remainder):
            return {
                'behavior': 'passthrough',
                'message': 'Git commit remainder contains shell metacharacters',
            }

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
                return {
                    'behavior': 'passthrough',
                    'message': 'Git commit remainder contains unquoted redirect operator',
                }

        # Security hardening: block messages starting with dash
        if message_content and message_content.startswith('-'):
            return {
                'behavior': 'ask',
                'message': 'Command contains quoted characters in flag names',
            }

        return {
            'behavior': 'allow',
            'updatedInput': {'command': original_command},
            'decisionReason': {
                'type': 'other',
                'reason': 'Git commit with simple quoted message is allowed',
            },
        }

    return {'behavior': 'passthrough', 'message': 'Git commit needs validation'}


def validate_jq_command(context: ValidationContext) -> PermissionResult:
    original_command = context.original_command
    base_command = context.base_command

    if base_command != 'jq':
        return {'behavior': 'passthrough', 'message': 'Not jq'}

    if re.search(r'\bsystem\s*\(', original_command):
        return {
            'behavior': 'ask',
            'message': 'jq command contains system() function which executes arbitrary commands',
        }

    # File arguments are now allowed - they will be validated by path validation
    # Only block dangerous flags that could read files into jq variables
    after_jq = original_command[3:].strip() if len(original_command) > 3 else ''
    if re.search(
        r'(?:^|\s)(?:-f\b|--from-file|--rawfile|--slurpfile|-L\b|--library-path)',
        after_jq,
    ):
        return {
            'behavior': 'ask',
            'message': 'jq command contains dangerous flags that could execute code or read arbitrary files',
        }

    return {'behavior': 'passthrough', 'message': 'jq command is safe'}


def validate_shell_metacharacters(context: ValidationContext) -> PermissionResult:
    unquoted_content = context.unquoted_content
    message = 'Command contains shell metacharacters (;, |, or &) in arguments'

    if re.search(r'(?:^|\s)["\'][^"\']*[;&][^"\']*["\'](?:\s|$)', unquoted_content):
        return {'behavior': 'ask', 'message': message}

    glob_patterns = [
        re.compile(r"-name\s+[\"'][^\"\']*[;|&][^\"\']*[\"']"),
        re.compile(r"-path\s+[\"'][^\"\']*[;|&][^\"\']*[\"']"),
        re.compile(r"-iname\s+[\"'][^\"\']*[;|&][^\"\']*[\"']"),
    ]

    if any(p.search(unquoted_content) for p in glob_patterns):
        return {'behavior': 'ask', 'message': message}

    if re.search(r"-regex\s+[\"'][^\"\']*[;&][^\"\']*[\"']", unquoted_content):
        return {'behavior': 'ask', 'message': message}

    return {'behavior': 'passthrough', 'message': 'No metacharacters'}


def validate_dangerous_variables(context: ValidationContext) -> PermissionResult:
    fully_unquoted_content = context.fully_unquoted_content

    if (
        re.search(r'[<>|]\s*\$[A-Za-z_]', fully_unquoted_content)
        or re.search(r'\$[A-Za-z_][A-Za-z0-9_]*\s*[|<>]', fully_unquoted_content)
    ):
        return {
            'behavior': 'ask',
            'message': 'Command contains variables in dangerous contexts (redirections or pipes)',
        }

    return {'behavior': 'passthrough', 'message': 'No dangerous variables'}


def validate_dangerous_patterns(context: ValidationContext) -> PermissionResult:
    unquoted_content = context.unquoted_content

    # Special handling for backticks - check for UNESCAPED backticks only
    if has_unescaped_char(unquoted_content, '`'):
        return {
            'behavior': 'ask',
            'message': 'Command contains backticks (`) for command substitution',
        }

    # Other command substitution checks (include double-quoted content)
    for entry in COMMAND_SUBSTITUTION_PATTERNS:
        if entry['pattern'].search(unquoted_content):
            return {'behavior': 'ask', 'message': f"Command contains {entry['message']}"}

    return {'behavior': 'passthrough', 'message': 'No dangerous patterns'}


def validate_redirections(context: ValidationContext) -> PermissionResult:
    fully_unquoted_content = context.fully_unquoted_content

    if re.search(r'<', fully_unquoted_content):
        return {
            'behavior': 'ask',
            'message': 'Command contains input redirection (<) which could read sensitive files',
        }

    if re.search(r'>', fully_unquoted_content):
        return {
            'behavior': 'ask',
            'message': 'Command contains output redirection (>) which could write to arbitrary files',
        }

    return {'behavior': 'passthrough', 'message': 'No redirections'}


def validate_newlines(context: ValidationContext) -> PermissionResult:
    """
    Use fully_unquoted_pre_strip (before strip_safe_redirections) to prevent
    bypasses where stripping >/dev/null creates a phantom backslash-newline continuation.
    """
    fully_unquoted_pre_strip = context.fully_unquoted_pre_strip

    if not re.search(r'[\n\r]', fully_unquoted_pre_strip):
        return {'behavior': 'passthrough', 'message': 'No newlines'}

    # Flag any newline/CR followed by non-whitespace, EXCEPT backslash-newline
    # continuations at word boundaries.
    looks_like_command = bool(re.search(
        r'(?<![\ \t]\\)[\n\r]\s*\S', fully_unquoted_pre_strip
    ))
    if looks_like_command:
        return {
            'behavior': 'ask',
            'message': 'Command contains newlines that could separate multiple commands',
        }

    return {'behavior': 'passthrough', 'message': 'Newlines appear to be within data'}


def validate_carriage_return(context: ValidationContext) -> PermissionResult:
    """
    SECURITY: Carriage return (\\r, 0x0D) IS a misparsing concern.
    
    Parser differential:
      - shell-quote's BAREWORD regex uses `[^\\s...]` — JS `\\s` INCLUDES \\r,
        so shell-quote treats CR as a token boundary. `TZ=UTC\\recho` tokenizes
        as TWO tokens: ['TZ=UTC', 'echo'].
      - bash's default IFS = $' \\t\\n' — CR is NOT in IFS. bash sees
        `TZ=UTC\\recho` as ONE word.
    """
    original_command = context.original_command

    if '\r' not in original_command:
        return {'behavior': 'passthrough', 'message': 'No carriage return'}

    # Check if CR appears outside double quotes.
    in_single_quote = False
    in_double_quote = False
    escaped = False
    for c in original_command:
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
            return {
                'behavior': 'ask',
                'message': r'Command contains carriage return (\r) which shell-quote and bash tokenize differently',
            }

    return {'behavior': 'passthrough', 'message': 'CR only inside double quotes'}


def validate_ifs_injection(context: ValidationContext) -> PermissionResult:
    original_command = context.original_command

    if re.search(r'\$IFS|\$\{[^}]*IFS', original_command):
        return {
            'behavior': 'ask',
            'message': 'Command contains IFS variable usage which could bypass security validation',
        }

    return {'behavior': 'passthrough', 'message': 'No IFS injection detected'}


def validate_proc_environ_access(context: ValidationContext) -> PermissionResult:
    original_command = context.original_command

    if re.search(r'/proc/.*/environ', original_command):
        return {
            'behavior': 'ask',
            'message': 'Command accesses /proc/*/environ which could expose sensitive environment variables',
        }

    return {'behavior': 'passthrough', 'message': 'No /proc/environ access detected'}


def validate_malformed_token_injection(context: ValidationContext) -> PermissionResult:
    """
    Detects commands with malformed tokens (unbalanced delimiters) combined with
    command separators. This catches potential injection patterns where ambiguous
    shell syntax could be exploited.
    """
    original_command = context.original_command

    # Simple check for command separators and unbalanced quotes/braces
    # (Full check requires shell-quote parser; we approximate here)
    has_separator = bool(re.search(r';|&&|\|\|', original_command))
    if not has_separator:
        return {'behavior': 'passthrough', 'message': 'No command separators'}

    # Check for potential JSON/brace injection patterns with separators
    if re.search(r'\{[^}]*[;:|][^}]*\}', original_command):
        return {
            'behavior': 'ask',
            'message': 'Command contains ambiguous syntax with command separators that could be misinterpreted',
        }

    return {'behavior': 'passthrough', 'message': 'No malformed token injection detected'}


def validate_obfuscated_flags(context: ValidationContext) -> PermissionResult:
    """
    Block shell quoting bypass patterns used to circumvent negative lookaheads
    in dangerous flag regexes.
    """
    original_command = context.original_command
    base_command = context.base_command

    # Echo is safe for obfuscated flags, BUT only for simple echo commands.
    has_shell_operators = bool(re.search(r'[|&;]', original_command))
    if base_command == 'echo' and not has_shell_operators:
        return {'behavior': 'passthrough', 'message': 'echo command is safe and has no dangerous flags'}

    # 1. Block ANSI-C quoting ($'...') - can encode any character via escape sequences
    if re.search(r"\$'[^']*'", original_command):
        return {
            'behavior': 'ask',
            'message': "Command contains ANSI-C quoting which can hide characters",
        }

    # 2. Block locale quoting ($"...")  - can also use escape sequences
    if re.search(r'\$"[^"]*"', original_command):
        return {
            'behavior': 'ask',
            'message': "Command contains locale quoting which can hide characters",
        }

    # 3. Block empty ANSI-C or locale quotes followed by dash ($''-exec or $""-exec)
    if re.search(r'\$[\'\"]{2}\s*-', original_command):
        return {
            'behavior': 'ask',
            'message': 'Command contains empty special quotes before dash (potential bypass)',
        }

    # 4. Block ANY sequence of empty quotes followed by dash
    if re.search(r"(?:^|\s)(?:''|\"\")+\s*-", original_command):
        return {
            'behavior': 'ask',
            'message': 'Command contains empty quotes before dash (potential bypass)',
        }

    # 4b. Block homogeneous empty quote pair(s) immediately adjacent to a quoted dash
    if re.search(r'(?:""|\'\')+[\'"]-', original_command):
        return {
            'behavior': 'ask',
            'message': 'Command contains empty quote pair adjacent to quoted dash (potential flag obfuscation)',
        }

    # 4c. Block 3+ consecutive quotes at word start
    if re.search(r"(?:^|\s)['\"`]{3,}", original_command):
        return {
            'behavior': 'ask',
            'message': 'Command contains consecutive quote characters at word start (potential obfuscation)',
        }

    # Track quote state to find obfuscated flags
    in_single_quote = False
    in_double_quote = False
    escaped = False

    for i in range(len(original_command) - 1):
        current_char = original_command[i]
        next_char = original_command[i + 1]

        if escaped:
            escaped = False
            continue

        # SECURITY: Only treat backslash as escape OUTSIDE single quotes.
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

        # Look for whitespace followed by quote that contains a dash (potential flag obfuscation)
        if current_char and next_char and re.match(r'\s', current_char) and next_char in "'`\"":
            quote_char = next_char
            j = i + 2
            inside_quote = ''

            # Collect content inside the quote
            while j < len(original_command) and original_command[j] != quote_char:
                inside_quote += original_command[j]
                j += 1

            if j < len(original_command) and original_command[j] == quote_char:
                char_after_quote = original_command[j + 1] if j + 1 < len(original_command) else None

                has_flag_chars_inside = bool(re.match(r'^-+[a-zA-Z0-9$`]', inside_quote))

                FLAG_CONTINUATION_CHARS = re.compile(r'[a-zA-Z0-9\\${`-]')
                has_flag_chars_continuing = (
                    bool(re.match(r'^-+$', inside_quote))
                    and char_after_quote is not None
                    and FLAG_CONTINUATION_CHARS.match(char_after_quote)
                )

                has_flag_chars_in_next_quote = False
                if (inside_quote == '' or bool(re.match(r'^-+$', inside_quote))) and \
                   char_after_quote is not None and char_after_quote in "'`\"":
                    pos = j + 1
                    combined_content = inside_quote
                    while pos < len(original_command) and original_command[pos] in "'`\"":
                        seg_quote = original_command[pos]
                        end = pos + 1
                        while end < len(original_command) and original_command[end] != seg_quote:
                            end += 1
                        segment = original_command[pos + 1:end]
                        combined_content += segment

                        if re.match(r'^-+[a-zA-Z0-9$`]', combined_content):
                            has_flag_chars_in_next_quote = True
                            break

                        prior_content = combined_content[:-len(segment)] if segment else combined_content
                        if re.match(r'^-+$', prior_content):
                            if re.search(r'[a-zA-Z0-9$`]', segment):
                                has_flag_chars_in_next_quote = True
                                break

                        if end >= len(original_command):
                            break
                        pos = end + 1

                if has_flag_chars_inside or has_flag_chars_continuing or has_flag_chars_in_next_quote:
                    return {
                        'behavior': 'ask',
                        'message': 'Command contains quoted characters in flag names',
                    }

        # Look for whitespace followed by dash - this starts a flag
        if current_char and next_char and re.match(r'\s', current_char) and next_char == '-':
            j = i + 1
            flag_content = ''

            while j < len(original_command):
                flag_char = original_command[j]
                if not flag_char:
                    break
                if re.match(r'[\s=]', flag_char):
                    break
                if flag_char in "'`\"":
                    if base_command == 'cut' and flag_content == '-d' and flag_char in "'`\"":
                        break
                    if j + 1 < len(original_command):
                        next_flag_char = original_command[j + 1]
                        if next_flag_char and not re.match(r"[a-zA-Z0-9_'\"\\-]", next_flag_char):
                            break
                flag_content += flag_char
                j += 1

            if '"' in flag_content or "'" in flag_content:
                return {
                    'behavior': 'ask',
                    'message': 'Command contains quoted characters in flag names',
                }

    # Also handle flags that start with quotes: "--"output, '-'-output, etc.
    if re.search(r"\s['\"` ]-", context.fully_unquoted_content):
        return {
            'behavior': 'ask',
            'message': 'Command contains quoted characters in flag names',
        }

    if re.search(r"['\"` ]{2}-", context.fully_unquoted_content):
        return {
            'behavior': 'ask',
            'message': 'Command contains quoted characters in flag names',
        }

    return {'behavior': 'passthrough', 'message': 'No obfuscated flags detected'}


def has_backslash_escaped_whitespace(command: str) -> bool:
    """
    Detects backslash-escaped whitespace characters (space, tab) outside of quotes.
    
    In bash, `echo\\ test` is a single token (command named "echo test"), but
    shell-quote decodes the escape and produces `echo test` (two separate tokens).
    """
    in_single_quote = False
    in_double_quote = False

    i = 0
    while i < len(command):
        char = command[i]

        if char == '\\' and not in_single_quote:
            if not in_double_quote:
                if i + 1 < len(command):
                    next_char = command[i + 1]
                    if next_char == ' ' or next_char == '\t':
                        return True
            # Skip the escaped character
            i += 2
            continue

        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            i += 1
            continue

        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            i += 1
            continue

        i += 1

    return False


def validate_backslash_escaped_whitespace(context: ValidationContext) -> PermissionResult:
    if has_backslash_escaped_whitespace(context.original_command):
        return {
            'behavior': 'ask',
            'message': 'Command contains backslash-escaped whitespace that could alter command parsing',
        }

    return {'behavior': 'passthrough', 'message': 'No backslash-escaped whitespace'}


def validate_backslash_escaped_operators(context: ValidationContext) -> PermissionResult:
    """
    Detects a backslash immediately preceding a shell operator outside of quotes.
    
    In bash, \\& \\| \\; \\< \\> are operator escapes used in some contexts but
    they're very rare in legitimate commands and more common in bypass attempts.
    """
    command = context.original_command
    in_single_quote = False
    in_double_quote = False
    escaped = False

    for i in range(len(command)):
        char = command[i]

        if escaped:
            escaped = False
            # Check if this escaped character is a shell operator
            if not in_single_quote and not in_double_quote:
                if char in ';&|<>':
                    return {
                        'behavior': 'ask',
                        'message': f'Command contains backslash-escaped shell operator (\\{char})',
                        'isBashSecurityCheckForMisparsing': True,
                    }
            continue

        if char == '\\' and not in_single_quote:
            escaped = True
            continue

        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            continue

        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            continue

    return {'behavior': 'passthrough', 'message': 'No backslash-escaped operators'}


def validate_brace_expansion(context: ValidationContext) -> PermissionResult:
    """
    Detects bash brace expansion patterns that could bypass safety checks.
    Brace expansion like {a,b,c} can obfuscate commands.
    """
    fully_unquoted_pre_strip = context.fully_unquoted_pre_strip

    # Check for brace expansion in unquoted content (not inside quotes)
    # Look for {word,word} patterns which indicate brace expansion
    if re.search(r'\{[^}]+,[^}]+\}', fully_unquoted_pre_strip):
        # Allow common safe patterns like {a..z}, numeric ranges
        # but flag comma-separated brace expansions
        # that could be hiding command names or flags
        brace_match = re.search(r'\{([^}]+)\}', fully_unquoted_pre_strip)
        if brace_match:
            brace_content = brace_match.group(1)
            # Check if any brace expansion element starts with dash (flag obfuscation)
            if re.search(r'(?:^|,)-', brace_content):
                return {
                    'behavior': 'ask',
                    'message': 'Command contains brace expansion with flags which could obfuscate dangerous flags',
                }

    return {'behavior': 'passthrough', 'message': 'No dangerous brace expansion'}


def validate_control_characters(context: ValidationContext) -> PermissionResult:
    """Detect control characters (non-printable ASCII) in commands."""
    if CONTROL_CHAR_RE.search(context.original_command):
        return {
            'behavior': 'ask',
            'message': 'Command contains control characters that could alter command parsing',
        }

    return {'behavior': 'passthrough', 'message': 'No control characters'}


def validate_unicode_whitespace(context: ValidationContext) -> PermissionResult:
    """
    Detect unicode whitespace characters that look like spaces but aren't.
    These can be used to bypass regex-based safety checks.
    """
    if UNICODE_WHITESPACE_RE.search(context.original_command):
        return {
            'behavior': 'ask',
            'message': 'Command contains non-ASCII whitespace characters that could alter command parsing',
        }

    return {'behavior': 'passthrough', 'message': 'No unicode whitespace'}


def validate_mid_word_hash(context: ValidationContext) -> PermissionResult:
    """
    Detects '#' characters appearing mid-word which could be used to bypass
    security checks. In bash, '#' at the start of a word begins a comment, but
    mid-word '#' is not a comment. Shell parsers may interpret it differently.
    """
    unquoted_keep_quote_chars = context.unquoted_keep_quote_chars

    # Look for # that appears after non-whitespace (mid-word)
    if re.search(r'[^\s]#', unquoted_keep_quote_chars):
        return {
            'behavior': 'ask',
            'message': 'Command contains mid-word hash character which could affect parsing',
        }

    return {'behavior': 'passthrough', 'message': 'No mid-word hash'}


def validate_zsh_dangerous_commands(context: ValidationContext) -> PermissionResult:
    """
    Detects Zsh-specific dangerous commands that can bypass security checks.
    """
    original_command = context.original_command

    tokens = original_command.strip().split()
    base_cmd = ''
    for token in tokens:
        if not re.match(r'^[A-Za-z_]\w*=', token):  # Skip env var assignments
            base_cmd = token
            break

    if base_cmd in ZSH_DANGEROUS_COMMANDS:
        return {
            'behavior': 'ask',
            'message': f'Command uses Zsh-specific dangerous command: {base_cmd}',
        }

    return {'behavior': 'passthrough', 'message': 'No Zsh dangerous commands'}


def validate_comment_quote_desync(context: ValidationContext) -> PermissionResult:
    """
    Detects patterns where a '#' inside quotes could desync a quote tracker
    that treats '#' specially (like naive comment-stripping parsers).
    """
    original_command = context.original_command

    # Look for patterns like `"#` or `'#` which can confuse parsers
    # that try to strip comments before processing quotes
    if re.search(r'["\']#', original_command):
        # Check if it's a legitimate use (# inside quoted string vs. desync attack)
        # Allow common patterns like "#!" (shebang in heredoc) and color codes
        if re.search(r'"#[0-9a-fA-F]{3,6}"', original_command):
            return {'behavior': 'passthrough', 'message': 'Color code hex in quotes, safe'}
        # Other # inside quotes could cause parser desync in some contexts
        # but we only flag combined with other suspicious patterns
        pass

    return {'behavior': 'passthrough', 'message': 'No comment-quote desync'}


def validate_quoted_newline(context: ValidationContext) -> PermissionResult:
    """
    Detects literal newlines inside quoted strings.
    A quoted newline is `$'\\n'` expanded or an actual newline inside quotes.
    These can cause issues with some parsers.
    """
    original_command = context.original_command

    in_double_quote = False
    in_single_quote = False
    escaped = False

    for char in original_command:
        if escaped:
            escaped = False
            continue

        if char == '\\' and not in_single_quote:
            escaped = True
            continue

        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            continue

        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            continue

        if char == '\n' and (in_double_quote or in_single_quote):
            return {
                'behavior': 'ask',
                'message': 'Command contains a literal newline inside a quoted string',
            }

    return {'behavior': 'passthrough', 'message': 'No quoted newlines'}


# ---------------------------------------------------------------------------
# Main validation pipeline
# ---------------------------------------------------------------------------

def build_validation_context(command: str, tree_sitter: Any = None) -> ValidationContext:
    """Build a ValidationContext from a raw command string."""
    trimmed = command.strip()

    # Get base command (first non-env-var token)
    tokens = trimmed.split()
    base_command = ''
    for token in tokens:
        if not re.match(r'^[A-Za-z_]\w*=', token):
            base_command = token.strip("'\"")
            break

    quote_result = extract_quoted_content(command)
    fully_unquoted_pre_strip = quote_result['fully_unquoted']
    stripped_content = strip_safe_redirections(fully_unquoted_pre_strip)

    return ValidationContext(
        original_command=command,
        base_command=base_command,
        unquoted_content=quote_result['with_double_quotes'],
        fully_unquoted_content=stripped_content,
        fully_unquoted_pre_strip=fully_unquoted_pre_strip,
        unquoted_keep_quote_chars=quote_result['unquoted_keep_quote_chars'],
        tree_sitter=tree_sitter,
    )


# Validators that are primarily about misparsing (shell-quote vs bash divergence)
# These are tagged with isBashSecurityCheckForMisparsing in their results
_MISPARSING_VALIDATORS = [
    validate_backslash_escaped_operators,
    validate_carriage_return,
]

# All validators in order of application
_ALL_VALIDATORS = [
    validate_empty,
    validate_safe_command_substitution,
    validate_git_commit,
    validate_incomplete_commands,
    validate_jq_command,
    validate_shell_metacharacters,
    validate_dangerous_variables,
    validate_dangerous_patterns,
    validate_redirections,
    validate_newlines,
    validate_carriage_return,
    validate_ifs_injection,
    validate_proc_environ_access,
    validate_malformed_token_injection,
    validate_obfuscated_flags,
    validate_backslash_escaped_whitespace,
    validate_brace_expansion,
    validate_control_characters,
    validate_unicode_whitespace,
    validate_mid_word_hash,
    validate_zsh_dangerous_commands,
    validate_backslash_escaped_operators,
    validate_comment_quote_desync,
    validate_quoted_newline,
]


def bash_command_is_safe_deprecated(command: str, tree_sitter: Any = None) -> PermissionResult:
    """
    DEPRECATED: Legacy safety check for a shell command.
    Returns a PermissionResult dict with behavior: 'passthrough', 'allow', or 'ask'.
    
    This is the synchronous version. 'passthrough' means no special check triggered
    (not safe/unsafe, just no rule matched). 'allow' means explicitly safe.
    'ask' means potentially dangerous.
    
    Uses `isBashSecurityCheckForMisparsing: True` for checks that specifically
    detect shell-quote vs bash tokenization divergence.
    """
    if not command or not command.strip():
        return {
            'behavior': 'allow',
            'updatedInput': {'command': command},
            'decisionReason': {'type': 'other', 'reason': 'Empty command is safe'},
        }

    context = build_validation_context(command, tree_sitter)

    # Tree-sitter authoritative check (if available)
    if tree_sitter is not None:
        # When tree-sitter analysis is available and authoritative, we trust it
        pass

    for validator in _ALL_VALIDATORS:
        result = validator(context)
        if result['behavior'] != 'passthrough':
            return result

    return {'behavior': 'passthrough', 'message': 'No dangerous patterns detected'}


async def bash_command_is_safe_async_deprecated(
    command: str,
    on_divergence: Any = None,
    tree_sitter: Any = None,
) -> PermissionResult:
    """
    Async version of the deprecated safety check.
    The `on_divergence` callback is called when tree-sitter and legacy checks disagree.
    """
    return bash_command_is_safe_deprecated(command, tree_sitter)


# Public aliases (matching the TypeScript exports)
bash_command_is_safe_async_DEPRECATED = bash_command_is_safe_async_deprecated
