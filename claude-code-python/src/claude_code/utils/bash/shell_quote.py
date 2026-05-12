"""
shell_quote.py - Safe wrappers for shell quoting functions.

Port of TypeScript shellQuote.ts.
"""

import re
import shlex
from typing import Any, Callable, Dict, List, Optional, Union


ParseEntry = Union[str, dict]

ShellParseResult = Dict  # {'success': bool, 'tokens'?: list, 'error'?: str}
ShellQuoteResult = Dict  # {'success': bool, 'quoted'?: str, 'error'?: str}


def try_parse_shell_command(
    cmd: str,
    env: Optional[Union[Dict[str, Optional[str]], Callable[[str], Optional[str]]]] = None,
) -> ShellParseResult:
    """
    Safely parse a shell command string into tokens.
    Returns dict with 'success' key and either 'tokens' or 'error'.
    """
    try:
        tokens = _shell_parse(cmd, env)
        return {'success': True, 'tokens': tokens}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _shell_parse(
    cmd: str,
    env: Optional[Union[Dict, Callable]] = None,
) -> List[ParseEntry]:
    """Parse a shell command string into a list of tokens and operators."""
    # Simple tokenizer that handles basic shell quoting
    tokens: List[ParseEntry] = []
    i = 0
    current = []
    in_single = False
    in_double = False

    while i < len(cmd):
        ch = cmd[i]

        if in_single:
            if ch == "'":
                in_single = False
            else:
                current.append(ch)
            i += 1
            continue

        if in_double:
            if ch == '\\' and i + 1 < len(cmd):
                next_ch = cmd[i + 1]
                if next_ch in ('"', '\\', '$', '`', '\n'):
                    current.append(next_ch)
                    i += 2
                    continue
            if ch == '"':
                in_double = False
                i += 1
                continue
            current.append(ch)
            i += 1
            continue

        if ch == "'":
            in_single = True
            i += 1
            continue

        if ch == '"':
            in_double = True
            i += 1
            continue

        if ch == '\\' and i + 1 < len(cmd):
            current.append(cmd[i + 1])
            i += 2
            continue

        # Check for operators
        two_char = cmd[i:i + 2]
        if two_char in ('&&', '||', '>>', '>&'):
            if current:
                tokens.append(''.join(current))
                current = []
            tokens.append({'op': two_char})
            i += 2
            continue

        if ch in ('|', ';', '(', ')', '<', '>'):
            if current:
                tokens.append(''.join(current))
                current = []
            tokens.append({'op': ch})
            i += 1
            continue

        if ch in (' ', '\t'):
            if current:
                tokens.append(''.join(current))
                current = []
            i += 1
            continue

        # Handle variable expansion
        if ch == '$' and env is not None:
            var_match = re.match(r'\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?', cmd[i:])
            if var_match:
                var_name = var_match.group(1)
                if callable(env):
                    val = env(var_name)
                else:
                    val = env.get(var_name, '')
                current.append(val or '')
                i += len(var_match.group(0))
                continue

        current.append(ch)
        i += 1

    if current:
        tokens.append(''.join(current))

    return tokens


def try_quote_shell_args(args: List[Any]) -> ShellQuoteResult:
    """Safely quote shell arguments."""
    try:
        validated = []
        for idx, arg in enumerate(args):
            if arg is None:
                validated.append('None')
            elif isinstance(arg, (str, int, float, bool)):
                validated.append(str(arg))
            elif isinstance(arg, dict):
                raise ValueError(f"Cannot quote argument at index {idx}: object values are not supported")
            else:
                raise ValueError(f"Cannot quote argument at index {idx}: unsupported type {type(arg)}")

        quoted = _shell_quote(validated)
        return {'success': True, 'quoted': quoted}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _shell_quote(args: List[str]) -> str:
    """Quote a list of string arguments for use in a shell command."""
    return ' '.join(shlex.quote(str(a)) for a in args)


def has_malformed_tokens(command: str, parsed: List[ParseEntry]) -> bool:
    """
    Checks if parsed tokens contain malformed entries.
    Also detects unterminated quotes.
    """
    # Check for unterminated quotes
    in_single = False
    in_double = False
    double_count = 0
    single_count = 0

    i = 0
    while i < len(command):
        c = command[i]
        if c == '\\' and not in_single:
            i += 2
            continue
        if c == '"' and not in_single:
            double_count += 1
            in_double = not in_double
        elif c == "'" and not in_double:
            single_count += 1
            in_single = not in_single
        i += 1

    if double_count % 2 != 0 or single_count % 2 != 0:
        return True

    for entry in parsed:
        if not isinstance(entry, str):
            continue

        # Check for unbalanced braces
        if entry.count('{') != entry.count('}'):
            return True

        # Check for unbalanced parentheses
        if entry.count('(') != entry.count(')'):
            return True

        # Check for unbalanced brackets
        if entry.count('[') != entry.count(']'):
            return True

        # Check for unbalanced double quotes (not escaped)
        dq_count = len(re.findall(r'(?<!\\)"', entry))
        if dq_count % 2 != 0:
            return True

        # Check for unbalanced single quotes
        sq_count = len(re.findall(r"(?<!\\)'", entry))
        if sq_count % 2 != 0:
            return True

    return False


def has_shell_quote_single_quote_bug(command: str) -> bool:
    """
    Detects commands containing backslash patterns that exploit shell-quote's
    incorrect handling of backslashes inside single quotes.
    """
    in_single_quote = False
    in_double_quote = False

    i = 0
    while i < len(command):
        char = command[i]

        if char == '\\' and not in_single_quote:
            i += 2
            continue

        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            i += 1
            continue

        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote

            if not in_single_quote:
                # Check trailing backslashes
                backslash_count = 0
                j = i - 1
                while j >= 0 and command[j] == '\\':
                    backslash_count += 1
                    j -= 1

                if backslash_count > 0 and backslash_count % 2 == 1:
                    return True

                if (backslash_count > 0
                        and backslash_count % 2 == 0
                        and "'" in command[i + 1:]):
                    return True

            i += 1
            continue

        i += 1

    return False


def quote(args: List[Any]) -> str:
    """Quote shell arguments safely."""
    result = try_quote_shell_args(list(args))

    if result['success']:
        return result['quoted']

    # Lenient fallback
    try:
        string_args = []
        for arg in args:
            if arg is None:
                string_args.append('None')
            elif isinstance(arg, (str, int, float, bool)):
                string_args.append(str(arg))
            else:
                import json
                string_args.append(json.dumps(arg))

        return _shell_quote(string_args)
    except Exception as e:
        raise RuntimeError('Failed to quote shell arguments safely') from e
