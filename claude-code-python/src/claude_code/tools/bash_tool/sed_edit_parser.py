"""
Sed edit command parser. Ported from BashTool/sedEditParser.ts
Parses `sed -i 's/pattern/replacement/flags' file` into structured SedEditInfo.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SedEditInfo:
    file_path: str
    pattern: str
    replacement: str
    flags: str
    extended_regex: bool


def _simple_shell_split(cmd: str) -> Optional[List[str]]:
    """Very simple shell token splitter (handles basic quoting)."""
    tokens: List[str] = []
    current = []
    i = 0
    in_single = False
    in_double = False
    while i < len(cmd):
        c = cmd[i]
        if c == "'" and not in_double:
            in_single = not in_single
        elif c == '"' and not in_single:
            in_double = not in_double
        elif c == '\\' and not in_single and i + 1 < len(cmd):
            current.append(cmd[i + 1])
            i += 2
            continue
        elif c in (' ', '\t') and not in_single and not in_double:
            if current:
                tokens.append(''.join(current))
                current = []
        else:
            current.append(c)
        i += 1
    if in_single or in_double:
        return None  # Unclosed quote
    if current:
        tokens.append(''.join(current))
    return tokens


def _parse_sed_expression(expression: str) -> Optional[tuple]:
    """Parse s/pattern/replacement/flags from a sed expression string."""
    if not expression.startswith('s/'):
        return None
    rest = expression[2:]
    pattern_chars: List[str] = []
    replacement_chars: List[str] = []
    flags_chars: List[str] = []
    state = 'pattern'
    j = 0
    while j < len(rest):
        c = rest[j]
        if c == '\\' and j + 1 < len(rest):
            if state == 'pattern':
                pattern_chars += [c, rest[j + 1]]
            elif state == 'replacement':
                replacement_chars += [c, rest[j + 1]]
            else:
                flags_chars += [c, rest[j + 1]]
            j += 2
            continue
        if c == '/':
            if state == 'pattern':
                state = 'replacement'
            elif state == 'replacement':
                state = 'flags'
            else:
                return None  # extra slash
            j += 1
            continue
        if state == 'pattern':
            pattern_chars.append(c)
        elif state == 'replacement':
            replacement_chars.append(c)
        else:
            flags_chars.append(c)
        j += 1
    if state not in ('replacement', 'flags'):
        return None
    return ''.join(pattern_chars), ''.join(replacement_chars), ''.join(flags_chars)


def parse_sed_edit_command(command: str) -> Optional[SedEditInfo]:
    """Parse a sed -i 's/pat/rep/flags' file command. Return None if not parseable."""
    trimmed = command.strip()
    if not re.match(r'^\s*sed\s+', trimmed):
        return None
    without_sed = re.sub(r'^\s*sed\s+', '', trimmed)
    tokens = _simple_shell_split(without_sed)
    if tokens is None:
        return None

    has_in_place = False
    extended_regex = False
    expression: Optional[str] = None
    file_path: Optional[str] = None

    i = 0
    while i < len(tokens):
        arg = tokens[i]
        if arg in ('-i', '--in-place'):
            has_in_place = True
            i += 1
            if i < len(tokens) and not tokens[i].startswith('-') and \
               (tokens[i] == '' or tokens[i].startswith('.')):
                i += 1
            continue
        if arg.startswith('-i'):
            has_in_place = True
            i += 1
            continue
        if arg in ('-E', '-r', '--regexp-extended'):
            extended_regex = True
            i += 1
            continue
        if arg in ('-e', '--expression'):
            if i + 1 < len(tokens) and expression is None:
                expression = tokens[i + 1]
                i += 2
                continue
            return None
        if arg.startswith('--expression='):
            if expression is not None:
                return None
            expression = arg[len('--expression='):]
            i += 1
            continue
        if arg.startswith('-'):
            return None  # Unknown flag
        if expression is None:
            expression = arg
        elif file_path is None:
            file_path = arg
        else:
            return None  # Multiple files
        i += 1

    if not has_in_place or not expression or not file_path:
        return None

    parsed = _parse_sed_expression(expression)
    if parsed is None:
        return None
    pattern, replacement, flags = parsed
    return SedEditInfo(file_path=file_path, pattern=pattern,
                       replacement=replacement, flags=flags,
                       extended_regex=extended_regex)


def is_sed_in_place_edit(command: str) -> bool:
    return parse_sed_edit_command(command) is not None
