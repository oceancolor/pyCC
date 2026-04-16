"""
AST-based bash command analysis.

This module provides static analysis of bash commands. It is a Python port of
utils/bash/ast.ts from the Claude Code TypeScript source.

NOTE: The TypeScript version uses tree-sitter WASM for real AST parsing.
The Python port provides the type definitions, constants, and analysis utilities
that do NOT depend on tree-sitter. Functions that require tree-sitter parsing
return 'parse-unavailable' since we don't have a tree-sitter Python binding
configured identically to the TS version.

Ported from utils/bash/ast.ts (2679 lines)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class Redirect:
    """A shell redirect (>, >>, <, etc.)."""
    op: str  # one of: '>' | '>>' | '<' | '<<' | '>&' | '>|' | '<&' | '&>' | '&>>' | '<<<'
    target: str
    fd: Optional[int] = None


@dataclass
class SimpleCommand:
    """A single simple shell command extracted from AST analysis."""
    # argv[0] is the command name, rest are arguments with quotes already resolved
    argv: List[str] = field(default_factory=list)
    # Leading VAR=val assignments
    env_vars: List[Dict[str, str]] = field(default_factory=list)
    # Output/input redirects
    redirects: List[Redirect] = field(default_factory=list)
    # Original source span for this command (for UI display)
    text: str = ''


@dataclass
class ParseForSecuritySimple:
    """Result: command was successfully parsed into simple commands."""
    kind: str = 'simple'
    commands: List[SimpleCommand] = field(default_factory=list)


@dataclass
class ParseForSecurityTooComplex:
    """Result: command is too complex to statically analyze."""
    kind: str = 'too-complex'
    reason: str = ''
    node_type: Optional[str] = None


@dataclass
class ParseForSecurityUnavailable:
    """Result: parser (tree-sitter) is not available."""
    kind: str = 'parse-unavailable'


ParseForSecurityResult = Union[
    ParseForSecuritySimple,
    ParseForSecurityTooComplex,
    ParseForSecurityUnavailable,
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Structural node types that represent composition of commands
STRUCTURAL_TYPES: Set[str] = {
    'program',
    'list',
    'pipeline',
    'redirected_statement',
}

# Operator tokens that separate commands
SEPARATOR_TYPES: Set[str] = {'&&', '||', '|', ';', '&', '|&', '\n'}

# Placeholder used in outer argv when a $() is recursively extracted
CMDSUB_PLACEHOLDER = '__CMDSUB_OUTPUT__'

# Placeholder for simple_expansion ($VAR) references to tracked variables
VAR_PLACEHOLDER = '__TRACKED_VAR__'


def contains_any_placeholder(value: str) -> bool:
    """Check if value contains any placeholder (exact or embedded)."""
    return CMDSUB_PLACEHOLDER in value or VAR_PLACEHOLDER in value


# Unquoted $VAR in bash undergoes word-splitting and pathname expansion
BARE_VAR_UNSAFE_RE = re.compile(r'[ \t\n*?\[]')

# stdbuf flag forms
STDBUF_SHORT_SEP_RE = re.compile(r'^-[ioe]$')
STDBUF_SHORT_FUSED_RE = re.compile(r'^-[ioe].')
STDBUF_LONG_RE = re.compile(r'^--(input|output|error)=')

# Known-safe environment variables that bash sets automatically
SAFE_ENV_VARS: Set[str] = {
    'HOME', 'PWD', 'OLDPWD', 'USER', 'LOGNAME', 'SHELL', 'PATH',
    'HOSTNAME', 'UID', 'EUID', 'PPID', 'RANDOM', 'SECONDS', 'LINENO',
    'TMPDIR', 'BASH_VERSION', 'BASHPID', 'SHLVL', 'HISTFILE', 'IFS',
}

# Special shell variables ($?, $$, $!, $#, $0-$9)
SPECIAL_VAR_NAMES: Set[str] = {'?', '$', '!', '#', '0', '-'}

# Node types that mean "this command cannot be statically analyzed"
DANGEROUS_TYPES: Set[str] = {
    'command_substitution',
    'process_substitution',
    'expansion',
    'simple_expansion',
    'brace_expression',
    'subshell',
    'compound_statement',
    'for_statement',
    'while_statement',
    'until_statement',
    'if_statement',
    'case_statement',
    'function_definition',
    'test_command',
    'ansi_c_string',
    'translated_string',
    'herestring_redirect',
    'heredoc_redirect',
}

DANGEROUS_TYPE_IDS = list(DANGEROUS_TYPES)


def node_type_id(node_type: Optional[str]) -> int:
    """Get numeric ID for a node type (for analytics)."""
    if not node_type:
        return -2
    if node_type == 'ERROR':
        return -1
    try:
        idx = DANGEROUS_TYPE_IDS.index(node_type)
        return idx + 1
    except ValueError:
        return 0


# Redirect operator tokens → canonical operator
REDIRECT_OPS: Dict[str, str] = {
    '>': '>',
    '>>': '>>',
    '<': '<',
    '>&': '>&',
    '<&': '<&',
    '>|': '>|',
    '&>': '&>',
    '&>>': '&>>',
    '<<<': '<<<',
}

# Brace expansion pattern: {a,b} or {a..b}
BRACE_EXPANSION_RE = re.compile(r'\{[^{}\s]*(,|\.\.)[^{}\s]*\}')

# Control characters that bash silently drops but confuse static analysis
CONTROL_CHAR_RE = re.compile(r'[\x00-\x08\x0B-\x1F\x7F]')

# Unicode whitespace beyond ASCII
UNICODE_WHITESPACE_RE = re.compile(
    r'[\u00A0\u1680\u2000-\u200B\u2028\u2029\u202F\u205F\u3000\uFEFF]'
)

# Backslash immediately before whitespace
BACKSLASH_WHITESPACE_RE = re.compile(r'\\[ \t]|[^ \t\n\\]\\\n')

# Zsh dynamic named directory expansion
ZSH_TILDE_BRACKET_RE = re.compile(r'~\[')

# Zsh EQUALS expansion
ZSH_EQUALS_EXPANSION_RE = re.compile(r'(?:^|[\s;&|])=[a-zA-Z_]')

# Brace character combined with quote characters
BRACE_WITH_QUOTE_RE = re.compile(r'\{[^}]*[\'"]')

# Newline + hash (bash comment marker) in a value
NEWLINE_HASH_RE = re.compile(r'\n\s*#')

# $VAR pattern in text (for detecting when argv was rebuilt)
DOLLAR_IDENT_RE = re.compile(r'\$[A-Za-z_]')

# /proc/self/environ check
PROC_ENVIRON_RE = re.compile(r'/proc/self/environ')

# Arithmetic leaf pattern for walkArithmetic
ARITH_LEAF_RE = re.compile(
    r'^(?:[0-9]+|0[xX][0-9a-fA-F]+|[0-9]+#[0-9a-zA-Z]+|[-+*/%^&|~!<>=?:(),]+|<<|>>|\*\*|&&|\|\||[<>=!]=|\$\(\(|\)\))$'
)

DOLLAR = chr(0x24)


def mask_braces_in_quoted_contexts(cmd: str) -> str:
    """
    Mask `{` characters inside single- or double-quoted contexts.

    Brace expansion cannot occur inside quotes, so masking `{` there
    prevents false positives in BRACE_WITH_QUOTE_RE checks.
    """
    if '{' not in cmd:
        return cmd  # Fast path: no braces

    out = []
    in_single = False
    in_double = False
    i = 0

    while i < len(cmd):
        c = cmd[i]
        if in_single:
            # Single quotes: no escapes, `'` always terminates
            if c == "'":
                in_single = False
            out.append(' ' if c == '{' else c)
            i += 1
        elif in_double:
            # Double quotes: `\` escapes `"` and `\`
            if c == '\\' and i + 1 < len(cmd) and cmd[i + 1] in ('"', '\\'):
                out.append(c)
                out.append(cmd[i + 1])
                i += 2
            else:
                if c == '"':
                    in_double = False
                out.append(' ' if c == '{' else c)
                i += 1
        else:
            # Unquoted: `\` escapes any next char
            if c == '\\' and i + 1 < len(cmd):
                out.append(c)
                out.append(cmd[i + 1])
                i += 2
            else:
                if c == "'":
                    in_single = True
                elif c == '"':
                    in_double = True
                out.append(c)
                i += 1

    return ''.join(out)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_for_security(cmd: str) -> ParseForSecurityResult:
    """
    Parse a bash command string and extract a flat list of simple commands.

    Returns:
        - 'simple' with commands if successfully parsed
        - 'too-complex' if the command uses features we can't statically analyze
        - 'parse-unavailable' if tree-sitter is not available (Python always returns this
          for complex commands since we don't have a full tree-sitter binding)

    NOTE: The Python port does not have a tree-sitter binding. This function
    runs the pre-checks (which are pure string analysis) and returns
    'parse-unavailable' for commands that would require AST walking.
    """
    if cmd == '':
        return ParseForSecuritySimple(commands=[])

    return parse_for_security_from_ast(cmd, None)


def parse_for_security_from_ast(
    cmd: str,
    root: Any,  # Node | PARSE_ABORTED | None
) -> ParseForSecurityResult:
    """
    Run pre-checks and, if root is provided, walk the AST.

    Pre-checks catch tree-sitter/bash differentials. If root is None,
    returns parse-unavailable after pre-checks.
    """
    # Pre-checks
    if CONTROL_CHAR_RE.search(cmd):
        return ParseForSecurityTooComplex(reason='Contains control characters')
    if UNICODE_WHITESPACE_RE.search(cmd):
        return ParseForSecurityTooComplex(reason='Contains Unicode whitespace')
    if BACKSLASH_WHITESPACE_RE.search(cmd):
        return ParseForSecurityTooComplex(reason='Contains backslash-escaped whitespace')
    if ZSH_TILDE_BRACKET_RE.search(cmd):
        return ParseForSecurityTooComplex(reason='Contains zsh ~[ dynamic directory syntax')
    if ZSH_EQUALS_EXPANSION_RE.search(cmd):
        return ParseForSecurityTooComplex(reason='Contains zsh =cmd equals expansion')
    if BRACE_WITH_QUOTE_RE.search(mask_braces_in_quoted_contexts(cmd)):
        return ParseForSecurityTooComplex(
            reason='Contains brace with quote character (expansion obfuscation)'
        )

    trimmed = cmd.strip()
    if trimmed == '':
        return ParseForSecuritySimple(commands=[])

    if root is None:
        # No tree-sitter available — return parse-unavailable
        return ParseForSecurityUnavailable()

    # If root is the PARSE_ABORTED sentinel
    if root == 'PARSE_ABORTED':
        return ParseForSecurityTooComplex(
            reason='Parser aborted (timeout or resource limit) — possible adversarial input',
            node_type='PARSE_ABORT',
        )

    # Walk the AST (requires tree-sitter Node object)
    # In the Python port this path is only reachable if a caller provides a
    # tree-sitter node — which the current Python codebase does not do.
    return ParseForSecurityUnavailable()


# ---------------------------------------------------------------------------
# Semantic analysis (does not require tree-sitter)
# ---------------------------------------------------------------------------

# Eval-like builtins that execute their arguments as shell code
EVAL_LIKE_BUILTINS: Set[str] = {
    'eval', 'exec', 'source', '.', 'bash', 'sh', 'zsh', 'fish', 'dash',
    'ksh', 'csh', 'tcsh',
}

# Zsh dangerous builtins
ZSH_DANGEROUS_BUILTINS: Set[str] = {
    'zmodload', 'autoload', 'zcompile',
}

# Commands that affect shell execution environment dangerously
# PS4 value safety — only ${VAR} references and safe chars
PS4_SAFE_RE = re.compile(r'^[^$`\\]*(?:\$\{[A-Za-z_][A-Za-z0-9_]*\}[^$`\\]*)*$')

# Subscript eval flags for declare/typeset/local
SUBSCRIPT_EVAL_FLAGS_RE = re.compile(r'^-[a-zA-Z]*[niaA]')

# Valid variable identifier
VAR_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def check_semantics(
    commands: List[SimpleCommand],
    raw_cmd: str,
) -> Optional[ParseForSecurityTooComplex]:
    """
    Run semantic checks on a list of extracted SimpleCommands.

    These checks operate on the argv[] values rather than the AST structure.
    Returns a too-complex result if any check fails, or None if all pass.

    This is called AFTER the AST walk to validate the extracted commands.
    """
    for cmd_obj in commands:
        argv = cmd_obj.argv
        if not argv:
            continue

        cmd0 = argv[0]

        # Defense-in-depth: argv[0] should never be a placeholder
        if cmd0 == CMDSUB_PLACEHOLDER or cmd0 == VAR_PLACEHOLDER:
            return ParseForSecurityTooComplex(
                reason=f'argv[0] is a placeholder ({cmd0})',
                node_type='placeholder',
            )

        # Eval-like builtins — `eval`, `exec`, `source`, etc.
        if cmd0 in EVAL_LIKE_BUILTINS:
            return ParseForSecurityTooComplex(
                reason=f'Command {cmd0!r} executes its arguments as shell code',
                node_type='eval_like',
            )

        # Zsh dangerous builtins
        if cmd0 in ZSH_DANGEROUS_BUILTINS:
            return ParseForSecurityTooComplex(
                reason=f'Zsh builtin {cmd0!r} can execute arbitrary code',
                node_type='zsh_dangerous',
            )

        # Check for /proc/self/environ in argv
        for arg in argv:
            if PROC_ENVIRON_RE.search(arg):
                return ParseForSecurityTooComplex(
                    reason='Command accesses /proc/self/environ',
                    node_type='proc_environ',
                )

        # Newline + hash in any argv value (bash comment injection)
        for arg in argv:
            if NEWLINE_HASH_RE.search(arg):
                return ParseForSecurityTooComplex(
                    reason='Argument contains newline followed by # (comment injection)',
                    node_type='newline_hash',
                )

    return None


# ---------------------------------------------------------------------------
# Utility: strip raw string (single-quoted) delimiters
# ---------------------------------------------------------------------------


def strip_raw_string(text: str) -> str:
    """Remove surrounding single quotes from a raw_string node text."""
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1]
    return text


# ---------------------------------------------------------------------------
# Export for type checking compatibility
# ---------------------------------------------------------------------------

__all__ = [
    'Redirect',
    'SimpleCommand',
    'ParseForSecurityResult',
    'ParseForSecuritySimple',
    'ParseForSecurityTooComplex',
    'ParseForSecurityUnavailable',
    'CMDSUB_PLACEHOLDER',
    'VAR_PLACEHOLDER',
    'STRUCTURAL_TYPES',
    'SEPARATOR_TYPES',
    'DANGEROUS_TYPES',
    'SAFE_ENV_VARS',
    'SPECIAL_VAR_NAMES',
    'REDIRECT_OPS',
    'BRACE_EXPANSION_RE',
    'CONTROL_CHAR_RE',
    'UNICODE_WHITESPACE_RE',
    'BACKSLASH_WHITESPACE_RE',
    'ZSH_TILDE_BRACKET_RE',
    'ZSH_EQUALS_EXPANSION_RE',
    'BRACE_WITH_QUOTE_RE',
    'NEWLINE_HASH_RE',
    'PROC_ENVIRON_RE',
    'ARITH_LEAF_RE',
    'DOLLAR',
    'EVAL_LIKE_BUILTINS',
    'ZSH_DANGEROUS_BUILTINS',
    'BARE_VAR_UNSAFE_RE',
    'STDBUF_SHORT_SEP_RE',
    'STDBUF_SHORT_FUSED_RE',
    'STDBUF_LONG_RE',
    'contains_any_placeholder',
    'mask_braces_in_quoted_contexts',
    'parse_for_security',
    'parse_for_security_from_ast',
    'check_semantics',
    'strip_raw_string',
    'node_type_id',
]
