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
    'eval',
    'source',
    '.',
    'exec',
    'command',
    'builtin',
    'fc',
    # `coproc rm -rf /` spawns rm as a coprocess
    'coproc',
    # Zsh precommand modifiers
    'noglob',
    'nocorrect',
    # `trap 'cmd' SIGNAL` — cmd runs as shell code on signal/exit
    'trap',
    # `enable -f /path/lib.so name` — dlopen arbitrary .so
    'enable',
    # `mapfile -C callback` / `readarray -C callback`
    'mapfile',
    'readarray',
    # `hash -p /path cmd` — poisons bash command-lookup cache
    'hash',
    # bind/complete/compgen callbacks
    'bind',
    'complete',
    'compgen',
    # `alias name='cmd'`
    'alias',
    # `let EXPR` arithmetically evaluates EXPR
    'let',
}

# Zsh dangerous builtins (full list from TS source)
ZSH_DANGEROUS_BUILTINS: Set[str] = {
    'zmodload',
    'emulate',
    'sysopen',
    'sysread',
    'syswrite',
    'sysseek',
    'zpty',
    'ztcp',
    'zsocket',
    'zf_rm',
    'zf_mv',
    'zf_ln',
    'zf_chmod',
    'zf_chown',
    'zf_mkdir',
    'zf_rmdir',
    'zf_chgrp',
}

# PS4 value safety — only ${VAR} references and safe chars
PS4_SAFE_RE = re.compile(r'^[^$`\\]*(?:\$\{[A-Za-z_][A-Za-z0-9_]*\}[^$`\\]*)*$')

# Subscript eval flags for declare/typeset/local
SUBSCRIPT_EVAL_FLAGS_RE = re.compile(r'^-[a-zA-Z]*[niaA]')

# Valid variable identifier
VAR_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

# Builtins that re-parse a NAME operand and arithmetically evaluate subscripts.
# Maps: builtin name -> set of flags whose NEXT argument is a NAME.
SUBSCRIPT_EVAL_FLAGS: Dict[str, Set[str]] = {
    'test': {'-v', '-R'},
    '[': {'-v', '-R'},
    '[[': {'-v', '-R'},
    'printf': {'-v'},
    'read': {'-a'},
    'unset': {'-v'},
    'wait': {'-p'},
}

# `[[ ARG OP ARG ]]` arithmetic comparison operators — both operands are
# arithmetically evaluated (array subscript eval risk).
TEST_ARITH_CMP_OPS: Set[str] = {'-eq', '-ne', '-lt', '-le', '-gt', '-ge'}

# Builtins where EVERY non-flag positional argument is a NAME re-parsed by bash.
BARE_SUBSCRIPT_NAME_BUILTINS: Set[str] = {'read', 'unset'}

# `read` flags whose NEXT argument is data (not a NAME variable target).
READ_DATA_FLAGS: Set[str] = {'-p', '-d', '-n', '-N', '-t', '-u', '-i'}

# Shell reserved keywords — if one appears as argv[0], tree-sitter mis-parsed.
SHELL_KEYWORDS: Set[str] = {
    'if', 'then', 'else', 'elif', 'fi',
    'for', 'while', 'until', 'do', 'done',
    'case', 'esac', 'in',
    'function',
    'select',
    'time',
    '{', '}',
    '!',
}


# ---------------------------------------------------------------------------
# SemanticCheckResult type (mirrors TS: {ok: true} | {ok: false, reason: str})
# ---------------------------------------------------------------------------

@dataclass
class SemanticCheckOk:
    """Semantic check passed."""
    ok: bool = True


@dataclass
class SemanticCheckFail:
    """Semantic check failed with a reason."""
    ok: bool = False
    reason: str = ''


SemanticCheckResult = Union[SemanticCheckOk, SemanticCheckFail]


def check_semantics(
    commands: List[SimpleCommand],
    raw_cmd: str = '',
) -> Optional[ParseForSecurityTooComplex]:
    """
    Run semantic checks on a list of extracted SimpleCommands.

    These checks operate on the argv[] values rather than the AST structure.
    Returns a too-complex result if any check fails, or None if all pass.

    This is called AFTER the AST walk to validate the extracted commands.
    """
    result = check_semantics_full(commands)
    if not result.ok:
        # Cast SemanticCheckFail reason to ParseForSecurityTooComplex
        return ParseForSecurityTooComplex(
            reason=result.reason,  # type: ignore[union-attr]
        )
    return None


# jq dangerous flag regex (mirrors TS)
_JQ_DANGEROUS_FLAGS_RE = re.compile(
    r'^(?:-[fL](?:$|[^A-Za-z])|--(?:from-file|rawfile|slurpfile|library-path)(?:$|=))'
)

# timeout duration regex
_TIMEOUT_DURATION_RE = re.compile(r'^\d+(?:\.\d+)?[smhd]?$')


def _strip_wrapper_argv(argv: List[str]) -> List[str]:
    """
    Strip safe wrapper commands from argv, returning the inner argv.

    Handles: time, nohup, timeout [opts] DUR, nice [-n N], env [VAR=val...],
    stdbuf [flags].

    Mirrors the wrapper-stripping loop in checkSemantics (TS ast.ts).
    """
    a = list(argv)
    while a:
        if a[0] in ('time', 'nohup'):
            a = a[1:]

        elif a[0] == 'timeout':
            i = 1
            ok = True
            while i < len(a):
                arg = a[i]
                if arg in ('--foreground', '--preserve-status', '--verbose'):
                    i += 1
                elif re.match(r'^--(?:kill-after|signal)=[A-Za-z0-9_.+-]+$', arg):
                    i += 1
                elif arg in ('--kill-after', '--signal') and i + 1 < len(a) and re.match(r'^[A-Za-z0-9_.+-]+$', a[i + 1]):
                    i += 2
                elif arg.startswith('--'):
                    ok = False
                    break
                elif arg == '-v':
                    i += 1
                elif arg in ('-k', '-s') and i + 1 < len(a) and re.match(r'^[A-Za-z0-9_.+-]+$', a[i + 1]):
                    i += 2
                elif re.match(r'^-[ks][A-Za-z0-9_.+-]+$', arg):
                    i += 1
                elif arg.startswith('-'):
                    ok = False
                    break
                else:
                    break
            if not ok:
                break
            if i < len(a) and _TIMEOUT_DURATION_RE.match(a[i]):
                a = a[i + 1:]
            elif i < len(a):
                # non-matching duration — fail open (leave as-is)
                break
            else:
                break

        elif a[0] == 'nice':
            if len(a) > 2 and a[1] == '-n' and re.match(r'^-?\d+$', a[2]):
                a = a[3:]
            elif len(a) > 1 and re.match(r'^-\d+$', a[1]):
                a = a[2:]
            elif len(a) > 1 and re.search(r'[$(`]', a[1]):
                # expansion in argument — can't determine wrapped cmd
                break
            else:
                a = a[1:]

        elif a[0] == 'env':
            i = 1
            ok = True
            while i < len(a):
                arg = a[i]
                if '=' in arg and not arg.startswith('-'):
                    i += 1
                elif arg in ('-i', '-0', '-v'):
                    i += 1
                elif arg == '-u' and i + 1 < len(a):
                    i += 2
                elif arg.startswith('-'):
                    ok = False
                    break
                else:
                    break
            if not ok:
                break
            if i < len(a):
                a = a[i:]
            else:
                break

        elif a[0] == 'stdbuf':
            i = 1
            ok = True
            while i < len(a):
                arg = a[i]
                if STDBUF_SHORT_SEP_RE.match(arg) and i + 1 < len(a):
                    i += 2
                elif STDBUF_SHORT_FUSED_RE.match(arg):
                    i += 1
                elif STDBUF_LONG_RE.match(arg):
                    i += 1
                elif arg.startswith('-'):
                    ok = False
                    break
                else:
                    break
            if not ok or i <= 1 or i >= len(a):
                break
            a = a[i:]

        else:
            break

    return a


def check_semantics_full(commands: List[SimpleCommand]) -> SemanticCheckResult:
    """
    Full post-argv semantic checks — mirrors checkSemantics() in TS ast.ts.

    Operates on the argv[] values (not the raw source). Catches:
    - empty/placeholder command names
    - wrapper-command stripping (timeout, nohup, nice, env, stdbuf)
    - eval-like builtins
    - zsh dangerous builtins
    - subscript-eval attacks (SUBSCRIPT_EVAL_FLAGS, TEST_ARITH_CMP_OPS,
      BARE_SUBSCRIPT_NAME_BUILTINS)
    - shell keyword mis-parses
    - newline+# injection
    - jq system() and dangerous flags
    - /proc/*/environ access

    Returns SemanticCheckOk on success, SemanticCheckFail with a reason.
    """
    for cmd_obj in commands:
        # Strip safe wrapper commands so we check the wrapped command
        a = _strip_wrapper_argv(cmd_obj.argv)

        if not a:
            continue

        name = a[0]

        # Empty command name
        if name == '':
            return SemanticCheckFail(
                reason='Empty command name — argv[0] may not reflect what bash runs'
            )

        # Defense-in-depth: argv[0] should never be a placeholder
        if CMDSUB_PLACEHOLDER in name or VAR_PLACEHOLDER in name:
            return SemanticCheckFail(
                reason='Command name is runtime-determined (placeholder argv[0])'
            )

        # Fragment detection
        if name.startswith('-') or name.startswith('|') or name.startswith('&'):
            return SemanticCheckFail(
                reason='Command appears to be an incomplete fragment'
            )

        # SUBSCRIPT_EVAL_FLAGS: builtins where a flag's next arg is a NAME
        # that bash re-parses with arithmetic subscript evaluation
        danger_flags = SUBSCRIPT_EVAL_FLAGS.get(name)
        if danger_flags is not None:
            for i in range(1, len(a)):
                arg = a[i]
                # Separate form: `-v` then NAME in next arg
                if arg in danger_flags and i + 1 < len(a) and '[' in a[i + 1]:
                    return SemanticCheckFail(
                        reason=(
                            f"'{name} {arg}' operand contains array subscript "
                            f"— bash evaluates $(cmd) in subscripts"
                        )
                    )
                # Combined short flags: `-ra` merges multiple flags
                if (len(arg) > 2 and arg[0] == '-' and arg[1] != '-'
                        and '[' not in arg):
                    for flag in danger_flags:
                        if len(flag) == 2 and flag[1] in arg[1:]:
                            if i + 1 < len(a) and '[' in a[i + 1]:
                                return SemanticCheckFail(
                                    reason=(
                                        f"'{name} {flag}' (combined in '{arg}') "
                                        f"operand contains array subscript "
                                        f"— bash evaluates $(cmd) in subscripts"
                                    )
                                )
                # Fused form: `-vNAME` in one arg
                for flag in danger_flags:
                    if (len(flag) == 2 and arg.startswith(flag)
                            and len(arg) > 2 and '[' in arg):
                        return SemanticCheckFail(
                            reason=(
                                f"'{name} {flag}' (fused) operand contains array subscript "
                                f"— bash evaluates $(cmd) in subscripts"
                            )
                        )

        # TEST_ARITH_CMP_OPS: `[[ ARG OP ARG ]]` arithmetic comparisons
        if name == '[[':
            for i in range(2, len(a)):
                if a[i] in TEST_ARITH_CMP_OPS:
                    prev = a[i - 1] if i - 1 >= 0 else ''
                    nxt = a[i + 1] if i + 1 < len(a) else ''
                    if '[' in prev or '[' in nxt:
                        return SemanticCheckFail(
                            reason=(
                                f"'[[ ... {a[i]} ... ]]' operand contains array subscript "
                                f"— bash arithmetically evaluates $(cmd) in subscripts"
                            )
                        )

        # BARE_SUBSCRIPT_NAME_BUILTINS: every positional arg is a NAME
        if name in BARE_SUBSCRIPT_NAME_BUILTINS:
            skip_next = False
            for i in range(1, len(a)):
                arg = a[i]
                if skip_next:
                    skip_next = False
                    continue
                if arg.startswith('-'):
                    if name == 'read':
                        if arg in READ_DATA_FLAGS:
                            skip_next = True
                        elif len(arg) > 2 and arg[1] != '-':
                            # Combined short flags like `-rp`
                            for j in range(1, len(arg)):
                                if ('-' + arg[j]) in READ_DATA_FLAGS:
                                    if j == len(arg) - 1:
                                        skip_next = True
                                    break
                    continue
                if '[' in arg:
                    return SemanticCheckFail(
                        reason=(
                            f"'{name}' positional NAME '{arg}' contains array subscript "
                            f"— bash evaluates $(cmd) in subscripts"
                        )
                    )

        # Shell keywords as argv[0] indicate a tree-sitter mis-parse
        if name in SHELL_KEYWORDS:
            return SemanticCheckFail(
                reason=f"Shell keyword '{name}' as command name — tree-sitter mis-parse"
            )

        # Newline+# injection in argv, envVars, redirects
        for arg in cmd_obj.argv:
            if '\n' in arg and NEWLINE_HASH_RE.search(arg):
                return SemanticCheckFail(
                    reason=(
                        'Newline followed by # inside a quoted argument '
                        'can hide arguments from path validation'
                    )
                )
        for ev in cmd_obj.env_vars:
            val = ev.get('value', '') if isinstance(ev, dict) else ''
            if '\n' in val and NEWLINE_HASH_RE.search(val):
                return SemanticCheckFail(
                    reason=(
                        'Newline followed by # inside an env var value '
                        'can hide arguments from path validation'
                    )
                )
        for r in cmd_obj.redirects:
            if '\n' in r.target and NEWLINE_HASH_RE.search(r.target):
                return SemanticCheckFail(
                    reason=(
                        'Newline followed by # inside a redirect target '
                        'can hide arguments from path validation'
                    )
                )

        # jq system() and dangerous flags
        if name == 'jq':
            for arg in a:
                if re.search(r'\bsystem\s*\(', arg):
                    return SemanticCheckFail(
                        reason=(
                            'jq command contains system() function '
                            'which executes arbitrary commands'
                        )
                    )
            if any(_JQ_DANGEROUS_FLAGS_RE.match(arg) for arg in a):
                return SemanticCheckFail(
                    reason=(
                        'jq command contains dangerous flags that could '
                        'execute code or read arbitrary files'
                    )
                )

        # Zsh dangerous builtins
        if name in ZSH_DANGEROUS_BUILTINS:
            return SemanticCheckFail(
                reason=f"Zsh builtin '{name}' can bypass security checks"
            )

        # Eval-like builtins
        if name in EVAL_LIKE_BUILTINS:
            # `command -v foo` / `command -V foo` are safe existence checks
            if name == 'command' and len(a) > 1 and a[1] in ('-v', '-V'):
                pass  # fall through
            elif (name == 'fc'
                  and not any(re.search(r'^-[^-]*[es]', arg) for arg in a[1:])):
                pass  # fc -l (list history) is safe
            elif (name == 'compgen'
                  and not any(re.search(r'^-[^-]*[CFW]', arg) for arg in a[1:])):
                pass  # compgen -c/-f/-v only lists completions
            else:
                return SemanticCheckFail(
                    reason=f"'{name}' evaluates arguments as shell code"
                )

        # /proc/*/environ access
        for arg in cmd_obj.argv:
            if '/proc/' in arg and PROC_ENVIRON_RE.search(arg):
                return SemanticCheckFail(
                    reason='Accesses /proc/*/environ which may expose secrets'
                )
        for r in cmd_obj.redirects:
            if '/proc/' in r.target and PROC_ENVIRON_RE.search(r.target):
                return SemanticCheckFail(
                    reason='Accesses /proc/*/environ which may expose secrets'
                )

    return SemanticCheckOk()


# ---------------------------------------------------------------------------
# Utility: strip raw string (single-quoted) delimiters
# ---------------------------------------------------------------------------


def strip_raw_string(text: str) -> str:
    """Remove surrounding single quotes from a raw_string node text."""
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1]
    return text


# ---------------------------------------------------------------------------
# Variable scope helpers (mirror TS applyVarToScope)
# ---------------------------------------------------------------------------

def apply_var_to_scope(
    var_scope: Dict[str, str],
    ev: Dict[str, Any],
) -> None:
    """
    Apply a variable assignment to the scope, handling `+=` append semantics.

    SECURITY: If either side (existing value or appended value) contains a
    placeholder, the result is non-literal — store VAR_PLACEHOLDER so later
    $VAR correctly rejects as bare arg.

    Mirrors applyVarToScope() in TS ast.ts.
    """
    name = ev.get('name', '')
    value = ev.get('value', '')
    is_append = ev.get('is_append', False)

    existing = var_scope.get(name, '')
    combined = (existing + value) if is_append else value
    var_scope[name] = VAR_PLACEHOLDER if contains_any_placeholder(combined) else combined


# ---------------------------------------------------------------------------
# Tree-sitter AST walking stubs
# (Full implementation requires tree-sitter Python bindings.
#  These stubs define the interface; the parse_for_security function
#  returns parse-unavailable when no AST root is provided.)
# ---------------------------------------------------------------------------

def _too_complex(node_type: Optional[str], reason: str = '') -> ParseForSecurityTooComplex:
    """
    Construct a too-complex result for an unhandled or dangerous node type.

    Mirrors tooComplex(node) in TS ast.ts.
    """
    if not reason:
        if node_type == 'ERROR':
            reason = 'Parse error'
        elif node_type in DANGEROUS_TYPES:
            reason = f'Contains {node_type}'
        else:
            reason = f'Unhandled node type: {node_type}'
    return ParseForSecurityTooComplex(reason=reason, node_type=node_type)


def walk_program(
    root: Any,
    var_scope: Optional[Dict[str, str]] = None,
) -> ParseForSecurityResult:
    """
    Walk an AST program root and collect simple commands.

    Requires a tree-sitter Node as `root`. Returns parse-unavailable if root
    is None. Mirrors walkProgram() in TS ast.ts.

    NOTE: In the Python port, tree-sitter parsing is not available, so this
    function will only be called when an external tree-sitter binding provides
    a Node object.
    """
    if root is None:
        return ParseForSecurityUnavailable()
    # Full AST walking is not implemented without tree-sitter bindings.
    return ParseForSecurityUnavailable()


def resolve_simple_expansion(
    var_name: str,
    var_scope: Dict[str, str],
    inside_string: bool,
    is_special: bool = False,
) -> Union[str, ParseForSecurityTooComplex]:
    """
    Resolve a simple $VAR expansion to its static value (or a placeholder).

    @param var_name: The variable name (without leading $).
    @param var_scope: Current variable scope mapping name → value.
    @param inside_string: True when $VAR is inside a double-quoted string.
    @param is_special: True for special_variable_name nodes ($?, $$, etc.).

    Returns:
    - The literal value if tracked as a pure literal
    - VAR_PLACEHOLDER if the var is tracked-but-dynamic or safe-env
    - ParseForSecurityTooComplex if the var is unknown/unsafe

    Mirrors resolveSimpleExpansion() in TS ast.ts.
    """
    # Tracked vars: return the stored value or placeholder
    tracked_value = var_scope.get(var_name)
    if tracked_value is not None:
        if contains_any_placeholder(tracked_value):
            # Non-literal: bare → reject, inside string → VAR_PLACEHOLDER
            if not inside_string:
                return _too_complex('simple_expansion',
                                    f'Variable {var_name!r} has non-literal value')
            return VAR_PLACEHOLDER
        # Pure literal value
        if not inside_string:
            # Bare arg: reject if empty or contains IFS/glob chars
            if tracked_value == '':
                return _too_complex('simple_expansion',
                                    f'Variable {var_name!r} is empty')
            if BARE_VAR_UNSAFE_RE.search(tracked_value):
                return _too_complex('simple_expansion',
                                    f'Variable {var_name!r} contains word-split/glob chars')
        return tracked_value

    # SAFE_ENV_VARS + special vars: only safe inside strings
    if inside_string:
        if var_name in SAFE_ENV_VARS:
            return VAR_PLACEHOLDER
        if is_special and (
            var_name in SPECIAL_VAR_NAMES or var_name.isdigit()
        ):
            return VAR_PLACEHOLDER

    return _too_complex('simple_expansion',
                        f'Unresolvable variable reference ${var_name}')


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
    'SemanticCheckResult',
    'SemanticCheckOk',
    'SemanticCheckFail',
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
    'SUBSCRIPT_EVAL_FLAGS',
    'TEST_ARITH_CMP_OPS',
    'BARE_SUBSCRIPT_NAME_BUILTINS',
    'READ_DATA_FLAGS',
    'SHELL_KEYWORDS',
    'BARE_VAR_UNSAFE_RE',
    'STDBUF_SHORT_SEP_RE',
    'STDBUF_SHORT_FUSED_RE',
    'STDBUF_LONG_RE',
    'contains_any_placeholder',
    'mask_braces_in_quoted_contexts',
    'parse_for_security',
    'parse_for_security_from_ast',
    'check_semantics',
    'check_semantics_full',
    'strip_raw_string',
    'node_type_id',
    'apply_var_to_scope',
    'resolve_simple_expansion',
    'walk_program',
    '_too_complex',
    '_strip_wrapper_argv',
]
