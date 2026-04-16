"""
Sed command constraints. Ported from BashTool/sedValidation.ts (684 lines → core).
"""
from __future__ import annotations
import re
from typing import List, Optional

_ALLOWED_SAFE_FLAGS = {'-n', '--quiet', '--silent', '-E', '--regexp-extended',
                       '-r', '-z', '--zero-terminated', '--posix', '-i', '--in-place',
                       '-e', '--expression', '-f', '--file'}


def _has_flag(tokens: List[str], flag: str) -> bool:
    for t in tokens:
        if t == flag:
            return True
        if t.startswith('-') and not t.startswith('--') and flag.startswith('-') and len(flag) == 2:
            if flag[1] in t[1:]:
                return True
    return False


def _simple_split(cmd: str) -> Optional[List[str]]:
    """Very basic shell-level split (single-quote aware)."""
    tokens, cur, in_sq = [], [], False
    for c in cmd:
        if c == "'" and not in_sq:
            in_sq = True
        elif c == "'" and in_sq:
            in_sq = False
        elif c in (' ', '\t') and not in_sq:
            if cur:
                tokens.append(''.join(cur))
                cur = []
        else:
            cur.append(c)
    if cur:
        tokens.append(''.join(cur))
    return tokens


def is_line_printing_command(command: str, expressions: List[str]) -> bool:
    """True if `sed -n 'Np'` or similar read-only print command."""
    m = re.match(r'^\s*sed\s+', command)
    if not m:
        return False
    tokens = _simple_split(command[m.end():]) or []
    if not _has_flag(tokens, '-n'):
        return False
    return all(bool(re.match(r'^\d+(,\d+)?p$', e) or re.match(r'^\d+(;\d+p)*p$', e))
               for e in expressions if e)


def sed_command_is_allowed_by_allowlist(command: str, allowed_patterns: List[str]) -> bool:
    """Check if a sed command matches a user-configured allow list."""
    return any(command.strip().startswith(pat) for pat in allowed_patterns)


def has_file_args(command: str) -> bool:
    """Return True if the sed command has explicit file arguments."""
    tokens = _simple_split(re.sub(r'^\s*sed\s+', '', command)) or []
    non_flags = [t for t in tokens if not t.startswith('-') and not t.startswith('s/')]
    return len(non_flags) > 0


def extract_sed_expressions(command: str) -> List[str]:
    """Extract -e expressions from a sed command."""
    tokens = _simple_split(re.sub(r'^\s*sed\s+', '', command)) or []
    exprs: List[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in ('-e', '--expression') and i + 1 < len(tokens):
            exprs.append(tokens[i + 1])
            i += 2
        elif t.startswith('--expression='):
            exprs.append(t[len('--expression='):])
            i += 1
        elif not t.startswith('-'):
            exprs.append(t)
            i += 1
        else:
            i += 1
    return exprs


def check_sed_constraints(command: str, permission_context: dict) -> dict:
    """
    Main entry point for sed permission checking.
    Returns a PermissionResult dict.
    """
    if not command.strip().startswith('sed'):
        return {"behavior": "passthrough", "message": "Not a sed command"}

    exprs = extract_sed_expressions(command)
    if is_line_printing_command(command, exprs):
        return {"behavior": "allow", "updatedInput": {"command": command},
                "decisionReason": {"type": "readonly_sed"}}

    return {"behavior": "passthrough", "message": "sed requires permission check"}
