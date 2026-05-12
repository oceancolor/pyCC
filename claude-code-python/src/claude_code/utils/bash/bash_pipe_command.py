"""
bash_pipe_command.py - Rearranges pipe commands for correct stdin redirect placement.

Port of TypeScript bashPipeCommand.ts.
"""

import re
from typing import List, Optional, Union

# Type alias for parsed shell entries
ParseEntry = Union[str, dict]


def rearrange_pipe_command(command: str) -> str:
    """
    Rearranges a command with pipes to place stdin redirect after the first command.
    This fixes an issue where eval treats the entire piped command as a single unit,
    causing the stdin redirect to apply to eval itself rather than the first command.
    """
    from .shell_quote import try_parse_shell_command, has_malformed_tokens, has_shell_quote_single_quote_bug, quote

    # Skip if command has backticks - shell-quote doesn't handle them well
    if '`' in command:
        return _quote_with_eval_stdin_redirect(command)

    # Skip if command has command substitution
    if '$(' in command:
        return _quote_with_eval_stdin_redirect(command)

    # Skip if command references shell variables
    if re.search(r'\$[A-Za-z_{]', command):
        return _quote_with_eval_stdin_redirect(command)

    # Skip if command contains bash control structures
    if _contains_control_structure(command):
        return _quote_with_eval_stdin_redirect(command)

    # Join continuation lines before parsing
    joined = _join_continuation_lines(command)

    # Bail on bare newlines
    if '\n' in joined:
        return _quote_with_eval_stdin_redirect(command)

    # Check for shell-quote single quote bug
    if has_shell_quote_single_quote_bug(joined):
        return _quote_with_eval_stdin_redirect(command)

    parse_result = try_parse_shell_command(joined)

    if not parse_result['success']:
        return _quote_with_eval_stdin_redirect(command)

    parsed = parse_result['tokens']

    if has_malformed_tokens(joined, parsed):
        return _quote_with_eval_stdin_redirect(command)

    first_pipe_index = _find_first_pipe_operator(parsed)

    if first_pipe_index <= 0:
        return _quote_with_eval_stdin_redirect(command)

    # Rebuild: first_command < /dev/null | rest_of_pipeline
    parts = (
        _build_command_parts(parsed, 0, first_pipe_index)
        + ['< /dev/null']
        + _build_command_parts(parsed, first_pipe_index, len(parsed))
    )

    return _single_quote_for_eval(' '.join(parts))


def _find_first_pipe_operator(parsed: List[ParseEntry]) -> int:
    """Finds the index of the first pipe operator in parsed shell command."""
    for i, entry in enumerate(parsed):
        if _is_operator(entry, '|'):
            return i
    return -1


def _build_command_parts(parsed: List[ParseEntry], start: int, end: int) -> List[str]:
    """Builds command parts from parsed entries."""
    from .shell_quote import quote

    parts = []
    seen_non_env_var = False

    i = start
    while i < end:
        entry = parsed[i]

        # Check for file descriptor redirections (e.g., 2>&1, 2>/dev/null)
        if (isinstance(entry, str) and re.match(r'^[012]$', entry)
                and i + 2 < end and _is_operator(parsed[i + 1])):
            op = parsed[i + 1]
            target = parsed[i + 2]

            if isinstance(op, dict):
                if op.get('op') == '>&' and isinstance(target, str) and re.match(r'^[012]$', target):
                    parts.append(f"{entry}>&{target}")
                    i += 3
                    continue

                if op.get('op') == '>' and target == '/dev/null':
                    parts.append(f"{entry}>/dev/null")
                    i += 3
                    continue

                if op.get('op') == '>' and isinstance(target, str) and target.startswith('&'):
                    fd = target[1:]
                    if re.match(r'^[012]$', fd):
                        parts.append(f"{entry}>&{fd}")
                        i += 3
                        continue

        # Handle regular entries
        if isinstance(entry, str):
            is_env_var = not seen_non_env_var and _is_environment_variable_assignment(entry)

            if is_env_var:
                eq_index = entry.index('=')
                name = entry[:eq_index]
                value = entry[eq_index + 1:]
                quoted_value = quote([value])
                parts.append(f"{name}={quoted_value}")
            else:
                seen_non_env_var = True
                parts.append(quote([entry]))
        elif _is_operator(entry):
            if isinstance(entry, dict) and entry.get('op') == 'glob' and 'pattern' in entry:
                parts.append(entry['pattern'])
            else:
                op_str = entry.get('op', '') if isinstance(entry, dict) else ''
                parts.append(op_str)
                if _is_command_separator(op_str):
                    seen_non_env_var = False

        i += 1

    return parts


def _is_environment_variable_assignment(s: str) -> bool:
    """Checks if a string is an environment variable assignment (VAR=value)."""
    return bool(re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', s))


def _is_command_separator(op: str) -> bool:
    """Checks if an operator is a command separator."""
    return op in ('&&', '||', ';')


def _is_operator(entry: object, op: Optional[str] = None) -> bool:
    """Type guard to check if a parsed entry is an operator."""
    if not isinstance(entry, dict) or 'op' not in entry:
        return False
    if op is not None:
        return entry['op'] == op
    return True


def _contains_control_structure(command: str) -> bool:
    """Checks if a command contains bash control structures."""
    return bool(re.search(r'\b(for|while|until|if|case|select)\s', command))


def _quote_with_eval_stdin_redirect(command: str) -> str:
    """Quotes a command and adds `< /dev/null` as a shell redirect on eval."""
    return _single_quote_for_eval(command) + ' < /dev/null'


def _single_quote_for_eval(s: str) -> str:
    """Single-quote a string for use as an eval argument."""
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _join_continuation_lines(command: str) -> str:
    """Joins shell continuation lines (backslash-newline) into a single line."""
    def replace_match(m: re.Match) -> str:
        match_str = m.group(0)
        backslash_count = len(match_str) - 1  # -1 for the newline
        if backslash_count % 2 == 1:
            return '\\' * (backslash_count - 1)
        else:
            return match_str

    return re.sub(r'\\+\n', replace_match, command)
