"""
Bash command parsing and analysis utilities.
Ported from utils/bash/commands.ts (1339 lines).

Provides:
- splitCommandWithOperators: split a shell command into tokens at operators
- splitCommand_DEPRECATED: legacy path that filters control operators
- filterControlOperators: strip control operator tokens
- isHelpCommand: check if a command is a simple --help invocation
- isUnsafeCompoundCommand_DEPRECATED: detect unsafe compound commands
- extractOutputRedirections: extract > and >> redirections from a command
- getCommandSubcommandPrefix: extract a Bash command prefix for allowlisting
- clearCommandPrefixCaches: clear the LRU caches for prefix extraction

Security notes (ported from TS source):
- Placeholders use random salt to prevent injection attacks.
- isStaticRedirectTarget / isSimpleTarget reject dynamic shell expansions.
- Fail-closed on parse errors.
"""
from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union, TYPE_CHECKING

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Placeholder generation
# ---------------------------------------------------------------------------

def _generate_placeholders() -> Dict[str, str]:
    """
    Generate placeholder strings with random salt to prevent injection attacks.
    The salt prevents malicious commands from containing literal placeholder strings
    that would be replaced during parsing, allowing command argument injection.

    Security: This is critical for preventing attacks where a command like
    `sort __SINGLE_QUOTE__ hello --help __SINGLE_QUOTE__` could inject arguments.
    """
    salt = secrets.token_hex(8)  # 8 random bytes as hex (16 chars)
    return {
        'SINGLE_QUOTE': f'__SINGLE_QUOTE_{salt}__',
        'DOUBLE_QUOTE': f'__DOUBLE_QUOTE_{salt}__',
        'NEW_LINE': f'__NEW_LINE_{salt}__',
        'ESCAPED_OPEN_PAREN': f'__ESCAPED_OPEN_PAREN_{salt}__',
        'ESCAPED_CLOSE_PAREN': f'__ESCAPED_CLOSE_PAREN_{salt}__',
    }


# ---------------------------------------------------------------------------
# File descriptor allowlist
# ---------------------------------------------------------------------------

# File descriptors for standard input/output/error
# https://en.wikipedia.org/wiki/File_descriptor#Standard_streams
ALLOWED_FILE_DESCRIPTORS: Set[str] = {'0', '1', '2'}


# ---------------------------------------------------------------------------
# Static redirect target validation
# ---------------------------------------------------------------------------

def _is_static_redirect_target(target: str) -> bool:
    """
    Checks if a redirection target is a simple static file path that can be
    safely stripped. Returns False for targets containing dynamic content
    (variables, command substitutions, globs, shell expansions) which should
    remain visible in permission prompts for security.

    SECURITY: A static redirect target in bash is a SINGLE shell word. After
    the adjacent-string collapse at splitCommandWithOperators, multiple args
    following a redirect get merged into one string with spaces. For
    `cat > out /etc/passwd`, bash writes to `out` and reads `/etc/passwd`,
    but the collapse gives us `out /etc/passwd` as the "target". Accepting
    this merged blob returns `['cat']` and pathValidation never sees the path.
    Reject any target containing whitespace or quote chars.
    """
    # Reject whitespace or quote chars
    if re.search(r"[\s'\"]", target):
        return False
    # Reject empty string
    if not target:
        return False
    # Reject #-prefixed targets (comment tokens, parser differential)
    if target.startswith('#'):
        return False
    return (
        not target.startswith('!') and   # No history expansion like !!, !-1, !foo
        not target.startswith('=') and   # No Zsh equals expansion
        not target.startswith('&') and   # Not a file descriptor like &1
        '$' not in target and            # No variables like $HOME
        '`' not in target and            # No command substitution
        '*' not in target and            # No glob patterns
        '?' not in target and            # No single-char glob
        '[' not in target and            # No character class glob
        '{' not in target and            # No brace expansion
        '~' not in target and            # No tilde expansion
        '(' not in target and            # No process substitution like >(cmd)
        '<' not in target                # No process substitution like <(cmd)
    )


# ---------------------------------------------------------------------------
# Shell command parsing helpers
# ---------------------------------------------------------------------------

def _try_parse_shell_command(command: str, var_resolver=None) -> Dict[str, Any]:
    """
    Parse a shell command using the shell-quote equivalent.
    Returns {'success': bool, 'tokens': list}.
    
    Uses the bash_parser module if available, otherwise falls back to a simple
    whitespace splitter that handles quoted strings.
    """
    try:
        from claude_code.utils.bash.shell_quote import try_parse_shell_command
        return try_parse_shell_command(command, var_resolver)
    except (ImportError, Exception):
        pass

    # Simple fallback: use shlex for basic parsing
    try:
        import shlex
        tokens = shlex.split(command)
        return {'success': True, 'tokens': tokens}
    except Exception:
        return {'success': False, 'tokens': []}


def _extract_heredocs(command: str) -> Dict[str, Any]:
    """
    Extract heredoc bodies from a command before shell-quote parsing.
    Returns {'processedCommand': str, 'heredocs': list}.
    """
    try:
        from claude_code.utils.bash.heredoc import extract_heredocs
        return extract_heredocs(command)
    except (ImportError, Exception):
        return {'processedCommand': command, 'heredocs': []}


def _restore_heredocs(parts: List[str], heredocs: Any) -> List[str]:
    """Restore heredoc bodies that were extracted earlier."""
    try:
        from claude_code.utils.bash.heredoc import restore_heredocs
        return restore_heredocs(parts, heredocs)
    except (ImportError, Exception):
        return parts


# ---------------------------------------------------------------------------
# Control operators
# ---------------------------------------------------------------------------

_COMMAND_LIST_SEPARATORS: Set[str] = {'&&', '||', ';', ';;', '|'}

_ALL_SUPPORTED_CONTROL_OPERATORS: Set[str] = {
    *_COMMAND_LIST_SEPARATORS,
    '>&',
    '>',
    '>>',
}


def filter_control_operators(commands_and_operators: List[str]) -> List[str]:
    """Filter out control operator tokens from a list of command tokens."""
    return [
        part for part in commands_and_operators
        if part not in _ALL_SUPPORTED_CONTROL_OPERATORS
    ]


# ---------------------------------------------------------------------------
# Join line continuations helper
# ---------------------------------------------------------------------------

def _join_line_continuations(text: str) -> str:
    """
    Join continuation lines (backslash + newline) in a command string.
    Only odd numbers of backslashes before a newline trigger joining.

    SECURITY: We must NOT add a space here - shell joins tokens directly without
    space. Adding a space would allow bypass attacks like `tr\<newline>aceroute`
    being parsed as `tr aceroute` (two tokens) while shell executes `traceroute`
    (one token).
    """
    def replacer(m: re.Match) -> str:
        bs_count = len(m.group()) - 1  # -1 for the newline
        if bs_count % 2 == 1:
            # Odd: last backslash escapes the newline (line continuation)
            return '\\' * (bs_count - 1)
        # Even: all pair up, newline is separator
        return m.group()

    return re.sub(r'\\+\n', replacer, text)


# ---------------------------------------------------------------------------
# splitCommandWithOperators
# ---------------------------------------------------------------------------

def split_command_with_operators(command: str) -> List[str]:
    """
    Split a shell command string into individual tokens (commands, arguments,
    and shell operators).

    Handles:
    - Heredoc extraction
    - Line continuation joining
    - Placeholder injection to preserve quotes
    - Adjacent-string collapsing
    - Operator → string mapping
    """
    parts_accumulator: List[Optional[str]] = []

    # Generate unique placeholders for this parse to prevent injection attacks
    placeholders = _generate_placeholders()

    # Extract heredocs before parsing
    heredoc_result = _extract_heredocs(command)
    processed_command = heredoc_result['processedCommand']
    heredocs = heredoc_result['heredocs']

    # Join continuation lines
    # SECURITY: Must only join on ODD number of backslashes
    command_with_continuations_joined = _join_line_continuations(processed_command)

    # Also join on the ORIGINAL command for fallback paths
    # SECURITY: See TS source for exploit rationale
    command_original_joined = _join_line_continuations(command)

    # Inject placeholders to preserve quotes during parsing
    prepped = (
        command_with_continuations_joined
        .replace('"', f'"{ placeholders["DOUBLE_QUOTE"]}')
        .replace("'", f"'{placeholders['SINGLE_QUOTE']}")
        .replace('\n', f"\n{placeholders['NEW_LINE']}\n")
        .replace('\\(', placeholders['ESCAPED_OPEN_PAREN'])
        .replace('\\)', placeholders['ESCAPED_CLOSE_PAREN'])
    )

    parse_result = _try_parse_shell_command(prepped, lambda v: f'${v}')

    if not parse_result['success']:
        # SECURITY: Return the CONTINUATION-JOINED original
        return [command_original_joined]

    parsed = parse_result['tokens']

    if not parsed:
        return []

    try:
        # 1. Collapse adjacent strings and globs
        for part in parsed:
            if isinstance(part, str):
                if (
                    parts_accumulator
                    and isinstance(parts_accumulator[-1], str)
                ):
                    if part == placeholders['NEW_LINE']:
                        parts_accumulator.append(None)
                    else:
                        parts_accumulator[-1] += ' ' + part
                    continue
            elif isinstance(part, dict):
                if part.get('op') == 'glob':
                    if (
                        parts_accumulator
                        and isinstance(parts_accumulator[-1], str)
                    ):
                        parts_accumulator[-1] += ' ' + part.get('pattern', '')
                        continue
            parts_accumulator.append(part)

        # 2. Map tokens to strings
        string_parts: List[Optional[str]] = []
        for part in parts_accumulator:
            if part is None:
                string_parts.append(None)
                continue
            if isinstance(part, str):
                string_parts.append(part)
                continue
            if isinstance(part, dict):
                if 'comment' in part:
                    # Strip injected-quote prefixes to avoid exponential quoting
                    cleaned = (
                        part['comment']
                        .replace(f'"{ placeholders["DOUBLE_QUOTE"]}', placeholders['DOUBLE_QUOTE'])
                        .replace(f"'{placeholders['SINGLE_QUOTE']}", placeholders['SINGLE_QUOTE'])
                    )
                    string_parts.append('#' + cleaned)
                    continue
                if part.get('op') == 'glob':
                    string_parts.append(part.get('pattern', ''))
                    continue
                if 'op' in part:
                    string_parts.append(part['op'])
                    continue
            string_parts.append(None)

        non_null_parts = [p for p in string_parts if p is not None]

        # 3. Map quotes and escaped parentheses back
        quoted_parts = []
        for part in non_null_parts:
            part = (
                part
                .replace(placeholders['SINGLE_QUOTE'], "'")
                .replace(placeholders['DOUBLE_QUOTE'], '"')
                .replace(f"\n{placeholders['NEW_LINE']}\n", '\n')
                .replace(placeholders['ESCAPED_OPEN_PAREN'], '\\(')
                .replace(placeholders['ESCAPED_CLOSE_PAREN'], '\\)')
            )
            quoted_parts.append(part)

        return _restore_heredocs(quoted_parts, heredocs)

    except Exception:
        # SECURITY: Return the CONTINUATION-JOINED original
        return [command_original_joined]


# ---------------------------------------------------------------------------
# isHelpCommand
# ---------------------------------------------------------------------------

def is_help_command(command: str) -> bool:
    """
    Checks if a command is a help command (e.g., "foo --help" or "foo bar --help")
    and should be allowed as-is without going through prefix extraction.

    We bypass Haiku prefix extraction for simple --help commands because:
    1. Help commands are read-only and safe
    2. We want to allow the full command (e.g., "python --help"), not a prefix
       that would be too broad (e.g., "python:*")
    3. This saves API calls and improves performance for common help queries

    Returns True if:
    - Command ends with --help
    - Command contains no other flags
    - All non-flag tokens are simple alphanumeric identifiers (no paths, special chars)
    """
    trimmed = command.strip()

    # Must end with --help
    if not trimmed.endswith('--help'):
        return False

    # Reject commands with quotes
    if '"' in trimmed or "'" in trimmed:
        return False

    parse_result = _try_parse_shell_command(trimmed)
    if not parse_result['success']:
        return False

    tokens = parse_result['tokens']
    alphanumeric_pattern = re.compile(r'^[a-zA-Z0-9]+$')
    found_help = False

    for token in tokens:
        if isinstance(token, str):
            if token.startswith('-'):
                if token == '--help':
                    found_help = True
                else:
                    return False  # Found another flag
            else:
                if not alphanumeric_pattern.match(token):
                    return False

    return found_help


# ---------------------------------------------------------------------------
# splitCommand_DEPRECATED
# ---------------------------------------------------------------------------

def split_command_deprecated(command: str) -> List[str]:
    """
    @deprecated Legacy regex/shell-quote path. Only used when tree-sitter is
    unavailable. The primary gate is parseForSecurity (ast.ts).

    Splits a command string into individual commands based on shell operators.
    """
    parts: List[Optional[str]] = list(split_command_with_operators(command))

    # Handle standard input/output/error redirection
    for i in range(len(parts)):
        part = parts[i]
        if part is None:
            continue

        if part in ('>&', '>', '>>'):
            prev_part = parts[i - 1].strip() if (i > 0 and isinstance(parts[i - 1], str)) else None
            next_part = parts[i + 1].strip() if (i + 1 < len(parts) and isinstance(parts[i + 1], str)) else None
            after_next_part = (
                parts[i + 2].strip()
                if (i + 2 < len(parts) and isinstance(parts[i + 2], str))
                else None
            )

            if next_part is None:
                continue

            should_strip = False
            strip_third_token = False
            effective_next = next_part

            # SPECIAL CASE: detect `/dev/null 2` pattern
            if (
                part in ('>', '>>')
                and len(next_part) >= 3
                and next_part[-2] == ' '
                and next_part[-1] in ALLOWED_FILE_DESCRIPTORS
                and after_next_part in ('>', '>>', '>&')
            ):
                effective_next = next_part[:-2]

            if part == '>&' and next_part in ALLOWED_FILE_DESCRIPTORS:
                should_strip = True
            elif (
                part == '>'
                and next_part == '&'
                and after_next_part is not None
                and after_next_part in ALLOWED_FILE_DESCRIPTORS
            ):
                should_strip = True
                strip_third_token = True
            elif (
                part == '>'
                and next_part.startswith('&')
                and len(next_part) > 1
                and next_part[1:] in ALLOWED_FILE_DESCRIPTORS
            ):
                should_strip = True
            elif part in ('>', '>>') and _is_static_redirect_target(effective_next):
                should_strip = True

            if should_strip:
                # Remove trailing file descriptor from previous part
                # SECURITY: Only strip when preceded by space and leaves non-empty string
                if (
                    prev_part
                    and len(prev_part) >= 3
                    and prev_part[-1] in ALLOWED_FILE_DESCRIPTORS
                    and prev_part[-2] == ' '
                ):
                    parts[i - 1] = prev_part[:-2]

                parts[i] = None
                parts[i + 1] = None
                if strip_third_token and i + 2 < len(parts):
                    parts[i + 2] = None

    # Remove None and empty strings
    string_parts = [p for p in parts if p is not None and p != '']
    return filter_control_operators(string_parts)


# ---------------------------------------------------------------------------
# isUnsafeCompoundCommand_DEPRECATED
# ---------------------------------------------------------------------------

def _is_command_list(command: str) -> bool:
    """
    Checks if a command is just a list of commands joined by safe operators.
    Internal helper for isUnsafeCompoundCommand_DEPRECATED.
    """
    placeholders = _generate_placeholders()
    heredoc_result = _extract_heredocs(command)
    processed_command = heredoc_result['processedCommand']

    prepped = (
        processed_command
        .replace('"', f'"{ placeholders["DOUBLE_QUOTE"]}')
        .replace("'", f"'{placeholders['SINGLE_QUOTE']}")
    )

    parse_result = _try_parse_shell_command(prepped, lambda v: f'${v}')
    if not parse_result['success']:
        return False

    parts = parse_result['tokens']
    for i, part in enumerate(parts):
        if part is None:
            continue
        if isinstance(part, str):
            continue
        if isinstance(part, dict):
            if 'comment' in part:
                return False
            if part.get('op') == 'glob':
                continue
            if part.get('op') in _COMMAND_LIST_SEPARATORS:
                continue
            if part.get('op') == '>&':
                next_part = parts[i + 1] if i + 1 < len(parts) else None
                if (
                    next_part is not None
                    and isinstance(next_part, str)
                    and next_part.strip() in ALLOWED_FILE_DESCRIPTORS
                ):
                    continue
            if part.get('op') in ('>', '>>'):
                continue
            return False
    return True


def is_unsafe_compound_command_deprecated(command: str) -> bool:
    """
    @deprecated Legacy regex/shell-quote path. Only used when tree-sitter is
    unavailable. The primary gate is parseForSecurity (ast.ts).

    Defense-in-depth: if shell-quote can't parse the command at all,
    treat it as unsafe so it always prompts the user.
    """
    heredoc_result = _extract_heredocs(command)
    processed = heredoc_result['processedCommand']
    parse_result = _try_parse_shell_command(processed, lambda v: f'${v}')
    if not parse_result['success']:
        return True
    return (
        len(split_command_deprecated(command)) > 1
        and not _is_command_list(command)
    )


# ---------------------------------------------------------------------------
# extractOutputRedirections
# ---------------------------------------------------------------------------

@dataclass
class Redirection:
    """A single output redirection extracted from a command."""
    target: str
    operator: str  # '>' or '>>'


@dataclass
class ExtractOutputRedirectionsResult:
    """Result of extracting output redirections from a command."""
    command_without_redirections: str
    redirections: List[Redirection]
    has_dangerous_redirection: bool


def _is_simple_target(target: Any) -> bool:
    """
    Returns True if target is a simple static string that can be path-validated.

    SECURITY: Reject empty strings. An empty target can arise from shell-quote
    emitting '' for `\<newline>`. In bash, `> \<newline>/etc/passwd` joins the
    continuation and writes to /etc/passwd.
    """
    if not isinstance(target, str) or not target:
        return False
    return (
        not target.startswith('!') and
        not target.startswith('=') and
        not target.startswith('~') and
        '$' not in target and
        '`' not in target and
        '*' not in target and
        '?' not in target and
        '[' not in target and
        '{' not in target
    )


def _has_dangerous_expansion(target: Any) -> bool:
    """
    Checks if a redirection target contains shell expansion syntax that could
    bypass path validation.

    Design invariant: for every string redirect target, EITHER isSimpleTarget
    is TRUE (→ captured → path-validated) OR hasDangerousExpansion is TRUE
    (→ flagged dangerous → ask).
    """
    if isinstance(target, dict) and target.get('op') == 'glob':
        return True
    if not isinstance(target, str):
        return False
    if not target:
        return False
    return (
        '$' in target or
        '%' in target or
        '`' in target or
        '*' in target or
        '?' in target or
        '[' in target or
        '{' in target or
        target.startswith('!') or
        target.startswith('=') or
        target.startswith('~')
    )


def _is_operator(part: Any, op: str) -> bool:
    """Check if a parsed token is a specific operator."""
    return isinstance(part, dict) and part.get('op') == op


def _is_file_descriptor(p: Any) -> bool:
    """Check if a token is a file descriptor number (0-9)."""
    return isinstance(p, str) and bool(re.match(r'^\d+$', p.strip()))


def _handle_fd_redirection(
    fd: str,
    operator: str,
    target: Any,
    redirections: List[Redirection],
    kept: List[Any],
    skip_count: int = 1,
) -> Dict[str, Any]:
    """Handle a file-descriptor-based redirection (e.g., 2>/tmp/file, 2>&1)."""
    is_stdout = fd == '1'
    is_file_target = (
        target is not None
        and _is_simple_target(target)
        and isinstance(target, str)
        and not re.match(r'^\d+$', target)
    )
    is_fd_target = isinstance(target, str) and bool(re.match(r'^\d+$', target.strip()))

    # Always remove the fd number from kept
    if kept:
        kept.pop()

    # SECURITY: Check for dangerous expansion FIRST
    if not is_fd_target and _has_dangerous_expansion(target):
        return {'skip': 0, 'dangerous': True}

    if is_file_target:
        redirections.append(Redirection(target=target, operator=operator))
        if not is_stdout:
            kept.extend([fd + operator, target])
        return {'skip': skip_count, 'dangerous': False}

    if not is_stdout:
        kept.append(fd + operator)
        if target:
            kept.append(target)
            return {'skip': 1, 'dangerous': False}

    return {'skip': 0, 'dangerous': False}


def _handle_redirection(
    part: Any,
    prev: Any,
    next_: Any,
    next_next: Any,
    next_next_next: Any,
    redirections: List[Redirection],
    kept: List[Any],
) -> Dict[str, Any]:
    """
    Handle a single redirection operator token.
    Returns {'skip': int, 'dangerous': bool}.
    """
    # Handle > and >> operators
    if _is_operator(part, '>') or _is_operator(part, '>>'):
        operator = part['op']  # '>' or '>>'

        # File descriptor redirection (2>, 3>, etc.)
        if _is_file_descriptor(prev):
            prev_fd = prev.strip()
            # Check for ZSH force clobber 2>!
            if next_ == '!' and _is_simple_target(next_next):
                return _handle_fd_redirection(prev_fd, operator, next_next, redirections, kept, 2)
            if next_ == '!' and _has_dangerous_expansion(next_next):
                return {'skip': 0, 'dangerous': True}
            # 2>|
            if _is_operator(next_, '|') and _is_simple_target(next_next):
                return _handle_fd_redirection(prev_fd, operator, next_next, redirections, kept, 2)
            if _is_operator(next_, '|') and _has_dangerous_expansion(next_next):
                return {'skip': 0, 'dangerous': True}
            # 2>!filename (no space)
            if (
                isinstance(next_, str)
                and next_.startswith('!')
                and len(next_) > 1
                and next_[1] not in ('!', '-', '?')
                and not re.match(r'^!\d', next_)
            ):
                after_bang = next_[1:]
                if _has_dangerous_expansion(after_bang):
                    return {'skip': 0, 'dangerous': True}
                return _handle_fd_redirection(prev_fd, operator, after_bang, redirections, kept, 1)
            return _handle_fd_redirection(prev_fd, operator, next_, redirections, kept, 1)

        # >| force overwrite
        if _is_operator(next_, '|') and _is_simple_target(next_next):
            redirections.append(Redirection(target=next_next, operator=operator))
            return {'skip': 2, 'dangerous': False}
        if _is_operator(next_, '|') and _has_dangerous_expansion(next_next):
            return {'skip': 0, 'dangerous': True}

        # >! ZSH force clobber
        if next_ == '!' and _is_simple_target(next_next):
            redirections.append(Redirection(target=next_next, operator=operator))
            return {'skip': 2, 'dangerous': False}
        if next_ == '!' and _has_dangerous_expansion(next_next):
            return {'skip': 0, 'dangerous': True}

        # >!filename (no space)
        if (
            isinstance(next_, str)
            and next_.startswith('!')
            and len(next_) > 1
            and next_[1] not in ('!', '-', '?')
            and not re.match(r'^!\d', next_)
        ):
            after_bang = next_[1:]
            if _has_dangerous_expansion(after_bang):
                return {'skip': 0, 'dangerous': True}
            redirections.append(Redirection(target=after_bang, operator=operator))
            return {'skip': 1, 'dangerous': False}

        # >>&! and >>&| patterns
        if _is_operator(next_, '&'):
            if next_next == '!' and _is_simple_target(next_next_next):
                redirections.append(Redirection(target=next_next_next, operator=operator))
                return {'skip': 3, 'dangerous': False}
            if next_next == '!' and _has_dangerous_expansion(next_next_next):
                return {'skip': 0, 'dangerous': True}
            if _is_operator(next_next, '|') and _is_simple_target(next_next_next):
                redirections.append(Redirection(target=next_next_next, operator=operator))
                return {'skip': 3, 'dangerous': False}
            if _is_operator(next_next, '|') and _has_dangerous_expansion(next_next_next):
                return {'skip': 0, 'dangerous': True}
            if _is_simple_target(next_next):
                redirections.append(Redirection(target=next_next, operator=operator))
                return {'skip': 2, 'dangerous': False}
            if _has_dangerous_expansion(next_next):
                return {'skip': 0, 'dangerous': True}

        # Standard stdout redirection
        if _is_simple_target(next_):
            redirections.append(Redirection(target=next_, operator=operator))
            return {'skip': 1, 'dangerous': False}
        if _has_dangerous_expansion(next_):
            return {'skip': 0, 'dangerous': True}

    # Handle >& operator
    if _is_operator(part, '>&'):
        if _is_file_descriptor(prev) and _is_file_descriptor(next_):
            return {'skip': 0, 'dangerous': False}
        if _is_operator(next_, '|') and _is_simple_target(next_next):
            redirections.append(Redirection(target=next_next, operator='>'))
            return {'skip': 2, 'dangerous': False}
        if _is_operator(next_, '|') and _has_dangerous_expansion(next_next):
            return {'skip': 0, 'dangerous': True}
        if next_ == '!' and _is_simple_target(next_next):
            redirections.append(Redirection(target=next_next, operator='>'))
            return {'skip': 2, 'dangerous': False}
        if next_ == '!' and _has_dangerous_expansion(next_next):
            return {'skip': 0, 'dangerous': True}
        if _is_simple_target(next_) and not _is_file_descriptor(next_):
            redirections.append(Redirection(target=next_, operator='>'))
            return {'skip': 1, 'dangerous': False}
        if not _is_file_descriptor(next_) and _has_dangerous_expansion(next_):
            return {'skip': 0, 'dangerous': True}

    return {'skip': 0, 'dangerous': False}


def _reconstruct_command(kept: List[Any], original_cmd: str) -> str:
    """
    Reconstruct a shell command string from parsed tokens.
    Used by extractOutputRedirections to rebuild after stripping redirections.
    """
    if not kept:
        return original_cmd

    result = ''
    cmd_sub_depth = 0
    in_process_sub = False

    def needs_quoting(s: str) -> bool:
        if re.match(r'^\d+>>?$', s):
            return False
        if re.search(r'\s', s):
            return True
        if len(s) == 1 and s in '><|&;()':
            return True
        return False

    def add_token(res: str, tok: str, no_space: bool = False) -> str:
        if not res or no_space:
            return res + tok
        return res + ' ' + tok

    for i, part in enumerate(kept):
        prev = kept[i - 1] if i > 0 else None
        next_ = kept[i + 1] if i + 1 < len(kept) else None

        if isinstance(part, str):
            has_sep = bool(re.search(r'[|&;]', part))
            if has_sep:
                s = f'"{part}"'
            elif needs_quoting(part):
                try:
                    from claude_code.utils.bash.shell_quote import quote
                    s = quote([part])
                except (ImportError, Exception):
                    import shlex
                    s = shlex.quote(part)
            else:
                s = part

            no_space = (
                result.endswith('(')
                or prev == '$'
                or (isinstance(prev, dict) and prev.get('op') == ')')
            )

            if result.endswith('<('):
                result += ' ' + s
            else:
                result = add_token(result, s, no_space)
            continue

        if not isinstance(part, dict) or 'op' not in part:
            continue

        op = part['op']

        if op == 'glob':
            result = add_token(result, part.get('pattern', ''))
            continue

        # File descriptor redirects (2>&1)
        if (
            op == '>&'
            and isinstance(prev, str)
            and re.match(r'^\d+$', prev)
            and isinstance(next_, str)
            and re.match(r'^\d+$', next_)
        ):
            last_idx = result.rfind(prev)
            result = result[:last_idx] + prev + op + next_
            # Skip next
            continue

        # Heredoc handling
        if op == '<' and _is_operator(next_, '<'):
            delimiter = kept[i + 2] if i + 2 < len(kept) else None
            if delimiter and isinstance(delimiter, str):
                result = add_token(result, delimiter)
                continue

        if op == '<<<':
            result = add_token(result, op)
            continue

        if op == '(':
            # Command substitution depth tracking
            if isinstance(prev, str) and (prev == '$' or prev.endswith('$')):
                cmd_sub_depth += 1
                if result.endswith(' '):
                    result = result[:-1]
                result += '('
            else:
                no_sp = result.endswith('<(') or result.endswith('(')
                result = add_token(result, '(', no_sp)
            continue

        if op == ')':
            if in_process_sub:
                in_process_sub = False
                result += ')'
                continue
            if cmd_sub_depth > 0:
                cmd_sub_depth -= 1
            result += ')'
            continue

        if op == '<(':
            in_process_sub = True
            result = add_token(result, op)
            continue

        if op in ('&&', '||', '|', ';', '>', '>>', '<'):
            result = add_token(result, op)

    return result.strip() or original_cmd


def extract_output_redirections(cmd: str) -> ExtractOutputRedirectionsResult:
    """
    Extracts output redirections from a command if present.
    Only handles simple string targets (no variables or command substitutions).

    Returns ExtractOutputRedirectionsResult with:
    - command_without_redirections: the command minus redirect tokens
    - redirections: list of Redirection(target, operator) pairs
    - has_dangerous_redirection: True if any unsafe redirection was found

    Security: FAIL-CLOSED on parse failure (hasDangerousRedirection=True).

    TODO: Refactor and simplify once we have AST parsing.
    """
    redirections: List[Redirection] = []
    has_dangerous_redirection = False

    # SECURITY: Extract heredocs BEFORE line-continuation joining AND parsing.
    # This matches splitCommandWithOperators. ORDER MATTERS.
    heredoc_result = _extract_heredocs(cmd)
    heredoc_extracted = heredoc_result['processedCommand']
    heredocs = heredoc_result['heredocs']

    # SECURITY: Join line continuations AFTER heredoc extraction, BEFORE parsing.
    processed_command = _join_line_continuations(heredoc_extracted)

    parse_result = _try_parse_shell_command(processed_command, lambda e: f'${e}')

    # SECURITY: FAIL-CLOSED on parse failure.
    if not parse_result['success']:
        return ExtractOutputRedirectionsResult(
            command_without_redirections=cmd,
            redirections=[],
            has_dangerous_redirection=True,
        )

    parsed = parse_result['tokens']

    # Find redirected subshells (e.g., "(cmd) > file")
    redirected_subshells: Set[int] = set()
    paren_stack: List[Dict[str, Any]] = []

    for i, part in enumerate(parsed):
        if _is_operator(part, '('):
            prev = parsed[i - 1] if i > 0 else None
            is_start = (
                i == 0 or (
                    isinstance(prev, dict)
                    and prev.get('op') in ('&&', '||', ';', '|')
                )
            )
            paren_stack.append({'index': i, 'is_start': bool(is_start)})
        elif _is_operator(part, ')') and paren_stack:
            opening = paren_stack.pop()
            next_p = parsed[i + 1] if i + 1 < len(parsed) else None
            if (
                opening['is_start']
                and (_is_operator(next_p, '>') or _is_operator(next_p, '>>'))
            ):
                redirected_subshells.add(opening['index'])
                redirected_subshells.add(i)

    # Process command and extract redirections
    kept: List[Any] = []
    cmd_sub_depth = 0
    i = 0

    while i < len(parsed):
        part = parsed[i]
        if part is None:
            i += 1
            continue

        prev = parsed[i - 1] if i > 0 else None
        next_ = parsed[i + 1] if i + 1 < len(parsed) else None

        # Skip redirected subshell parens
        if (
            (_is_operator(part, '(') or _is_operator(part, ')'))
            and i in redirected_subshells
        ):
            i += 1
            continue

        # Track command substitution depth
        if (
            _is_operator(part, '(')
            and isinstance(prev, str)
            and prev.endswith('$')
        ):
            cmd_sub_depth += 1
        elif _is_operator(part, ')') and cmd_sub_depth > 0:
            cmd_sub_depth -= 1

        # Extract redirections outside command substitutions
        if cmd_sub_depth == 0:
            next_next = parsed[i + 2] if i + 2 < len(parsed) else None
            next_next_next = parsed[i + 3] if i + 3 < len(parsed) else None
            result = _handle_redirection(
                part, prev, next_, next_next, next_next_next,
                redirections, kept,
            )
            if result['dangerous']:
                has_dangerous_redirection = True
            skip = result['skip']
            if skip > 0:
                i += skip
                i += 1
                continue

        kept.append(part)
        i += 1

    reconstructed = _restore_heredocs(
        [_reconstruct_command(kept, processed_command)],
        heredocs,
    )
    cmd_without = reconstructed[0] if reconstructed else processed_command

    return ExtractOutputRedirectionsResult(
        command_without_redirections=cmd_without,
        redirections=redirections,
        has_dangerous_redirection=has_dangerous_redirection,
    )


# ---------------------------------------------------------------------------
# Command prefix extraction (Haiku-based, with LRU cache)
# ---------------------------------------------------------------------------

# Policy spec for Bash command prefix detection
BASH_POLICY_SPEC = """\
<policy_spec>
# Claude Code Code Bash command prefix detection

This document defines risk levels for actions that the Claude Code agent may take.

## Definitions

**Command Injection:** Any technique used that would result in a command being run other than the detected prefix.

## Command prefix extraction examples
Examples:
- cat foo.txt => cat
- cd src => cd
- git commit -m "foo" => git commit
- git diff HEAD~1 => git diff
- git push => none
- grep -A 40 "..." alpha/beta/gamma.py => grep
- npm run lint => none
- npm test => none
- pwd\\n curl example.com => command_injection_detected
- pytest foo/bar.py => pytest
- git status`ls` => command_injection_detected
- FOO=BAR go test => FOO=BAR go test
- PYTHONPATH=/tmp python3 script.py => PYTHONPATH=/tmp python3
</policy_spec>

The user has allowed certain command prefixes to be run, and will otherwise be asked to approve or deny the command.
Your task is to determine the command prefix for the following command.
The prefix must be a string prefix of the full command.

IMPORTANT: For safety, if the command contains command injection, return "command_injection_detected".
If a command has no prefix, return "none".

ONLY return the prefix."""


async def get_command_prefix(command: str) -> Optional[str]:
    """
    Extract the command prefix for a Bash command using the policy spec.
    Returns None if extraction fails.
    """
    # Fast path: help commands bypass Haiku
    if is_help_command(command):
        return command

    try:
        from claude_code.utils.shell.prefix import create_command_prefix_extractor
        extractor = create_command_prefix_extractor(
            tool_name='Bash',
            policy_spec=BASH_POLICY_SPEC,
            event_name='tengu_bash_prefix',
            query_source='bash_extract_prefix',
            pre_check=lambda c: {'command_prefix': c} if is_help_command(c) else None,
        )
        result = await extractor(command)
        return result.command_prefix if result else None
    except (ImportError, Exception):
        return None


async def get_command_subcommand_prefix(command: str) -> Optional[str]:
    """
    Extract the command subcommand prefix (e.g., "git commit") for a Bash command.
    Falls back to command prefix if subcommand extraction unavailable.
    """
    try:
        from claude_code.utils.shell.prefix import create_subcommand_prefix_extractor
        extractor = create_subcommand_prefix_extractor(
            get_command_prefix,
            split_command_deprecated,
        )
        result = await extractor(command)
        return result.command_prefix if result else None
    except (ImportError, Exception):
        return await get_command_prefix(command)


def clear_command_prefix_caches() -> None:
    """
    Clear both command prefix caches. Called on /clear to release memory.
    """
    try:
        from claude_code.utils.shell.prefix import (
            get_command_prefix_cache,
            get_subcommand_prefix_cache,
        )
        get_command_prefix_cache().clear()
        get_subcommand_prefix_cache().clear()
    except (ImportError, Exception):
        pass


# ---------------------------------------------------------------------------
# Public API re-exports
# ---------------------------------------------------------------------------

# Expose CommandPrefixResult and CommandSubcommandPrefixResult if available
try:
    from claude_code.utils.shell.prefix import (
        CommandPrefixResult,
        CommandSubcommandPrefixResult,
    )
except ImportError:
    # Provide minimal stubs
    @dataclass
    class CommandPrefixResult:  # type: ignore[no-redef]
        """Result of command prefix extraction."""
        command_prefix: Optional[str] = None

    @dataclass
    class CommandSubcommandPrefixResult:  # type: ignore[no-redef]
        """Result of command subcommand prefix extraction."""
        command_prefix: Optional[str] = None
