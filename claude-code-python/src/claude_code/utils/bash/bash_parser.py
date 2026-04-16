"""
Pure-Python bash parser producing tree-sitter-bash-compatible ASTs.

Downstream code in parser.py, ast.py, prefix.py, ParsedCommand.py walks this
by field name. startIndex/endIndex are UTF-8 BYTE offsets (not string indices).

Grammar reference: tree-sitter-bash. Validated against a 3449-input golden
corpus generated from the WASM parser.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ───────────────────────────── AST Node ─────────────────────────────


@dataclass
class TsNode:
    type: str
    text: str
    startIndex: int
    endIndex: int
    children: List["TsNode"]


# ───────────────────────────── Constants ─────────────────────────────

PARSE_TIMEOUT_MS = 50
MAX_NODES = 50_000

SPECIAL_VARS = set(["?", "$", "@", "*", "#", "-", "!", "_"])

DECL_KEYWORDS = set(["export", "declare", "typeset", "readonly", "local"])

SHELL_KEYWORDS = set([
    "if", "then", "elif", "else", "fi",
    "while", "until", "for", "in", "do", "done",
    "case", "esac", "function", "select",
])


# ───────────────────────────── Public API ─────────────────────────────


def ensure_parser_initialized():
    """No-op: pure-Python parser needs no async init. Kept for API compatibility."""
    pass


def get_parser_module():
    """Always succeeds — pure-Python needs no init."""
    return {"parse": parse_source}


def parse_source(source: str, timeout_ms: float = None) -> Optional[TsNode]:
    """Parse bash source and return a TsNode AST, or None on timeout/error."""
    if timeout_ms is None:
        timeout_ms = PARSE_TIMEOUT_MS
    L = _make_lexer(source)
    src_bytes = _byte_length_utf8(source)
    P = _ParseState(
        L=L,
        src=source,
        src_bytes=src_bytes,
        is_ascii=(src_bytes == len(source)),
        node_count=0,
        deadline=time.monotonic() + timeout_ms / 1000.0,
        aborted=False,
        in_backtick=0,
        stop_token=None,
    )
    try:
        program = _parse_program(P)
        if P.aborted:
            return None
        return program
    except Exception:
        return None


# ───────────────────────────── Tokenizer ─────────────────────────────

# Token types (string constants matching TS TokenType)
TOKEN_WORD = "WORD"
TOKEN_NUMBER = "NUMBER"
TOKEN_OP = "OP"
TOKEN_NEWLINE = "NEWLINE"
TOKEN_COMMENT = "COMMENT"
TOKEN_DQUOTE = "DQUOTE"
TOKEN_SQUOTE = "SQUOTE"
TOKEN_ANSI_C = "ANSI_C"
TOKEN_DOLLAR = "DOLLAR"
TOKEN_DOLLAR_PAREN = "DOLLAR_PAREN"
TOKEN_DOLLAR_BRACE = "DOLLAR_BRACE"
TOKEN_DOLLAR_DPAREN = "DOLLAR_DPAREN"
TOKEN_BACKTICK = "BACKTICK"
TOKEN_LT_PAREN = "LT_PAREN"
TOKEN_GT_PAREN = "GT_PAREN"
TOKEN_EOF = "EOF"


@dataclass
class _Token:
    type: str
    value: str
    start: int   # UTF-8 byte offset
    end: int     # UTF-8 byte offset


@dataclass
class _HeredocPending:
    delim: str
    strip_tabs: bool
    quoted: bool
    body_start: int = 0
    body_end: int = 0
    end_start: int = 0
    end_end: int = 0


@dataclass
class _Lexer:
    src: str
    len: int
    i: int           # string index
    b: int           # UTF-8 byte offset
    heredocs: List[_HeredocPending] = field(default_factory=list)
    byte_table: Optional[List[int]] = None


def _make_lexer(src: str) -> _Lexer:
    return _Lexer(src=src, len=len(src), i=0, b=0)


def _advance(L: _Lexer) -> None:
    """Advance one char, updating byte offset for UTF-8."""
    if L.i >= L.len:
        return
    c = ord(L.src[L.i])
    L.i += 1
    if c < 0x80:
        L.b += 1
    elif c < 0x800:
        L.b += 2
    elif 0xD800 <= c <= 0xDBFF:
        # High surrogate — Python handles these differently, but keep compat
        L.b += 4
        L.i += 1
    else:
        L.b += 3


def _peek(L: _Lexer, off: int = 0) -> str:
    idx = L.i + off
    if idx < L.len:
        return L.src[idx]
    return ""


def _byte_at(L: _Lexer, char_idx: int) -> int:
    """Get byte offset for a given char index, building byte_table if needed."""
    if L.byte_table is not None:
        return L.byte_table[char_idx]
    # Build table
    t = [0] * (L.len + 1)
    b = 0
    i = 0
    while i < L.len:
        t[i] = b
        c = ord(L.src[i])
        if c < 0x80:
            b += 1
            i += 1
        elif c < 0x800:
            b += 2
            i += 1
        elif 0xD800 <= c <= 0xDBFF:
            if i + 1 < L.len:
                t[i + 1] = b + 2
            b += 4
            i += 2
        else:
            b += 3
            i += 1
    t[L.len] = b
    L.byte_table = t
    return t[char_idx]


def _is_word_char(c: str) -> bool:
    return (
        ('a' <= c <= 'z') or ('A' <= c <= 'Z') or ('0' <= c <= '9') or
        c in ('_', '/', '.', '-', '+', ':', '@', '%', ',', '~', '^',
              '?', '*', '!', '=', '[', ']')
    )


def _is_word_start(c: str) -> bool:
    return _is_word_char(c) or c == '\\'


def _is_ident_start(c: str) -> bool:
    return ('a' <= c <= 'z') or ('A' <= c <= 'Z') or c == '_'


def _is_ident_char(c: str) -> bool:
    return _is_ident_start(c) or ('0' <= c <= '9')


def _is_digit(c: str) -> bool:
    return '0' <= c <= '9'


def _is_hex_digit(c: str) -> bool:
    return _is_digit(c) or ('a' <= c <= 'f') or ('A' <= c <= 'F')


def _is_base_digit(c: str) -> bool:
    return _is_ident_char(c) or c == '@'


def _is_heredoc_delim_char(c: str) -> bool:
    """Unquoted heredoc delimiter chars."""
    return (c != '' and c != ' ' and c != '\t' and c != '\n' and
            c != '<' and c != '>' and c != '|' and c != '&' and
            c != ';' and c != '(' and c != ')' and c != "'" and
            c != '"' and c != '`' and c != '\\')


def _skip_blanks(L: _Lexer) -> None:
    while L.i < L.len:
        c = L.src[L.i]
        if c in (' ', '\t', '\r'):
            _advance(L)
        elif c == '\\':
            nx = L.src[L.i + 1] if L.i + 1 < L.len else ''
            if nx == '\n' or (nx == '\r' and L.i + 2 < L.len and L.src[L.i + 2] == '\n'):
                _advance(L)
                _advance(L)
                if nx == '\r':
                    _advance(L)
            elif nx == ' ' or nx == '\t':
                _advance(L)
                _advance(L)
            else:
                break
        else:
            break


def _next_token(L: _Lexer, ctx: str = 'arg') -> _Token:
    """Scan next token. ctx is 'cmd' or 'arg'."""
    _skip_blanks(L)
    start = L.b
    if L.i >= L.len:
        return _Token(type=TOKEN_EOF, value='', start=start, end=start)

    c = L.src[L.i]
    c1 = _peek(L, 1)
    c2 = _peek(L, 2)

    if c == '\n':
        _advance(L)
        return _Token(type=TOKEN_NEWLINE, value='\n', start=start, end=L.b)

    if c == '#':
        si = L.i
        while L.i < L.len and L.src[L.i] != '\n':
            _advance(L)
        return _Token(type=TOKEN_COMMENT, value=L.src[si:L.i], start=start, end=L.b)

    # Multi-char operators (longest match first)
    if c == '&' and c1 == '&':
        _advance(L); _advance(L)
        return _Token(type=TOKEN_OP, value='&&', start=start, end=L.b)
    if c == '|' and c1 == '|':
        _advance(L); _advance(L)
        return _Token(type=TOKEN_OP, value='||', start=start, end=L.b)
    if c == '|' and c1 == '&':
        _advance(L); _advance(L)
        return _Token(type=TOKEN_OP, value='|&', start=start, end=L.b)
    if c == ';' and c1 == ';' and c2 == '&':
        _advance(L); _advance(L); _advance(L)
        return _Token(type=TOKEN_OP, value=';;&', start=start, end=L.b)
    if c == ';' and c1 == ';':
        _advance(L); _advance(L)
        return _Token(type=TOKEN_OP, value=';;', start=start, end=L.b)
    if c == ';' and c1 == '&':
        _advance(L); _advance(L)
        return _Token(type=TOKEN_OP, value=';&', start=start, end=L.b)
    if c == '>' and c1 == '>':
        _advance(L); _advance(L)
        return _Token(type=TOKEN_OP, value='>>', start=start, end=L.b)
    if c == '>' and c1 == '&' and c2 == '-':
        _advance(L); _advance(L); _advance(L)
        return _Token(type=TOKEN_OP, value='>&-', start=start, end=L.b)
    if c == '>' and c1 == '&':
        _advance(L); _advance(L)
        return _Token(type=TOKEN_OP, value='>&', start=start, end=L.b)
    if c == '>' and c1 == '|':
        _advance(L); _advance(L)
        return _Token(type=TOKEN_OP, value='>|', start=start, end=L.b)
    if c == '&' and c1 == '>' and c2 == '>':
        _advance(L); _advance(L); _advance(L)
        return _Token(type=TOKEN_OP, value='&>>', start=start, end=L.b)
    if c == '&' and c1 == '>':
        _advance(L); _advance(L)
        return _Token(type=TOKEN_OP, value='&>', start=start, end=L.b)
    if c == '<' and c1 == '<' and c2 == '<':
        _advance(L); _advance(L); _advance(L)
        return _Token(type=TOKEN_OP, value='<<<', start=start, end=L.b)
    if c == '<' and c1 == '<' and c2 == '-':
        _advance(L); _advance(L); _advance(L)
        return _Token(type=TOKEN_OP, value='<<-', start=start, end=L.b)
    if c == '<' and c1 == '<':
        _advance(L); _advance(L)
        return _Token(type=TOKEN_OP, value='<<', start=start, end=L.b)
    if c == '<' and c1 == '&' and c2 == '-':
        _advance(L); _advance(L); _advance(L)
        return _Token(type=TOKEN_OP, value='<&-', start=start, end=L.b)
    if c == '<' and c1 == '&':
        _advance(L); _advance(L)
        return _Token(type=TOKEN_OP, value='<&', start=start, end=L.b)
    if c == '<' and c1 == '(':
        _advance(L); _advance(L)
        return _Token(type=TOKEN_LT_PAREN, value='<(', start=start, end=L.b)
    if c == '>' and c1 == '(':
        _advance(L); _advance(L)
        return _Token(type=TOKEN_GT_PAREN, value='>(', start=start, end=L.b)
    if c == '(' and c1 == '(':
        _advance(L); _advance(L)
        return _Token(type=TOKEN_OP, value='((', start=start, end=L.b)
    if c == ')' and c1 == ')':
        _advance(L); _advance(L)
        return _Token(type=TOKEN_OP, value='))', start=start, end=L.b)

    if c in ('|', '&', ';', '>', '<'):
        _advance(L)
        return _Token(type=TOKEN_OP, value=c, start=start, end=L.b)
    if c in ('(', ')'):
        _advance(L)
        return _Token(type=TOKEN_OP, value=c, start=start, end=L.b)

    # In cmd position, [ [[ { start test/group; in arg position they're word chars
    if ctx == 'cmd':
        if c == '[' and c1 == '[':
            _advance(L); _advance(L)
            return _Token(type=TOKEN_OP, value='[[', start=start, end=L.b)
        if c == '[':
            _advance(L)
            return _Token(type=TOKEN_OP, value='[', start=start, end=L.b)
        if c == '{' and (c1 == ' ' or c1 == '\t' or c1 == '\n'):
            _advance(L)
            return _Token(type=TOKEN_OP, value='{', start=start, end=L.b)
        if c == '}':
            _advance(L)
            return _Token(type=TOKEN_OP, value='}', start=start, end=L.b)
        if c == '!' and (c1 == ' ' or c1 == '\t'):
            _advance(L)
            return _Token(type=TOKEN_OP, value='!', start=start, end=L.b)

    if c == '"':
        _advance(L)
        return _Token(type=TOKEN_DQUOTE, value='"', start=start, end=L.b)

    if c == "'":
        si = L.i
        _advance(L)
        while L.i < L.len and L.src[L.i] != "'":
            _advance(L)
        if L.i < L.len:
            _advance(L)
        return _Token(type=TOKEN_SQUOTE, value=L.src[si:L.i], start=start, end=L.b)

    if c == '$':
        if c1 == '(' and c2 == '(':
            _advance(L); _advance(L); _advance(L)
            return _Token(type=TOKEN_DOLLAR_DPAREN, value='$((', start=start, end=L.b)
        if c1 == '(':
            _advance(L); _advance(L)
            return _Token(type=TOKEN_DOLLAR_PAREN, value='$(', start=start, end=L.b)
        if c1 == '{':
            _advance(L); _advance(L)
            return _Token(type=TOKEN_DOLLAR_BRACE, value='${', start=start, end=L.b)
        if c1 == "'":
            # ANSI-C string $'...'
            si = L.i
            _advance(L); _advance(L)
            while L.i < L.len and L.src[L.i] != "'":
                if L.src[L.i] == '\\' and L.i + 1 < L.len:
                    _advance(L)
                _advance(L)
            if L.i < L.len:
                _advance(L)
            return _Token(type=TOKEN_ANSI_C, value=L.src[si:L.i], start=start, end=L.b)
        _advance(L)
        return _Token(type=TOKEN_DOLLAR, value='$', start=start, end=L.b)

    if c == '`':
        _advance(L)
        return _Token(type=TOKEN_BACKTICK, value='`', start=start, end=L.b)

    # File descriptor before redirect: digit+ immediately followed by > or <
    if _is_digit(c):
        j = L.i
        while j < L.len and _is_digit(L.src[j]):
            j += 1
        after = L.src[j] if j < L.len else ''
        if after == '>' or after == '<':
            si = L.i
            while L.i < j:
                _advance(L)
            return _Token(type=TOKEN_WORD, value=L.src[si:L.i], start=start, end=L.b)

    # Word / number
    if _is_word_start(c) or c in ('{', '}'):
        si = L.i
        while L.i < L.len:
            ch = L.src[L.i]
            if ch == '\\':
                if L.i + 1 >= L.len:
                    break
                if L.src[L.i + 1] == '\n':
                    _advance(L); _advance(L)
                    continue
                _advance(L); _advance(L)
                continue
            if not _is_word_char(ch) and ch not in ('{', '}'):
                break
            _advance(L)
        if L.i > si:
            v = L.src[si:L.i]
            if re.match(r'^-?\d+$', v):
                return _Token(type=TOKEN_NUMBER, value=v, start=start, end=L.b)
            return _Token(type=TOKEN_WORD, value=v, start=start, end=L.b)
        # fall through to single-char consumer

    # Unknown char — consume as single-char word
    _advance(L)
    return _Token(type=TOKEN_WORD, value=c, start=start, end=L.b)


# ───────────────────────────── Parser State ─────────────────────────────


@dataclass
class _ParseState:
    L: _Lexer
    src: str
    src_bytes: int
    is_ascii: bool
    node_count: int
    deadline: float
    aborted: bool
    in_backtick: int
    stop_token: Optional[str]


# Packed as (b << 24 | i) — avoids heap alloc on every backtrack.
# We use a simple 2-tuple for Python clarity.
def _save_lex(L: _Lexer) -> Tuple[int, int]:
    return (L.b, L.i)


def _restore_lex(L: _Lexer, s: Tuple[int, int]) -> None:
    L.b, L.i = s


def _byte_length_utf8(s: str) -> int:
    b = 0
    i = 0
    while i < len(s):
        c = ord(s[i])
        if c < 0x80:
            b += 1
        elif c < 0x800:
            b += 2
        elif 0xD800 <= c <= 0xDBFF:
            b += 4
            i += 1
        else:
            b += 3
        i += 1
    return b


def _check_budget(P: _ParseState) -> None:
    P.node_count += 1
    if P.node_count > MAX_NODES:
        P.aborted = True
        raise RuntimeError('budget')
    if (P.node_count & 0x7F) == 0 and time.monotonic() > P.deadline:
        P.aborted = True
        raise RuntimeError('timeout')


def _mk(P: _ParseState, type_: str, start: int, end: int, children: List[TsNode]) -> TsNode:
    """Build a node. Slices text from source by byte range via char-index lookup."""
    _check_budget(P)
    return TsNode(
        type=type_,
        text=_slice_bytes(P, start, end),
        startIndex=start,
        endIndex=end,
        children=children,
    )


def _slice_bytes(P: _ParseState, start_byte: int, end_byte: int) -> str:
    if P.is_ascii:
        return P.src[start_byte:end_byte]
    # Find char indices for byte offsets. Build byte table if needed.
    L = P.L
    if L.byte_table is None:
        _byte_at(L, 0)
    t = L.byte_table

    # Binary search for start char
    lo, hi = 0, len(P.src)
    while lo < hi:
        m = (lo + hi) >> 1
        if t[m] < start_byte:
            lo = m + 1
        else:
            hi = m
    sc = lo

    lo, hi = sc, len(P.src)
    while lo < hi:
        m = (lo + hi) >> 1
        if t[m] < end_byte:
            lo = m + 1
        else:
            hi = m
    return P.src[sc:lo]


def _leaf(P: _ParseState, type_: str, tok: _Token) -> TsNode:
    return _mk(P, type_, tok.start, tok.end, [])


def _restore_lex_to_byte(P: _ParseState, target_byte: int) -> None:
    L = P.L
    if L.byte_table is None:
        _byte_at(L, 0)
    t = L.byte_table
    lo, hi = 0, len(P.src)
    while lo < hi:
        m = (lo + hi) >> 1
        if t[m] < target_byte:
            lo = m + 1
        else:
            hi = m
    L.i = lo
    L.b = target_byte


# ───────────────────────────── Parse program ─────────────────────────────


def _parse_program(P: _ParseState) -> TsNode:
    children: List[TsNode] = []
    _skip_blanks(P.L)
    # Skip leading newlines
    while True:
        save = _save_lex(P.L)
        t = _next_token(P.L, 'cmd')
        if t.type == TOKEN_NEWLINE:
            _skip_blanks(P.L)
            continue
        _restore_lex(P.L, save)
        break

    prog_start = P.L.b

    while P.L.i < P.L.len:
        save = _save_lex(P.L)
        t = _next_token(P.L, 'cmd')
        if t.type == TOKEN_EOF:
            break
        if t.type == TOKEN_NEWLINE:
            continue
        if t.type == TOKEN_COMMENT:
            children.append(_leaf(P, 'comment', t))
            continue
        _restore_lex(P.L, save)
        stmts = _parse_statements(P, None)
        for s in stmts:
            children.append(s)
        if len(stmts) == 0:
            err_tok = _next_token(P.L, 'cmd')
            if err_tok.type == TOKEN_EOF:
                break
            if (err_tok.type == TOKEN_OP and err_tok.value == ';;' and
                    len(children) > 0):
                continue
            children.append(_mk(P, 'ERROR', err_tok.start, err_tok.end, []))

    prog_end = P.src_bytes if len(children) > 0 else prog_start
    return _mk(P, 'program', prog_start, prog_end, children)


def _skip_newlines(P: _ParseState) -> None:
    while True:
        save = _save_lex(P.L)
        t = _next_token(P.L, 'cmd')
        if t.type != TOKEN_NEWLINE:
            _restore_lex(P.L, save)
            break


def _parse_statements(P: _ParseState, terminator: Optional[str]) -> List[TsNode]:
    """
    Parse a sequence of statements separated by ; & newline.
    Returns a flat list. Stops at terminator or EOF.
    """
    out: List[TsNode] = []
    while True:
        _skip_blanks(P.L)
        save = _save_lex(P.L)
        t = _next_token(P.L, 'cmd')
        if t.type == TOKEN_EOF:
            _restore_lex(P.L, save)
            break
        if t.type == TOKEN_NEWLINE:
            if P.L.heredocs:
                _scan_heredoc_bodies(P)
            continue
        if t.type == TOKEN_COMMENT:
            out.append(_leaf(P, 'comment', t))
            continue
        if terminator and t.type == TOKEN_OP and t.value == terminator:
            _restore_lex(P.L, save)
            break
        if t.type == TOKEN_OP and t.value in (')', '}', ';;', ';&', ';;&', '))', ']]', ']'):
            _restore_lex(P.L, save)
            break
        if t.type == TOKEN_BACKTICK and P.in_backtick > 0:
            _restore_lex(P.L, save)
            break
        if (t.type == TOKEN_WORD and
                t.value in ('then', 'elif', 'else', 'fi', 'do', 'done', 'esac')):
            _restore_lex(P.L, save)
            break
        _restore_lex(P.L, save)
        stmt = _parse_and_or(P)
        if not stmt:
            break
        out.append(stmt)
        # Look for separator
        _skip_blanks(P.L)
        save2 = _save_lex(P.L)
        sep = _next_token(P.L, 'cmd')
        if sep.type == TOKEN_OP and sep.value in (';', '&'):
            save3 = _save_lex(P.L)
            after = _next_token(P.L, 'cmd')
            _restore_lex(P.L, save3)
            out.append(_leaf(P, sep.value, sep))
            if (after.type == TOKEN_EOF or
                    (after.type == TOKEN_OP and
                     after.value in (')', '}', ';;', ';&', ';;&')) or
                    (after.type == TOKEN_WORD and
                     after.value in ('then', 'elif', 'else', 'fi', 'do', 'done', 'esac'))):
                continue
        elif sep.type == TOKEN_NEWLINE:
            if P.L.heredocs:
                _scan_heredoc_bodies(P)
            continue
        else:
            _restore_lex(P.L, save2)
    return out


def _parse_and_or(P: _ParseState) -> Optional[TsNode]:
    """Parse pipeline chains joined by && ||."""
    left = _parse_pipeline(P)
    if not left:
        return None
    while True:
        save = _save_lex(P.L)
        t = _next_token(P.L, 'cmd')
        if t.type == TOKEN_OP and t.value in ('&&', '||'):
            op = _leaf(P, t.value, t)
            _skip_newlines(P)
            right = _parse_pipeline(P)
            if not right:
                left = _mk(P, 'list', left.startIndex, op.endIndex, [left, op])
                break
            # If right is a redirected_statement, hoist its redirects
            if right.type == 'redirected_statement' and len(right.children) >= 2:
                inner = right.children[0]
                redirs = right.children[1:]
                list_node = _mk(P, 'list', left.startIndex, inner.endIndex,
                                [left, op, inner])
                last_r = redirs[-1]
                left = _mk(P, 'redirected_statement', list_node.startIndex,
                           last_r.endIndex, [list_node] + list(redirs))
            else:
                left = _mk(P, 'list', left.startIndex, right.endIndex,
                           [left, op, right])
        else:
            _restore_lex(P.L, save)
            break
    return left


def _parse_pipeline(P: _ParseState) -> Optional[TsNode]:
    """Parse commands joined by | or |&."""
    first = _parse_command(P)
    if not first:
        return None
    parts: List[TsNode] = [first]
    while True:
        save = _save_lex(P.L)
        t = _next_token(P.L, 'cmd')
        if t.type == TOKEN_OP and t.value in ('|', '|&'):
            op = _leaf(P, t.value, t)
            _skip_newlines(P)
            nxt = _parse_command(P)
            if not nxt:
                parts.append(op)
                break
            # Hoist trailing redirect on `nxt` to wrap current pipeline fragment
            if (nxt.type == 'redirected_statement' and
                    len(nxt.children) >= 2 and len(parts) >= 1):
                inner = nxt.children[0]
                redirs = nxt.children[1:]
                pipe_kids = parts + [op, inner]
                pipe_node = _mk(P, 'pipeline', pipe_kids[0].startIndex,
                                inner.endIndex, pipe_kids)
                last_r = redirs[-1]
                wrapped = _mk(P, 'redirected_statement', pipe_node.startIndex,
                              last_r.endIndex, [pipe_node] + list(redirs))
                parts = [wrapped]
                first = wrapped
                continue
            parts.append(op)
            parts.append(nxt)
        else:
            _restore_lex(P.L, save)
            break
    if len(parts) == 1:
        return parts[0]
    last = parts[-1]
    return _mk(P, 'pipeline', parts[0].startIndex, last.endIndex, parts)


def _parse_command(P: _ParseState) -> Optional[TsNode]:
    """Parse a single command: simple, compound, or control structure."""
    _skip_blanks(P.L)
    save = _save_lex(P.L)
    t = _next_token(P.L, 'cmd')

    if t.type == TOKEN_EOF:
        _restore_lex(P.L, save)
        return None

    # Negation
    if t.type == TOKEN_OP and t.value == '!':
        bang = _leaf(P, '!', t)
        inner = _parse_command(P)
        if not inner:
            _restore_lex(P.L, save)
            return None
        if inner.type == 'redirected_statement' and len(inner.children) >= 2:
            cmd = inner.children[0]
            redirs = inner.children[1:]
            neg = _mk(P, 'negated_command', bang.startIndex, cmd.endIndex,
                      [bang, cmd])
            last_r = redirs[-1]
            return _mk(P, 'redirected_statement', neg.startIndex,
                       last_r.endIndex, [neg] + list(redirs))
        return _mk(P, 'negated_command', bang.startIndex, inner.endIndex,
                   [bang, inner])

    if t.type == TOKEN_OP and t.value == '(':
        open_p = _leaf(P, '(', t)
        body = _parse_statements(P, ')')
        close_tok = _next_token(P.L, 'cmd')
        if close_tok.type == TOKEN_OP and close_tok.value == ')':
            close = _leaf(P, ')', close_tok)
        else:
            close = _mk(P, ')', open_p.endIndex, open_p.endIndex, [])
        node = _mk(P, 'subshell', open_p.startIndex, close.endIndex,
                   [open_p] + body + [close])
        return _maybe_redirect(P, node)

    if t.type == TOKEN_OP and t.value == '((':
        open_p = _leaf(P, '((', t)
        exprs = _parse_arith_comma_list(P, '))', 'var')
        close_tok = _next_token(P.L, 'cmd')
        if close_tok.value == '))':
            close = _leaf(P, '))', close_tok)
        else:
            close = _mk(P, '))', open_p.endIndex, open_p.endIndex, [])
        return _mk(P, 'compound_statement', open_p.startIndex, close.endIndex,
                   [open_p] + exprs + [close])

    if t.type == TOKEN_OP and t.value == '{':
        open_b = _leaf(P, '{', t)
        body = _parse_statements(P, '}')
        close_tok = _next_token(P.L, 'cmd')
        if close_tok.type == TOKEN_OP and close_tok.value == '}':
            close = _leaf(P, '}', close_tok)
        else:
            close = _mk(P, '}', open_b.endIndex, open_b.endIndex, [])
        node = _mk(P, 'compound_statement', open_b.startIndex, close.endIndex,
                   [open_b] + body + [close])
        return _maybe_redirect(P, node)

    if t.type == TOKEN_OP and t.value in ('[', '[['):
        open_b = _leaf(P, t.value, t)
        closer = ']' if t.value == '[' else ']]'
        expr_save = _save_lex(P.L)
        expr = _parse_test_expr(P, closer)
        _skip_blanks(P.L)
        if t.value == '[' and _peek(P.L) != ']':
            _restore_lex(P.L, expr_save)
            prev_stop = P.stop_token
            P.stop_token = ']'
            rstmt = _parse_command(P)
            P.stop_token = prev_stop
            if rstmt and rstmt.type == 'redirected_statement':
                expr = rstmt
            else:
                _restore_lex(P.L, expr_save)
                expr = _parse_test_expr(P, closer)
            _skip_blanks(P.L)
        close_tok = _next_token(P.L, 'arg')
        if close_tok.value == closer:
            close = _leaf(P, closer, close_tok)
        else:
            close = _mk(P, closer, open_b.endIndex, open_b.endIndex, [])
        kids = [open_b, expr, close] if expr else [open_b, close]
        return _mk(P, 'test_command', open_b.startIndex, close.endIndex, kids)

    if t.type == TOKEN_WORD:
        if t.value == 'if':
            return _maybe_redirect(P, _parse_if(P, t), allow_herestring=True)
        if t.value in ('while', 'until'):
            return _maybe_redirect(P, _parse_while(P, t), allow_herestring=True)
        if t.value == 'for':
            return _maybe_redirect(P, _parse_for(P, t), allow_herestring=True)
        if t.value == 'select':
            return _maybe_redirect(P, _parse_for(P, t), allow_herestring=True)
        if t.value == 'case':
            return _maybe_redirect(P, _parse_case(P, t), allow_herestring=True)
        if t.value == 'function':
            return _parse_function(P, t)
        if t.value in DECL_KEYWORDS:
            return _maybe_redirect(P, _parse_declaration(P, t))
        if t.value in ('unset', 'unsetenv'):
            return _maybe_redirect(P, _parse_unset(P, t))

    _restore_lex(P.L, save)
    return _parse_simple_command(P)


def _parse_simple_command(P: _ParseState) -> Optional[TsNode]:
    """Parse a simple command: [assignment]* word [arg|redirect]*"""
    start = P.L.b
    assignments: List[TsNode] = []
    pre_redirects: List[TsNode] = []

    while True:
        _skip_blanks(P.L)
        a = _try_parse_assignment(P)
        if a:
            assignments.append(a)
            continue
        r = _try_parse_redirect(P)
        if r:
            pre_redirects.append(r)
            continue
        break

    _skip_blanks(P.L)
    save = _save_lex(P.L)
    name_tok = _next_token(P.L, 'cmd')
    if (name_tok.type == TOKEN_EOF or
            name_tok.type == TOKEN_NEWLINE or
            name_tok.type == TOKEN_COMMENT or
            (name_tok.type == TOKEN_OP and
             name_tok.value not in ('{', '[', '[[')) or
            (name_tok.type == TOKEN_WORD and
             name_tok.value in SHELL_KEYWORDS and
             name_tok.value != 'in')):
        _restore_lex(P.L, save)
        # No command — standalone assignment(s) or redirect
        if len(assignments) == 1 and len(pre_redirects) == 0:
            return assignments[0]
        if len(pre_redirects) > 0 and len(assignments) == 0:
            last = pre_redirects[-1]
            return _mk(P, 'redirected_statement',
                       pre_redirects[0].startIndex, last.endIndex, pre_redirects)
        if len(assignments) > 1 and len(pre_redirects) == 0:
            last = assignments[-1]
            return _mk(P, 'variable_assignments',
                       assignments[0].startIndex, last.endIndex, assignments)
        if assignments or pre_redirects:
            all_nodes = assignments + pre_redirects
            last = all_nodes[-1]
            return _mk(P, 'command', start, last.endIndex, all_nodes)
        return None
    _restore_lex(P.L, save)

    # Check for function definition: name() { ... }
    fn_save = _save_lex(P.L)
    nm = _parse_word(P, 'cmd')
    if nm and nm.type == 'word':
        _skip_blanks(P.L)
        if _peek(P.L) == '(' and _peek(P.L, 1) == ')':
            o_tok = _next_token(P.L, 'cmd')
            c_tok = _next_token(P.L, 'cmd')
            o_paren = _leaf(P, '(', o_tok)
            c_paren = _leaf(P, ')', c_tok)
            _skip_blanks(P.L)
            _skip_newlines(P)
            body = _parse_command(P)
            if body:
                body_kids: List[TsNode] = [body]
                if (body.type == 'redirected_statement' and
                        len(body.children) >= 2 and
                        body.children[0].type == 'compound_statement'):
                    body_kids = list(body.children)
                last = body_kids[-1]
                return _mk(P, 'function_definition', nm.startIndex, last.endIndex,
                           [nm, o_paren, c_paren] + body_kids)
    _restore_lex(P.L, fn_save)

    name_arg = _parse_word(P, 'cmd')
    if not name_arg:
        if len(assignments) == 1:
            return assignments[0]
        return None

    cmd_name = _mk(P, 'command_name', name_arg.startIndex, name_arg.endIndex,
                   [name_arg])

    args: List[TsNode] = []
    redirects: List[TsNode] = []
    heredoc_redirect: Optional[TsNode] = None

    while True:
        _skip_blanks(P.L)
        r = _try_parse_redirect(P, greedy=True)
        if r:
            if r.type == 'heredoc_redirect':
                heredoc_redirect = r
            elif r.type == 'herestring_redirect':
                args.append(r)
            else:
                redirects.append(r)
            continue
        if redirects:
            break
        if P.stop_token == ']' and _peek(P.L) == ']':
            break
        save2 = _save_lex(P.L)
        pk = _next_token(P.L, 'arg')
        if (pk.type == TOKEN_EOF or pk.type == TOKEN_NEWLINE or
                pk.type == TOKEN_COMMENT or
                (pk.type == TOKEN_OP and pk.value in (
                    '|', '|&', '&&', '||', ';', ';;', ';&', ';;&', '&',
                    ')', '}', '))'))):
            _restore_lex(P.L, save2)
            break
        _restore_lex(P.L, save2)
        arg = _parse_word(P, 'arg')
        if not arg:
            if _peek(P.L) == '(':
                o_tok = _next_token(P.L, 'cmd')
                open_p = _leaf(P, '(', o_tok)
                body = _parse_statements(P, ')')
                c_tok = _next_token(P.L, 'cmd')
                if c_tok.type == TOKEN_OP and c_tok.value == ')':
                    close = _leaf(P, ')', c_tok)
                else:
                    close = _mk(P, ')', open_p.endIndex, open_p.endIndex, [])
                args.append(_mk(P, 'subshell', open_p.startIndex, close.endIndex,
                               [open_p] + body + [close]))
                continue
            break
        # Lone `=` in arg position is a parse error
        if arg.type == 'word' and arg.text == '=':
            args.append(_mk(P, 'ERROR', arg.startIndex, arg.endIndex, [arg]))
            continue
        # Word immediately followed by `(` is a parse error
        if (arg.type in ('word', 'concatenation') and
                _peek(P.L) == '(' and P.L.b == arg.endIndex):
            args.append(_mk(P, 'ERROR', arg.startIndex, arg.endIndex, [arg]))
            continue
        args.append(arg)

    cmd_children = assignments + pre_redirects + [cmd_name] + args
    cmd_end = (cmd_children[-1].endIndex if cmd_children
               else cmd_name.endIndex)
    cmd_start = cmd_children[0].startIndex
    cmd = _mk(P, 'command', cmd_start, cmd_end, cmd_children)

    if heredoc_redirect:
        _scan_heredoc_bodies(P)
        hd = P.L.heredocs.pop(0) if P.L.heredocs else None
        if hd and len(heredoc_redirect.children) >= 2:
            body_node = _mk(
                P, 'heredoc_body', hd.body_start, hd.body_end,
                [] if hd.quoted else _parse_heredoc_body_content(P, hd.body_start, hd.body_end)
            )
            end_node = _mk(P, 'heredoc_end', hd.end_start, hd.end_end, [])
            heredoc_redirect.children.append(body_node)
            heredoc_redirect.children.append(end_node)
            heredoc_redirect.endIndex = hd.end_end
            heredoc_redirect.text = _slice_bytes(P, heredoc_redirect.startIndex, hd.end_end)
        all_r = pre_redirects + [heredoc_redirect] + redirects
        r_start = (min(cmd.startIndex, pre_redirects[0].startIndex)
                   if pre_redirects else cmd.startIndex)
        return _mk(P, 'redirected_statement', r_start, heredoc_redirect.endIndex,
                   [cmd] + all_r)

    if redirects:
        last = redirects[-1]
        return _mk(P, 'redirected_statement', cmd.startIndex, last.endIndex,
                   [cmd] + redirects)
    return cmd


def _maybe_redirect(P: _ParseState, node: TsNode,
                    allow_herestring: bool = False) -> TsNode:
    redirects: List[TsNode] = []
    while True:
        _skip_blanks(P.L)
        save = _save_lex(P.L)
        r = _try_parse_redirect(P)
        if not r:
            break
        if r.type == 'herestring_redirect' and not allow_herestring:
            _restore_lex(P.L, save)
            break
        redirects.append(r)
    if not redirects:
        return node
    last = redirects[-1]
    return _mk(P, 'redirected_statement', node.startIndex, last.endIndex,
               [node] + redirects)


def _try_parse_assignment(P: _ParseState) -> Optional[TsNode]:
    save = _save_lex(P.L)
    _skip_blanks(P.L)
    start_b = P.L.b
    if not _is_ident_start(_peek(P.L)):
        _restore_lex(P.L, save)
        return None
    while _is_ident_char(_peek(P.L)):
        _advance(P.L)
    name_end = P.L.b
    sub_end = name_end
    if _peek(P.L) == '[':
        _advance(P.L)
        depth = 1
        while P.L.i < P.L.len and depth > 0:
            c = _peek(P.L)
            if c == '[':
                depth += 1
            elif c == ']':
                depth -= 1
            _advance(P.L)
        sub_end = P.L.b
    c = _peek(P.L)
    c1 = _peek(P.L, 1)
    if c == '=' and c1 != '=':
        op = '='
    elif c == '+' and c1 == '=':
        op = '+='
    else:
        _restore_lex(P.L, save)
        return None

    name_node = _mk(P, 'variable_name', start_b, name_end, [])
    lhs: TsNode = name_node
    if sub_end > name_end:
        br_open = _mk(P, '[', name_end, name_end + 1, [])
        idx = _parse_subscript_index(P, name_end + 1, sub_end - 1)
        br_close = _mk(P, ']', sub_end - 1, sub_end, [])
        lhs = _mk(P, 'subscript', start_b, sub_end,
                  [name_node, br_open, idx, br_close])

    op_start = P.L.b
    _advance(P.L)
    if op == '+=':
        _advance(P.L)
    op_end = P.L.b
    op_node = _mk(P, op, op_start, op_end, [])

    val: Optional[TsNode] = None
    if _peek(P.L) == '(':
        ao_tok = _next_token(P.L, 'cmd')
        a_open = _leaf(P, '(', ao_tok)
        elems: List[TsNode] = [a_open]
        while True:
            _skip_blanks(P.L)
            if _peek(P.L) == ')':
                break
            e = _parse_word(P, 'arg')
            if not e:
                break
            elems.append(e)
        ac_tok = _next_token(P.L, 'cmd')
        if ac_tok.value == ')':
            a_close = _leaf(P, ')', ac_tok)
        else:
            a_close = _mk(P, ')', a_open.endIndex, a_open.endIndex, [])
        elems.append(a_close)
        val = _mk(P, 'array', a_open.startIndex, a_close.endIndex, elems)
    else:
        c2 = _peek(P.L)
        if c2 and c2 not in (' ', '\t', '\n', ';', '&', '|', ')', '}'):
            val = _parse_word(P, 'arg')

    kids = [lhs, op_node, val] if val else [lhs, op_node]
    end = val.endIndex if val else op_end
    return _mk(P, 'variable_assignment', start_b, end, kids)


def _parse_subscript_index_inline(P: _ParseState) -> Optional[TsNode]:
    """Parse subscript index content (for inline use)."""
    _skip_blanks(P.L)
    c = _peek(P.L)
    if (c in ('@', '*')) and _peek(P.L, 1) == ']':
        s = P.L.b
        _advance(P.L)
        return _mk(P, 'word', s, P.L.b, [])
    if c == '(' and _peek(P.L, 1) == '(':
        o_start = P.L.b
        _advance(P.L); _advance(P.L)
        open_n = _mk(P, '((', o_start, P.L.b, [])
        inner = _parse_arith_expr(P, '))', 'var')
        _skip_blanks(P.L)
        if _peek(P.L) == ')' and _peek(P.L, 1) == ')':
            cs = P.L.b
            _advance(P.L); _advance(P.L)
            close = _mk(P, '))', cs, P.L.b, [])
        else:
            close = _mk(P, '))', P.L.b, P.L.b, [])
        kids = [open_n, inner, close] if inner else [open_n, close]
        return _mk(P, 'compound_statement', open_n.startIndex, close.endIndex, kids)
    return _parse_arith_expr(P, ']', 'word')


def _parse_subscript_index(P: _ParseState, start_b: int, end_b: int) -> TsNode:
    """Legacy byte-range subscript index parser."""
    text = _slice_bytes(P, start_b, end_b)
    if re.match(r'^\d+$', text):
        return _mk(P, 'number', start_b, end_b, [])
    m = re.match(r'^\$([a-zA-Z_]\w*)$', text)
    if m:
        dollar = _mk(P, '$', start_b, start_b + 1, [])
        vn = _mk(P, 'variable_name', start_b + 1, end_b, [])
        return _mk(P, 'simple_expansion', start_b, end_b, [dollar, vn])
    if len(text) == 2 and text[0] == '$' and text[1] in SPECIAL_VARS:
        dollar = _mk(P, '$', start_b, start_b + 1, [])
        vn = _mk(P, 'special_variable_name', start_b + 1, end_b, [])
        return _mk(P, 'simple_expansion', start_b, end_b, [dollar, vn])
    return _mk(P, 'word', start_b, end_b, [])


def _is_redirect_literal_start(P: _ParseState) -> bool:
    """Can the current position start a redirect destination literal?"""
    c = _peek(P.L)
    if c == '' or c == '\n':
        return False
    if c in ('|', '&', ';', '(', ')'):
        return False
    if c in ('<', '>'):
        return _peek(P.L, 1) == '('
    if _is_digit(c):
        j = P.L.i
        while j < P.L.len and _is_digit(P.L.src[j]):
            j += 1
        after = P.L.src[j] if j < P.L.len else ''
        if after in ('>', '<'):
            return False
    if c == '}':
        return False
    if P.stop_token == ']' and c == ']':
        return False
    return True


def _try_parse_redirect(P: _ParseState, greedy: bool = False) -> Optional[TsNode]:
    """Parse a redirect operator + destination(s)."""
    save = _save_lex(P.L)
    _skip_blanks(P.L)
    fd: Optional[TsNode] = None
    if _is_digit(_peek(P.L)):
        start_b = P.L.b
        j = P.L.i
        while j < P.L.len and _is_digit(P.L.src[j]):
            j += 1
        after = P.L.src[j] if j < P.L.len else ''
        if after in ('>', '<'):
            while P.L.i < j:
                _advance(P.L)
            fd = _mk(P, 'file_descriptor', start_b, P.L.b, [])

    t = _next_token(P.L, 'arg')
    if t.type != TOKEN_OP:
        _restore_lex(P.L, save)
        return None

    v = t.value

    if v == '<<<':
        op = _leaf(P, '<<<', t)
        _skip_blanks(P.L)
        target = _parse_word(P, 'arg')
        end = target.endIndex if target else op.endIndex
        kids = [op, target] if target else [op]
        return _mk(P, 'herestring_redirect',
                   fd.startIndex if fd else op.startIndex, end,
                   ([fd] + kids) if fd else kids)

    if v in ('<<', '<<-'):
        op = _leaf(P, v, t)
        _skip_blanks(P.L)
        d_start = P.L.b
        quoted = False
        delim = ''
        dc = _peek(P.L)
        if dc in ("'", '"'):
            quoted = True
            _advance(P.L)
            while P.L.i < P.L.len and _peek(P.L) != dc:
                delim += _peek(P.L)
                _advance(P.L)
            if P.L.i < P.L.len:
                _advance(P.L)
        elif dc == '\\':
            # Backslash-escaped delimiter
            quoted = True
            _advance(P.L)
            if P.L.i < P.L.len and _peek(P.L) != '\n':
                delim += _peek(P.L)
                _advance(P.L)
            while P.L.i < P.L.len and _is_ident_char(_peek(P.L)):
                delim += _peek(P.L)
                _advance(P.L)
        else:
            while P.L.i < P.L.len and _is_heredoc_delim_char(_peek(P.L)):
                delim += _peek(P.L)
                _advance(P.L)
        d_end = P.L.b
        start_node = _mk(P, 'heredoc_start', d_start, d_end, [])
        P.L.heredocs.append(_HeredocPending(
            delim=delim,
            strip_tabs=(v == '<<-'),
            quoted=quoted,
        ))
        kids = ([fd, op, start_node] if fd else [op, start_node])
        start_idx = fd.startIndex if fd else op.startIndex
        # Parse trailing words/redirects/pipes between heredoc_start and newline
        while True:
            _skip_blanks(P.L)
            tc = _peek(P.L)
            if tc == '\n' or tc == '' or P.L.i >= P.L.len:
                break
            if tc in ('>', '<') or _is_digit(tc):
                r_save = _save_lex(P.L)
                r = _try_parse_redirect(P)
                if r and r.type == 'file_redirect':
                    kids.append(r)
                    continue
                _restore_lex(P.L, r_save)
            if tc == '|' and _peek(P.L, 1) != '|':
                _advance(P.L)
                _skip_blanks(P.L)
                pipe_cmds: List[TsNode] = []
                while True:
                    c2 = _parse_command(P)
                    if not c2:
                        break
                    pipe_cmds.append(c2)
                    _skip_blanks(P.L)
                    if _peek(P.L) == '|' and _peek(P.L, 1) != '|':
                        ps = P.L.b
                        _advance(P.L)
                        pipe_cmds.append(_mk(P, '|', ps, P.L.b, []))
                        _skip_blanks(P.L)
                        continue
                    break
                if pipe_cmds:
                    pl = pipe_cmds[-1]
                    kids.append(_mk(P, 'pipeline', pipe_cmds[0].startIndex,
                                   pl.endIndex, pipe_cmds))
                continue
            if ((tc == '&' and _peek(P.L, 1) == '&') or
                    (tc == '|' and _peek(P.L, 1) == '|')):
                _advance(P.L); _advance(P.L)
                _skip_blanks(P.L)
                rhs = _parse_command(P)
                if rhs:
                    kids.append(rhs)
                continue
            if tc in ('&', ';', '(', ')'):
                e_start = P.L.b
                while P.L.i < P.L.len and _peek(P.L) != '\n':
                    _advance(P.L)
                kids.append(_mk(P, 'ERROR', e_start, P.L.b, []))
                break
            w = _parse_word(P, 'arg')
            if w:
                kids.append(w)
                continue
            e_start = P.L.b
            while P.L.i < P.L.len and _peek(P.L) != '\n':
                _advance(P.L)
            if P.L.b > e_start:
                kids.append(_mk(P, 'ERROR', e_start, P.L.b, []))
            break
        return _mk(P, 'heredoc_redirect', start_idx, P.L.b, kids)

    if v in ('<&-', '>&-'):
        op = _leaf(P, v, t)
        kids = []
        if fd:
            kids.append(fd)
        kids.append(op)
        _skip_blanks(P.L)
        d_save = _save_lex(P.L)
        dest = _parse_word(P, 'arg') if _is_redirect_literal_start(P) else None
        if dest:
            kids.append(dest)
        else:
            _restore_lex(P.L, d_save)
        start_idx = fd.startIndex if fd else op.startIndex
        end = dest.endIndex if dest else op.endIndex
        return _mk(P, 'file_redirect', start_idx, end, kids)

    if v in ('>', '>>', '>&', '>|', '&>', '&>>', '<', '<&'):
        op = _leaf(P, v, t)
        kids = []
        if fd:
            kids.append(fd)
        kids.append(op)
        end = op.endIndex
        taken = 0
        while True:
            _skip_blanks(P.L)
            if not _is_redirect_literal_start(P):
                break
            if not greedy and taken >= 1:
                break
            tc = _peek(P.L)
            tc1 = _peek(P.L, 1)
            target = None
            if tc in ('<', '>') and tc1 == '(':
                target = _parse_process_sub(P)
            else:
                target = _parse_word(P, 'arg')
            if not target:
                break
            kids.append(target)
            end = target.endIndex
            taken += 1
        start_idx = fd.startIndex if fd else op.startIndex
        return _mk(P, 'file_redirect', start_idx, end, kids)

    _restore_lex(P.L, save)
    return None


def _parse_process_sub(P: _ParseState) -> Optional[TsNode]:
    c = _peek(P.L)
    if c not in ('<', '>') or _peek(P.L, 1) != '(':
        return None
    start = P.L.b
    _advance(P.L); _advance(P.L)
    open_n = _mk(P, c + '(', start, P.L.b, [])
    body = _parse_statements(P, ')')
    _skip_blanks(P.L)
    if _peek(P.L) == ')':
        cs = P.L.b
        _advance(P.L)
        close = _mk(P, ')', cs, P.L.b, [])
    else:
        close = _mk(P, ')', P.L.b, P.L.b, [])
    return _mk(P, 'process_substitution', start, close.endIndex,
               [open_n] + body + [close])


def _scan_heredoc_bodies(P: _ParseState) -> None:
    # Skip to newline if not already there
    while P.L.i < P.L.len and P.L.src[P.L.i] != '\n':
        _advance(P.L)
    if P.L.i < P.L.len:
        _advance(P.L)

    for hd in P.L.heredocs:
        hd.body_start = P.L.b
        delim_len = len(hd.delim)
        while P.L.i < P.L.len:
            line_start = P.L.i
            line_start_b = P.L.b
            check_i = line_start
            if hd.strip_tabs:
                while check_i < P.L.len and P.L.src[check_i] == '\t':
                    check_i += 1
            # Check if this line is the delimiter
            if (P.L.src.startswith(hd.delim, check_i) and
                    (check_i + delim_len >= P.L.len or
                     P.L.src[check_i + delim_len] in ('\n', '\r'))):
                hd.body_end = line_start_b
                # Advance past tabs
                while P.L.i < check_i:
                    _advance(P.L)
                hd.end_start = P.L.b
                # Advance past delimiter
                for _ in range(delim_len):
                    _advance(P.L)
                hd.end_end = P.L.b
                # Skip trailing newline
                if P.L.i < P.L.len and P.L.src[P.L.i] == '\n':
                    _advance(P.L)
                return
            # Consume line
            while P.L.i < P.L.len and P.L.src[P.L.i] != '\n':
                _advance(P.L)
            if P.L.i < P.L.len:
                _advance(P.L)
        # Unterminated
        hd.body_end = P.L.b
        hd.end_start = P.L.b
        hd.end_end = P.L.b


def _parse_heredoc_body_content(P: _ParseState, start: int, end: int) -> List[TsNode]:
    """Parse expansions inside an unquoted heredoc body."""
    saved = _save_lex(P.L)
    _restore_lex_to_byte(P, start)
    out: List[TsNode] = []
    content_start = P.L.b
    saw_expansion = False
    while P.L.b < end:
        c = _peek(P.L)
        if c == '\\':
            nxt = _peek(P.L, 1)
            if nxt in ('$', '`', '\\'):
                _advance(P.L); _advance(P.L)
                continue
            _advance(P.L)
            continue
        if c in ('$', '`'):
            pre_b = P.L.b
            exp = _parse_dollar_like(P)
            if (exp and exp.type in ('simple_expansion', 'expansion',
                                      'command_substitution', 'arithmetic_expansion')):
                if saw_expansion and pre_b > content_start:
                    out.append(_mk(P, 'heredoc_content', content_start, pre_b, []))
                out.append(exp)
                content_start = P.L.b
                saw_expansion = True
            continue
        _advance(P.L)
    if saw_expansion:
        out.append(_mk(P, 'heredoc_content', content_start, end, []))
    _restore_lex(P.L, saved)
    return out


def _restore_lex_to_byte(P: _ParseState, target_byte: int) -> None:
    L = P.L
    if L.byte_table is None:
        _byte_at(L, 0)
    t = L.byte_table
    lo, hi = 0, len(P.src)
    while lo < hi:
        m = (lo + hi) >> 1
        if t[m] < target_byte:
            lo = m + 1
        else:
            hi = m
    L.i = lo
    L.b = target_byte


def _parse_word(P: _ParseState, _ctx: str) -> Optional[TsNode]:
    """Parse a word-position element."""
    _skip_blanks(P.L)
    parts: List[TsNode] = []
    while P.L.i < P.L.len:
        c = _peek(P.L)
        if c in (' ', '\t', '\n', '\r', '', '|', '&', ';', '(', ')'):
            break
        if c in ('<', '>'):
            if _peek(P.L, 1) == '(':
                ps = _parse_process_sub(P)
                if ps:
                    parts.append(ps)
                continue
            break
        if c == '"':
            parts.append(_parse_double_quoted(P))
            continue
        if c == "'":
            tok = _next_token(P.L, 'arg')
            parts.append(_leaf(P, 'raw_string', tok))
            continue
        if c == '$':
            c1 = _peek(P.L, 1)
            if c1 == "'":
                tok = _next_token(P.L, 'arg')
                parts.append(_leaf(P, 'ansi_c_string', tok))
                continue
            if c1 == '"':
                d_tok = _Token(type=TOKEN_DOLLAR, value='$', start=P.L.b, end=P.L.b + 1)
                _advance(P.L)
                parts.append(_leaf(P, '$', d_tok))
                parts.append(_parse_double_quoted(P))
                continue
            if c1 == '`':
                _advance(P.L)
                continue
            exp = _parse_dollar_like(P)
            if exp:
                parts.append(exp)
            continue
        if c == '`':
            if P.in_backtick > 0:
                break
            bt = _parse_backtick(P)
            if bt:
                parts.append(bt)
            continue
        if c == '{':
            be = _try_parse_brace_expr(P)
            if be:
                parts.append(be)
                continue
            nc = _peek(P.L, 1)
            if nc in (';', '|', '&', '\n', '', ')', ' ', '\t'):
                b_start = P.L.b
                _advance(P.L)
                parts.append(_mk(P, 'word', b_start, P.L.b, []))
                continue
            cat = _try_parse_brace_like_cat(P)
            if cat:
                for p in cat:
                    parts.append(p)
                continue
        if c == '}':
            b_start = P.L.b
            _advance(P.L)
            parts.append(_mk(P, 'word', b_start, P.L.b, []))
            continue
        if c in ('[', ']'):
            b_start = P.L.b
            _advance(P.L)
            parts.append(_mk(P, 'word', b_start, P.L.b, []))
            continue
        frag = _parse_bare_word(P)
        if not frag:
            break
        # `NN#${...}` or `NN#$(...)` → number node
        if (frag.type == 'word' and
                re.match(r'^-?(0x)?[0-9]+#$', frag.text) and
                _peek(P.L) == '$' and
                _peek(P.L, 1) in ('{', '(')):
            exp = _parse_dollar_like(P)
            if exp:
                parts.append(_mk(P, 'number', frag.startIndex, exp.endIndex, [exp]))
                continue
        parts.append(frag)
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    first = parts[0]
    last = parts[-1]
    return _mk(P, 'concatenation', first.startIndex, last.endIndex, parts)


def _parse_bare_word(P: _ParseState) -> Optional[TsNode]:
    start = P.L.b
    start_i = P.L.i
    while P.L.i < P.L.len:
        c = _peek(P.L)
        if c == '\\':
            if P.L.i + 1 >= P.L.len:
                break
            nx = P.L.src[P.L.i + 1]
            if nx == '\n' or (nx == '\r' and P.L.i + 2 < P.L.len and P.L.src[P.L.i + 2] == '\n'):
                break
            _advance(P.L); _advance(P.L)
            continue
        if c in (' ', '\t', '\n', '\r', '', '|', '&', ';', '(', ')',
                 '<', '>', '"', "'", '$', '`', '{', '}', '[', ']'):
            break
        _advance(P.L)
    if P.L.b == start:
        return None
    text = P.src[start_i:P.L.i]
    type_ = 'number' if re.match(r'^-?\d+$', text) else 'word'
    return _mk(P, type_, start, P.L.b, [])


def _try_parse_brace_expr(P: _ParseState) -> Optional[TsNode]:
    """{N..M} where N, M are numbers or single chars."""
    save = _save_lex(P.L)
    if _peek(P.L) != '{':
        return None
    o_start = P.L.b
    _advance(P.L)
    o_end = P.L.b
    p1_start = P.L.b
    while _is_digit(_peek(P.L)) or _is_ident_start(_peek(P.L)):
        _advance(P.L)
    p1_end = P.L.b
    if p1_end == p1_start or _peek(P.L) != '.' or _peek(P.L, 1) != '.':
        _restore_lex(P.L, save)
        return None
    dot_start = P.L.b
    _advance(P.L); _advance(P.L)
    dot_end = P.L.b
    p2_start = P.L.b
    while _is_digit(_peek(P.L)) or _is_ident_start(_peek(P.L)):
        _advance(P.L)
    p2_end = P.L.b
    if p2_end == p2_start or _peek(P.L) != '}':
        _restore_lex(P.L, save)
        return None
    c_start = P.L.b
    _advance(P.L)
    c_end = P.L.b
    p1_text = _slice_bytes(P, p1_start, p1_end)
    p2_text = _slice_bytes(P, p2_start, p2_end)
    p1_is_num = bool(re.match(r'^\d+$', p1_text))
    p2_is_num = bool(re.match(r'^\d+$', p2_text))
    if p1_is_num != p2_is_num:
        _restore_lex(P.L, save)
        return None
    if not p1_is_num and (len(p1_text) != 1 or len(p2_text) != 1):
        _restore_lex(P.L, save)
        return None
    p1_type = 'number' if p1_is_num else 'word'
    p2_type = 'number' if p2_is_num else 'word'
    return _mk(P, 'brace_expression', o_start, c_end, [
        _mk(P, '{', o_start, o_end, []),
        _mk(P, p1_type, p1_start, p1_end, []),
        _mk(P, '..', dot_start, dot_end, []),
        _mk(P, p2_type, p2_start, p2_end, []),
        _mk(P, '}', c_start, c_end, []),
    ])


def _try_parse_brace_like_cat(P: _ParseState) -> Optional[List[TsNode]]:
    """{a,b,c} or {} → split into word fragments."""
    if _peek(P.L) != '{':
        return None
    o_start = P.L.b
    _advance(P.L)
    o_end = P.L.b
    inner: List[TsNode] = [_mk(P, 'word', o_start, o_end, [])]
    while P.L.i < P.L.len:
        bc = _peek(P.L)
        if bc in ('}', '\n', ';', '|', '&', ' ', '\t', '<', '>', '(', ')'):
            break
        if bc in ('[', ']'):
            b_start = P.L.b
            _advance(P.L)
            inner.append(_mk(P, 'word', b_start, P.L.b, []))
            continue
        mid_start = P.L.b
        while P.L.i < P.L.len:
            mc = _peek(P.L)
            if mc in ('}', '\n', ';', '|', '&', ' ', '\t', '<', '>', '(', ')', '[', ']'):
                break
            _advance(P.L)
        mid_end = P.L.b
        if mid_end > mid_start:
            mid_text = _slice_bytes(P, mid_start, mid_end)
            mid_type = 'number' if re.match(r'^-?\d+$', mid_text) else 'word'
            inner.append(_mk(P, mid_type, mid_start, mid_end, []))
        else:
            break
    if _peek(P.L) == '}':
        c_start = P.L.b
        _advance(P.L)
        inner.append(_mk(P, 'word', c_start, P.L.b, []))
    return inner


def _parse_double_quoted(P: _ParseState) -> TsNode:
    q_start = P.L.b
    _advance(P.L)
    q_end = P.L.b
    open_q = _mk(P, '"', q_start, q_end, [])
    parts: List[TsNode] = [open_q]
    content_start = P.L.b
    content_start_i = P.L.i

    def flush_content() -> None:
        nonlocal content_start, content_start_i
        if P.L.b > content_start:
            txt = P.src[content_start_i:P.L.i]
            if not re.match(r'^[ \t]+$', txt):
                parts.append(_mk(P, 'string_content', content_start, P.L.b, []))

    while P.L.i < P.L.len:
        c = _peek(P.L)
        if c == '"':
            break
        if c == '\\' and P.L.i + 1 < P.L.len:
            _advance(P.L); _advance(P.L)
            continue
        if c == '\n':
            flush_content()
            _advance(P.L)
            content_start = P.L.b
            content_start_i = P.L.i
            continue
        if c == '$':
            c1 = _peek(P.L, 1)
            if (c1 == '(' or c1 == '{' or _is_ident_start(c1) or
                    c1 in SPECIAL_VARS or _is_digit(c1)):
                flush_content()
                exp = _parse_dollar_like(P)
                if exp:
                    parts.append(exp)
                content_start = P.L.b
                content_start_i = P.L.i
                continue
            if c1 != '"' and c1 != '':
                flush_content()
                ds = P.L.b
                _advance(P.L)
                parts.append(_mk(P, '$', ds, P.L.b, []))
                content_start = P.L.b
                content_start_i = P.L.i
                continue
        if c == '`':
            flush_content()
            bt = _parse_backtick(P)
            if bt:
                parts.append(bt)
            content_start = P.L.b
            content_start_i = P.L.i
            continue
        _advance(P.L)

    flush_content()
    if _peek(P.L) == '"':
        c_start = P.L.b
        _advance(P.L)
        close = _mk(P, '"', c_start, P.L.b, [])
    else:
        close = _mk(P, '"', P.L.b, P.L.b, [])
    parts.append(close)
    return _mk(P, 'string', q_start, close.endIndex, parts)


def _parse_dollar_like(P: _ParseState) -> Optional[TsNode]:
    """Parse $..., ${...}, $(()), $(...)."""
    c1 = _peek(P.L, 1)
    d_start = P.L.b

    if c1 == '(' and _peek(P.L, 2) == '(':
        # $(( arithmetic ))
        _advance(P.L); _advance(P.L); _advance(P.L)
        open_n = _mk(P, '$((', d_start, P.L.b, [])
        exprs = _parse_arith_comma_list(P, '))', 'var')
        _skip_blanks(P.L)
        if _peek(P.L) == ')' and _peek(P.L, 1) == ')':
            cs = P.L.b
            _advance(P.L); _advance(P.L)
            close = _mk(P, '))', cs, P.L.b, [])
        else:
            close = _mk(P, '))', P.L.b, P.L.b, [])
        return _mk(P, 'arithmetic_expansion', d_start, close.endIndex,
                   [open_n] + exprs + [close])

    if c1 == '[':
        # $[ arithmetic ] — legacy bash syntax
        _advance(P.L); _advance(P.L)
        open_n = _mk(P, '$[', d_start, P.L.b, [])
        exprs = _parse_arith_comma_list(P, ']', 'var')
        _skip_blanks(P.L)
        if _peek(P.L) == ']':
            cs = P.L.b
            _advance(P.L)
            close = _mk(P, ']', cs, P.L.b, [])
        else:
            close = _mk(P, ']', P.L.b, P.L.b, [])
        return _mk(P, 'arithmetic_expansion', d_start, close.endIndex,
                   [open_n] + exprs + [close])

    if c1 == '(':
        _advance(P.L); _advance(P.L)
        open_n = _mk(P, '$(', d_start, P.L.b, [])
        body = _parse_statements(P, ')')
        _skip_blanks(P.L)
        if _peek(P.L) == ')':
            cs = P.L.b
            _advance(P.L)
            close = _mk(P, ')', cs, P.L.b, [])
        else:
            close = _mk(P, ')', P.L.b, P.L.b, [])
        # $(< file) shorthand
        if (len(body) == 1 and
                body[0].type == 'redirected_statement' and
                len(body[0].children) == 1 and
                body[0].children[0].type == 'file_redirect'):
            body = body[0].children
        return _mk(P, 'command_substitution', d_start, close.endIndex,
                   [open_n] + list(body) + [close])

    if c1 == '{':
        _advance(P.L); _advance(P.L)
        open_n = _mk(P, '${', d_start, P.L.b, [])
        inner = _parse_expansion_body(P)
        if _peek(P.L) == '}':
            cs = P.L.b
            _advance(P.L)
            close = _mk(P, '}', cs, P.L.b, [])
        else:
            close = _mk(P, '}', P.L.b, P.L.b, [])
        return _mk(P, 'expansion', d_start, close.endIndex,
                   [open_n] + inner + [close])

    # Simple expansion $VAR or $? $$ $@ etc
    _advance(P.L)
    d_end = P.L.b
    dollar = _mk(P, '$', d_start, d_end, [])
    nc = _peek(P.L)
    # $_ is special_variable_name only when not followed by more ident chars
    if nc == '_' and not _is_ident_char(_peek(P.L, 1)):
        v_start = P.L.b
        _advance(P.L)
        vn = _mk(P, 'special_variable_name', v_start, P.L.b, [])
        return _mk(P, 'simple_expansion', d_start, P.L.b, [dollar, vn])
    if _is_ident_start(nc):
        v_start = P.L.b
        while _is_ident_char(_peek(P.L)):
            _advance(P.L)
        vn = _mk(P, 'variable_name', v_start, P.L.b, [])
        return _mk(P, 'simple_expansion', d_start, P.L.b, [dollar, vn])
    if _is_digit(nc):
        v_start = P.L.b
        _advance(P.L)
        vn = _mk(P, 'variable_name', v_start, P.L.b, [])
        return _mk(P, 'simple_expansion', d_start, P.L.b, [dollar, vn])
    if nc in SPECIAL_VARS:
        v_start = P.L.b
        _advance(P.L)
        vn = _mk(P, 'special_variable_name', v_start, P.L.b, [])
        return _mk(P, 'simple_expansion', d_start, P.L.b, [dollar, vn])
    # Bare $ — just a $ leaf
    return dollar


def _parse_expansion_body(P: _ParseState) -> List[TsNode]:
    """Parse the body of ${...}."""
    out: List[TsNode] = []
    _skip_blanks(P.L)
    # Bizarre cases: ${#!} ${!#} ${!##} etc.
    c0 = _peek(P.L)
    c1 = _peek(P.L, 1)
    if c0 == '#' and c1 == '!' and _peek(P.L, 2) == '}':
        _advance(P.L); _advance(P.L)
        return out
    if c0 == '!' and c1 == '#':
        j = 2
        if _peek(P.L, j) == '#':
            j += 1
        if _peek(P.L, j) == ' ':
            j += 1
        if _peek(P.L, j) == '}':
            while j > 0:
                _advance(P.L)
                j -= 1
            return out

    # Optional # prefix for length
    if _peek(P.L) == '#':
        s = P.L.b
        _advance(P.L)
        out.append(_mk(P, '#', s, P.L.b, []))

    # Optional ! prefix for indirect expansion
    pc = _peek(P.L)
    if pc in ('!', '=', '~') and (_is_ident_start(_peek(P.L, 1)) or _is_digit(_peek(P.L, 1))):
        s = P.L.b
        _advance(P.L)
        out.append(_mk(P, pc, s, P.L.b, []))

    _skip_blanks(P.L)
    # Variable name
    if _is_ident_start(_peek(P.L)):
        s = P.L.b
        while _is_ident_char(_peek(P.L)):
            _advance(P.L)
        out.append(_mk(P, 'variable_name', s, P.L.b, []))
    elif _is_digit(_peek(P.L)):
        s = P.L.b
        while _is_digit(_peek(P.L)):
            _advance(P.L)
        out.append(_mk(P, 'variable_name', s, P.L.b, []))
    elif _peek(P.L) in SPECIAL_VARS:
        s = P.L.b
        _advance(P.L)
        out.append(_mk(P, 'special_variable_name', s, P.L.b, []))

    # Optional subscript [idx]
    if _peek(P.L) == '[':
        var_node = out[-1] if out else None
        br_open = P.L.b
        _advance(P.L)
        br_open_node = _mk(P, '[', br_open, P.L.b, [])
        idx = _parse_subscript_index_inline(P)
        _skip_blanks(P.L)
        br_close = P.L.b
        if _peek(P.L) == ']':
            _advance(P.L)
        br_close_node = _mk(P, ']', br_close, P.L.b, [])
        if var_node is not None:
            kids = ([var_node, br_open_node, idx, br_close_node] if idx
                    else [var_node, br_open_node, br_close_node])
            out[-1] = _mk(P, 'subscript', var_node.startIndex, P.L.b, kids)

    _skip_blanks(P.L)
    # Trailing * or @ for indirect/transformation
    tc = _peek(P.L)
    if tc in ('*', '@') and _peek(P.L, 1) == '}':
        s = P.L.b
        _advance(P.L)
        out.append(_mk(P, tc, s, P.L.b, []))
        return out
    if tc == '@' and _is_ident_start(_peek(P.L, 1)):
        s = P.L.b
        _advance(P.L)
        out.append(_mk(P, '@', s, P.L.b, []))
        while _is_ident_char(_peek(P.L)):
            _advance(P.L)
        return out

    # Operator handling
    c = _peek(P.L)
    # Bare `:` substring operator
    if c == ':':
        c1 = _peek(P.L, 1)
        if c1 in ('\n', '}'):
            _advance(P.L)
            while _peek(P.L) == '\n':
                _advance(P.L)
            return out
        if c1 not in ('-', '=', '?', '+'):
            _advance(P.L)
            _skip_blanks(P.L)
            off_c = _peek(P.L)
            off: Optional[TsNode] = None
            if off_c == '-' and _is_digit(_peek(P.L, 1)):
                ns = P.L.b
                _advance(P.L)
                while _is_digit(_peek(P.L)):
                    _advance(P.L)
                off = _mk(P, 'number', ns, P.L.b, [])
            else:
                off = _parse_arith_expr(P, ':}', 'var')
            if off:
                out.append(off)
            _skip_blanks(P.L)
            if _peek(P.L) == ':':
                _advance(P.L)
                _skip_blanks(P.L)
                len_c = _peek(P.L)
                len_n: Optional[TsNode] = None
                if len_c == '-' and _is_digit(_peek(P.L, 1)):
                    ns = P.L.b
                    _advance(P.L)
                    while _is_digit(_peek(P.L)):
                        _advance(P.L)
                    len_n = _mk(P, 'number', ns, P.L.b, [])
                else:
                    len_n = _parse_arith_expr(P, '}', 'var')
                if len_n:
                    out.append(len_n)
            return out

    if c in (':', '#', '%', '/', '^', ',', '-', '=', '?', '+'):
        s = P.L.b
        c1 = _peek(P.L, 1)
        op = c
        if c == ':' and c1 in ('-', '=', '?', '+'):
            _advance(P.L); _advance(P.L)
            op = c + c1
        elif c in ('#', '%', '/', '^', ',') and c1 == c:
            _advance(P.L); _advance(P.L)
            op = c + c
        else:
            _advance(P.L)
        out.append(_mk(P, op, s, P.L.b, []))

        is_pattern = op in ('#', '##', '%', '%%', '/', '//', '^', '^^', ',', ',,')

        if op in ('/', '//'):
            ac = _peek(P.L)
            if ac in ('#', '%'):
                a_start = P.L.b
                _advance(P.L)
                out.append(_mk(P, ac, a_start, P.L.b, []))
            if _peek(P.L) == '"':
                out.append(_parse_double_quoted(P))
                tail = _parse_expansion_rest(P, 'regex', True)
                if tail:
                    out.append(tail)
            else:
                regex = _parse_expansion_rest(P, 'regex', True)
                if regex:
                    out.append(regex)
            if _peek(P.L) == '/':
                sep_start = P.L.b
                _advance(P.L)
                out.append(_mk(P, '/', sep_start, P.L.b, []))
                repl = _parse_expansion_rest(P, 'replword', False)
                if repl:
                    # seq(cmd_sub, word) special case → siblings
                    if (repl.type == 'concatenation' and
                            len(repl.children) == 2 and
                            repl.children[0].type == 'command_substitution'):
                        out.append(repl.children[0])
                        out.append(repl.children[1])
                    else:
                        out.append(repl)
        elif op in ('#', '##', '%', '%%'):
            for p in _parse_expansion_regex_segmented(P):
                out.append(p)
        else:
            rest = _parse_expansion_rest(P, 'regex' if is_pattern else 'word', False)
            if rest:
                out.append(rest)

    return out


def _parse_expansion_rest(P: _ParseState, node_type: str,
                           stop_at_slash: bool) -> Optional[TsNode]:
    """Parse expansion RHS (word or regex mode)."""
    start = P.L.b

    # Value-substitution RHS starting with `(` → array
    if node_type == 'word' and _peek(P.L) == '(':
        _advance(P.L)
        open_n = _mk(P, '(', start, P.L.b, [])
        elems: List[TsNode] = [open_n]
        while P.L.i < P.L.len:
            _skip_blanks(P.L)
            c = _peek(P.L)
            if c in (')', '}', '\n', ''):
                break
            w_start = P.L.b
            while P.L.i < P.L.len:
                wc = _peek(P.L)
                if wc in (')', '}', ' ', '\t', '\n', ''):
                    break
                _advance(P.L)
            if P.L.b > w_start:
                elems.append(_mk(P, 'word', w_start, P.L.b, []))
            else:
                break
        if _peek(P.L) == ')':
            c_start = P.L.b
            _advance(P.L)
            elems.append(_mk(P, ')', c_start, P.L.b, []))
        while _peek(P.L) == '\n':
            _advance(P.L)
        return _mk(P, 'array', start, P.L.b, elems)

    # REGEX mode: flat single-span scan
    if node_type == 'regex':
        brace_depth = 0
        while P.L.i < P.L.len:
            c = _peek(P.L)
            if c == '\n':
                break
            if brace_depth == 0:
                if c == '}':
                    break
                if stop_at_slash and c == '/':
                    break
            if c == '\\' and P.L.i + 1 < P.L.len:
                _advance(P.L); _advance(P.L)
                continue
            if c in ('"', "'"):
                _advance(P.L)
                while P.L.i < P.L.len and _peek(P.L) != c:
                    if _peek(P.L) == '\\' and P.L.i + 1 < P.L.len:
                        _advance(P.L)
                    _advance(P.L)
                if _peek(P.L) == c:
                    _advance(P.L)
                continue
            if c == '$':
                c1 = _peek(P.L, 1)
                if c1 == '{':
                    d = 0
                    _advance(P.L); _advance(P.L)
                    d += 1
                    while P.L.i < P.L.len and d > 0:
                        nc = _peek(P.L)
                        if nc == '{':
                            d += 1
                        elif nc == '}':
                            d -= 1
                        _advance(P.L)
                    continue
                if c1 == '(':
                    d = 0
                    _advance(P.L); _advance(P.L)
                    d += 1
                    while P.L.i < P.L.len and d > 0:
                        nc = _peek(P.L)
                        if nc == '(':
                            d += 1
                        elif nc == ')':
                            d -= 1
                        _advance(P.L)
                    continue
            if c == '{':
                brace_depth += 1
            elif c == '}' and brace_depth > 0:
                brace_depth -= 1
            _advance(P.L)
        end = P.L.b
        while _peek(P.L) == '\n':
            _advance(P.L)
        if end == start:
            return None
        return _mk(P, 'regex', start, end, [])

    # WORD mode: segmenting parser
    parts: List[TsNode] = []
    seg_start = P.L.b
    brace_depth = 0

    def flush_seg() -> None:
        nonlocal seg_start
        if P.L.b > seg_start:
            parts.append(_mk(P, 'word', seg_start, P.L.b, []))

    while P.L.i < P.L.len:
        c = _peek(P.L)
        if c == '\n':
            break
        if brace_depth == 0:
            if c == '}':
                break
            if stop_at_slash and c == '/':
                break
        if c == '\\' and P.L.i + 1 < P.L.len:
            _advance(P.L); _advance(P.L)
            continue
        c1 = _peek(P.L, 1)
        if c == '$':
            if c1 in ('{', '(', '['):
                flush_seg()
                exp = _parse_dollar_like(P)
                if exp:
                    parts.append(exp)
                seg_start = P.L.b
                continue
            if c1 == "'":
                flush_seg()
                a_start = P.L.b
                _advance(P.L); _advance(P.L)
                while P.L.i < P.L.len and _peek(P.L) != "'":
                    if _peek(P.L) == '\\' and P.L.i + 1 < P.L.len:
                        _advance(P.L)
                    _advance(P.L)
                if _peek(P.L) == "'":
                    _advance(P.L)
                parts.append(_mk(P, 'ansi_c_string', a_start, P.L.b, []))
                seg_start = P.L.b
                continue
            if _is_ident_start(c1) or _is_digit(c1) or c1 in SPECIAL_VARS:
                flush_seg()
                exp = _parse_dollar_like(P)
                if exp:
                    parts.append(exp)
                seg_start = P.L.b
                continue
        if c == '"':
            flush_seg()
            parts.append(_parse_double_quoted(P))
            seg_start = P.L.b
            continue
        if c == "'":
            flush_seg()
            r_start = P.L.b
            _advance(P.L)
            while P.L.i < P.L.len and _peek(P.L) != "'":
                _advance(P.L)
            if _peek(P.L) == "'":
                _advance(P.L)
            parts.append(_mk(P, 'raw_string', r_start, P.L.b, []))
            seg_start = P.L.b
            continue
        if c in ('<', '>') and c1 == '(':
            flush_seg()
            ps = _parse_process_sub(P)
            if ps:
                parts.append(ps)
            seg_start = P.L.b
            continue
        if c == '`':
            flush_seg()
            bt = _parse_backtick(P)
            if bt:
                parts.append(bt)
            seg_start = P.L.b
            continue
        if c == '{':
            brace_depth += 1
        elif c == '}' and brace_depth > 0:
            brace_depth -= 1
        _advance(P.L)

    flush_seg()
    while _peek(P.L) == '\n':
        _advance(P.L)
    # Drop leading whitespace-only segment if not the only part
    if (len(parts) > 1 and parts[0].type == 'word' and
            re.match(r'^[ \t]+$', parts[0].text)):
        parts.pop(0)
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    last = parts[-1]
    return _mk(P, 'concatenation', parts[0].startIndex, last.endIndex, parts)


def _parse_expansion_regex_segmented(P: _ParseState) -> List[TsNode]:
    """Pattern for # ## % %% operators — each quote becomes a sibling node."""
    out: List[TsNode] = []
    seg_start = P.L.b

    def flush_regex() -> None:
        nonlocal seg_start
        if P.L.b > seg_start:
            out.append(_mk(P, 'regex', seg_start, P.L.b, []))

    while P.L.i < P.L.len:
        c = _peek(P.L)
        if c in ('}', '\n'):
            break
        if c == '\\' and P.L.i + 1 < P.L.len:
            _advance(P.L); _advance(P.L)
            continue
        if c == '"':
            flush_regex()
            out.append(_parse_double_quoted(P))
            seg_start = P.L.b
            continue
        if c == "'":
            flush_regex()
            r_start = P.L.b
            _advance(P.L)
            while P.L.i < P.L.len and _peek(P.L) != "'":
                _advance(P.L)
            if _peek(P.L) == "'":
                _advance(P.L)
            out.append(_mk(P, 'raw_string', r_start, P.L.b, []))
            seg_start = P.L.b
            continue
        if c == '$':
            c1 = _peek(P.L, 1)
            if c1 == '{':
                d = 1
                _advance(P.L); _advance(P.L)
                while P.L.i < P.L.len and d > 0:
                    nc = _peek(P.L)
                    if nc == '{':
                        d += 1
                    elif nc == '}':
                        d -= 1
                    _advance(P.L)
                continue
            if c1 == '(':
                d = 1
                _advance(P.L); _advance(P.L)
                while P.L.i < P.L.len and d > 0:
                    nc = _peek(P.L)
                    if nc == '(':
                        d += 1
                    elif nc == ')':
                        d -= 1
                    _advance(P.L)
                continue
        _advance(P.L)

    flush_regex()
    while _peek(P.L) == '\n':
        _advance(P.L)
    return out


def _parse_backtick(P: _ParseState) -> Optional[TsNode]:
    start = P.L.b
    _advance(P.L)
    open_n = _mk(P, '`', start, P.L.b, [])
    P.in_backtick += 1
    body: List[TsNode] = []
    while True:
        _skip_blanks(P.L)
        if _peek(P.L) in ('`', ''):
            break
        save = _save_lex(P.L)
        t = _next_token(P.L, 'cmd')
        if t.type in (TOKEN_EOF, TOKEN_BACKTICK):
            _restore_lex(P.L, save)
            break
        if t.type == TOKEN_NEWLINE:
            continue
        _restore_lex(P.L, save)
        stmt = _parse_and_or(P)
        if not stmt:
            break
        body.append(stmt)
        _skip_blanks(P.L)
        if _peek(P.L) == '`':
            break
        save2 = _save_lex(P.L)
        sep = _next_token(P.L, 'cmd')
        if sep.type == TOKEN_OP and sep.value in (';', '&'):
            body.append(_leaf(P, sep.value, sep))
        elif sep.type != TOKEN_NEWLINE:
            _restore_lex(P.L, save2)
    P.in_backtick -= 1
    if _peek(P.L) == '`':
        c_start = P.L.b
        _advance(P.L)
        close = _mk(P, '`', c_start, P.L.b, [])
    else:
        close = _mk(P, '`', P.L.b, P.L.b, [])
    if not body:
        return None
    return _mk(P, 'command_substitution', start, close.endIndex,
               [open_n] + body + [close])


def _parse_if(P: _ParseState, if_tok: _Token) -> TsNode:
    if_kw = _leaf(P, 'if', if_tok)
    kids: List[TsNode] = [if_kw]
    cond = _parse_statements(P, None)
    kids.extend(cond)
    _consume_keyword(P, 'then', kids)
    body = _parse_statements(P, None)
    kids.extend(body)
    while True:
        save = _save_lex(P.L)
        t = _next_token(P.L, 'cmd')
        if t.type == TOKEN_WORD and t.value == 'elif':
            e_kw = _leaf(P, 'elif', t)
            e_cond = _parse_statements(P, None)
            e_kids: List[TsNode] = [e_kw] + e_cond
            _consume_keyword(P, 'then', e_kids)
            e_body = _parse_statements(P, None)
            e_kids.extend(e_body)
            last = e_kids[-1]
            kids.append(_mk(P, 'elif_clause', e_kw.startIndex, last.endIndex, e_kids))
        elif t.type == TOKEN_WORD and t.value == 'else':
            el_kw = _leaf(P, 'else', t)
            el_body = _parse_statements(P, None)
            last = el_body[-1] if el_body else el_kw
            kids.append(_mk(P, 'else_clause', el_kw.startIndex, last.endIndex,
                            [el_kw] + el_body))
        else:
            _restore_lex(P.L, save)
            break
    _consume_keyword(P, 'fi', kids)
    last = kids[-1]
    return _mk(P, 'if_statement', if_kw.startIndex, last.endIndex, kids)


def _parse_while(P: _ParseState, kw_tok: _Token) -> TsNode:
    kw = _leaf(P, kw_tok.value, kw_tok)
    kids: List[TsNode] = [kw]
    cond = _parse_statements(P, None)
    kids.extend(cond)
    dg = _parse_do_group(P)
    if dg:
        kids.append(dg)
    last = kids[-1]
    return _mk(P, 'while_statement', kw.startIndex, last.endIndex, kids)


def _parse_for(P: _ParseState, for_tok: _Token) -> TsNode:
    for_kw = _leaf(P, for_tok.value, for_tok)
    _skip_blanks(P.L)
    # C-style for (( ; ; )) — only for `for`, not `select`
    if for_tok.value == 'for' and _peek(P.L) == '(' and _peek(P.L, 1) == '(':
        o_start = P.L.b
        _advance(P.L); _advance(P.L)
        open_n = _mk(P, '((', o_start, P.L.b, [])
        kids: List[TsNode] = [for_kw, open_n]
        for k in range(3):
            _skip_blanks(P.L)
            es = _parse_arith_comma_list(P, ';' if k < 2 else '))', 'assign')
            kids.extend(es)
            if k < 2:
                if _peek(P.L) == ';':
                    s = P.L.b
                    _advance(P.L)
                    kids.append(_mk(P, ';', s, P.L.b, []))
        _skip_blanks(P.L)
        if _peek(P.L) == ')' and _peek(P.L, 1) == ')':
            c_start = P.L.b
            _advance(P.L); _advance(P.L)
            kids.append(_mk(P, '))', c_start, P.L.b, []))
        save = _save_lex(P.L)
        sep = _next_token(P.L, 'cmd')
        if sep.type == TOKEN_OP and sep.value == ';':
            kids.append(_leaf(P, ';', sep))
        elif sep.type != TOKEN_NEWLINE:
            _restore_lex(P.L, save)
        dg = _parse_do_group(P)
        if dg:
            kids.append(dg)
        else:
            _skip_newlines(P)
            _skip_blanks(P.L)
            if _peek(P.L) == '{':
                b_open = P.L.b
                _advance(P.L)
                brace = _mk(P, '{', b_open, P.L.b, [])
                body = _parse_statements(P, '}')
                if _peek(P.L) == '}':
                    cs = P.L.b
                    _advance(P.L)
                    b_close = _mk(P, '}', cs, P.L.b, [])
                else:
                    b_close = _mk(P, '}', P.L.b, P.L.b, [])
                kids.append(_mk(P, 'compound_statement', brace.startIndex,
                               b_close.endIndex, [brace] + body + [b_close]))
        last = kids[-1]
        return _mk(P, 'c_style_for_statement', for_kw.startIndex, last.endIndex, kids)

    # Regular for VAR in words; do ... done
    kids2: List[TsNode] = [for_kw]
    var_tok = _next_token(P.L, 'arg')
    kids2.append(_mk(P, 'variable_name', var_tok.start, var_tok.end, []))
    _skip_blanks(P.L)
    save = _save_lex(P.L)
    in_tok = _next_token(P.L, 'arg')
    if in_tok.type == TOKEN_WORD and in_tok.value == 'in':
        kids2.append(_leaf(P, 'in', in_tok))
        while True:
            _skip_blanks(P.L)
            c = _peek(P.L)
            if c in (';', '\n', ''):
                break
            w = _parse_word(P, 'arg')
            if not w:
                break
            kids2.append(w)
    else:
        _restore_lex(P.L, save)
    save2 = _save_lex(P.L)
    sep = _next_token(P.L, 'cmd')
    if sep.type == TOKEN_OP and sep.value == ';':
        kids2.append(_leaf(P, ';', sep))
    elif sep.type != TOKEN_NEWLINE:
        _restore_lex(P.L, save2)
    dg = _parse_do_group(P)
    if dg:
        kids2.append(dg)
    last = kids2[-1]
    return _mk(P, 'for_statement', for_kw.startIndex, last.endIndex, kids2)


def _parse_do_group(P: _ParseState) -> Optional[TsNode]:
    _skip_newlines(P)
    save = _save_lex(P.L)
    do_tok = _next_token(P.L, 'cmd')
    if do_tok.type != TOKEN_WORD or do_tok.value != 'do':
        _restore_lex(P.L, save)
        return None
    do_kw = _leaf(P, 'do', do_tok)
    body = _parse_statements(P, None)
    kids: List[TsNode] = [do_kw] + body
    _consume_keyword(P, 'done', kids)
    last = kids[-1]
    return _mk(P, 'do_group', do_kw.startIndex, last.endIndex, kids)


def _parse_case(P: _ParseState, case_tok: _Token) -> TsNode:
    case_kw = _leaf(P, 'case', case_tok)
    kids: List[TsNode] = [case_kw]
    _skip_blanks(P.L)
    word = _parse_word(P, 'arg')
    if word:
        kids.append(word)
    _skip_blanks(P.L)
    _consume_keyword(P, 'in', kids)
    _skip_newlines(P)
    while True:
        _skip_blanks(P.L)
        _skip_newlines(P)
        save = _save_lex(P.L)
        t = _next_token(P.L, 'arg')
        if t.type == TOKEN_WORD and t.value == 'esac':
            kids.append(_leaf(P, 'esac', t))
            break
        if t.type == TOKEN_EOF:
            break
        _restore_lex(P.L, save)
        item = _parse_case_item(P)
        if not item:
            break
        kids.append(item)
    last = kids[-1]
    return _mk(P, 'case_statement', case_kw.startIndex, last.endIndex, kids)


def _parse_case_item(P: _ParseState) -> Optional[TsNode]:
    _skip_blanks(P.L)
    start = P.L.b
    kids: List[TsNode] = []
    if _peek(P.L) == '(':
        s = P.L.b
        _advance(P.L)
        kids.append(_mk(P, '(', s, P.L.b, []))
    is_first_alt = True
    while True:
        _skip_blanks(P.L)
        c = _peek(P.L)
        if c in (')', ''):
            break
        pats = _parse_case_pattern(P)
        if not pats:
            break
        if not is_first_alt and len(pats) > 1:
            rewritten = [
                (_mk(P, 'word', p.startIndex, p.endIndex, [])
                 if p.type == 'extglob_pattern' else p)
                for p in pats
            ]
            first = rewritten[0]
            last = rewritten[-1]
            kids.append(_mk(P, 'concatenation', first.startIndex, last.endIndex,
                            rewritten))
        else:
            kids.extend(pats)
        is_first_alt = False
        _skip_blanks(P.L)
        if _peek(P.L) == '\\' and _peek(P.L, 1) == '\n':
            _advance(P.L); _advance(P.L)
            _skip_blanks(P.L)
        if _peek(P.L) == '|':
            s = P.L.b
            _advance(P.L)
            kids.append(_mk(P, '|', s, P.L.b, []))
            if _peek(P.L) == '\\' and _peek(P.L, 1) == '\n':
                _advance(P.L); _advance(P.L)
        else:
            break
    if _peek(P.L) == ')':
        s = P.L.b
        _advance(P.L)
        kids.append(_mk(P, ')', s, P.L.b, []))
    body = _parse_statements(P, None)
    kids.extend(body)
    save = _save_lex(P.L)
    term = _next_token(P.L, 'cmd')
    if term.type == TOKEN_OP and term.value in (';;', ';&', ';;&'):
        kids.append(_leaf(P, term.value, term))
    else:
        _restore_lex(P.L, save)
    if not kids:
        return None
    # Downgrade extglob_pattern to word for empty case items
    if not body:
        for i, k in enumerate(kids):
            if k.type != 'extglob_pattern':
                continue
            text = _slice_bytes(P, k.startIndex, k.endIndex)
            if re.match(r'^[-+?*@!][a-zA-Z]', text) and not re.search(r'[*?(]', text):
                kids[i] = _mk(P, 'word', k.startIndex, k.endIndex, [])
    last = kids[-1]
    return _mk(P, 'case_item', start, last.endIndex, kids)


def _parse_case_pattern(P: _ParseState) -> List[TsNode]:
    _skip_blanks(P.L)
    save = _save_lex(P.L)
    start = P.L.b
    start_i = P.L.i
    paren_depth = 0
    has_dollar = False
    has_bracket_outside_paren = False
    has_quote = False
    while P.L.i < P.L.len:
        c = _peek(P.L)
        if c == '\\' and P.L.i + 1 < P.L.len:
            _advance(P.L); _advance(P.L)
            continue
        if c in ('"', "'"):
            has_quote = True
            _advance(P.L)
            while P.L.i < P.L.len and _peek(P.L) != c:
                if _peek(P.L) == '\\' and P.L.i + 1 < P.L.len:
                    _advance(P.L)
                _advance(P.L)
            if _peek(P.L) == c:
                _advance(P.L)
            continue
        if c == '(':
            paren_depth += 1
            _advance(P.L)
            continue
        if paren_depth > 0:
            if c == ')':
                paren_depth -= 1
                _advance(P.L)
                continue
            if c == '\n':
                break
            _advance(P.L)
            continue
        if c in (')', '|', ' ', '\t', '\n'):
            break
        if c == '$':
            has_dollar = True
        if c == '[':
            has_bracket_outside_paren = True
        _advance(P.L)
    if P.L.b == start:
        return []
    text = P.src[start_i:P.L.i]
    has_extglob_paren = bool(re.search(r'[*?+@!]\(', text))
    if has_quote and not has_extglob_paren:
        _restore_lex(P.L, save)
        return _parse_case_pattern_segmented(P)
    if not has_extglob_paren and (has_dollar or has_bracket_outside_paren):
        _restore_lex(P.L, save)
        w = _parse_word(P, 'arg')
        return [w] if w else []
    type_ = ('extglob_pattern'
             if (has_extglob_paren or re.search(r'[*?]', text) or
                 re.match(r'^[-+?*@!][a-zA-Z]', text))
             else 'word')
    return [_mk(P, type_, start, P.L.b, [])]


def _parse_case_pattern_segmented(P: _ParseState) -> List[TsNode]:
    """Segmented scan for case patterns containing quotes."""
    parts: List[TsNode] = []
    seg_start = P.L.b
    seg_start_i = P.L.i

    def flush_seg() -> None:
        nonlocal seg_start, seg_start_i
        if P.L.i > seg_start_i:
            t = P.src[seg_start_i:P.L.i]
            type_ = 'extglob_pattern' if re.search(r'[*?]', t) else 'word'
            parts.append(_mk(P, type_, seg_start, P.L.b, []))

    while P.L.i < P.L.len:
        c = _peek(P.L)
        if c == '\\' and P.L.i + 1 < P.L.len:
            _advance(P.L); _advance(P.L)
            continue
        if c == '"':
            flush_seg()
            parts.append(_parse_double_quoted(P))
            seg_start = P.L.b
            seg_start_i = P.L.i
            continue
        if c == "'":
            flush_seg()
            tok = _next_token(P.L, 'arg')
            parts.append(_leaf(P, 'raw_string', tok))
            seg_start = P.L.b
            seg_start_i = P.L.i
            continue
        if c in (')', '|', ' ', '\t', '\n'):
            break
        _advance(P.L)

    flush_seg()
    return parts


def _parse_function(P: _ParseState, fn_tok: _Token) -> TsNode:
    fn_kw = _leaf(P, 'function', fn_tok)
    _skip_blanks(P.L)
    name_tok = _next_token(P.L, 'arg')
    name = _mk(P, 'word', name_tok.start, name_tok.end, [])
    kids: List[TsNode] = [fn_kw, name]
    _skip_blanks(P.L)
    if _peek(P.L) == '(' and _peek(P.L, 1) == ')':
        o = _next_token(P.L, 'cmd')
        c = _next_token(P.L, 'cmd')
        kids.append(_leaf(P, '(', o))
        kids.append(_leaf(P, ')', c))
    _skip_blanks(P.L)
    _skip_newlines(P)
    body = _parse_command(P)
    if body:
        if (body.type == 'redirected_statement' and
                len(body.children) >= 2 and
                body.children[0].type == 'compound_statement'):
            kids.extend(body.children)
        else:
            kids.append(body)
    last = kids[-1]
    return _mk(P, 'function_definition', fn_kw.startIndex, last.endIndex, kids)


def _parse_declaration(P: _ParseState, kw_tok: _Token) -> TsNode:
    kw = _leaf(P, kw_tok.value, kw_tok)
    kids: List[TsNode] = [kw]
    while True:
        _skip_blanks(P.L)
        c = _peek(P.L)
        if c in ('', '\n', ';', '&', '|', ')', '<', '>'):
            break
        a = _try_parse_assignment(P)
        if a:
            kids.append(a)
            continue
        if c in ('"', "'", '$'):
            w = _parse_word(P, 'arg')
            if w:
                kids.append(w)
                continue
            break
        save = _save_lex(P.L)
        tok = _next_token(P.L, 'arg')
        if tok.type in (TOKEN_WORD, TOKEN_NUMBER):
            if tok.value.startswith('-'):
                kids.append(_leaf(P, 'word', tok))
            elif _is_ident_start(tok.value[0] if tok.value else ''):
                kids.append(_mk(P, 'variable_name', tok.start, tok.end, []))
            else:
                kids.append(_leaf(P, 'word', tok))
        else:
            _restore_lex(P.L, save)
            break
    last = kids[-1]
    return _mk(P, 'declaration_command', kw.startIndex, last.endIndex, kids)


def _parse_unset(P: _ParseState, kw_tok: _Token) -> TsNode:
    kw = _leaf(P, 'unset', kw_tok)
    kids: List[TsNode] = [kw]
    while True:
        _skip_blanks(P.L)
        c = _peek(P.L)
        if c in ('', '\n', ';', '&', '|', ')', '<', '>'):
            break
        arg = _parse_word(P, 'arg')
        if not arg:
            break
        if arg.type == 'word':
            if arg.text.startswith('-'):
                kids.append(arg)
            else:
                kids.append(_mk(P, 'variable_name', arg.startIndex, arg.endIndex, []))
        else:
            kids.append(arg)
    last = kids[-1]
    return _mk(P, 'unset_command', kw.startIndex, last.endIndex, kids)


def _consume_keyword(P: _ParseState, name: str, kids: List[TsNode]) -> None:
    _skip_newlines(P)
    save = _save_lex(P.L)
    t = _next_token(P.L, 'cmd')
    if t.type == TOKEN_WORD and t.value == name:
        kids.append(_leaf(P, name, t))
    else:
        _restore_lex(P.L, save)


# ───────────────────── Test & Arithmetic Expressions ─────────────────────


def _parse_test_expr(P: _ParseState, closer: str) -> Optional[TsNode]:
    return _parse_test_or(P, closer)


def _parse_test_or(P: _ParseState, closer: str) -> Optional[TsNode]:
    left = _parse_test_and(P, closer)
    if not left:
        return None
    while True:
        _skip_blanks(P.L)
        save = _save_lex(P.L)
        if _peek(P.L) == '|' and _peek(P.L, 1) == '|':
            s = P.L.b
            _advance(P.L); _advance(P.L)
            op = _mk(P, '||', s, P.L.b, [])
            right = _parse_test_and(P, closer)
            if not right:
                _restore_lex(P.L, save)
                break
            left = _mk(P, 'binary_expression', left.startIndex, right.endIndex,
                       [left, op, right])
        else:
            break
    return left


def _parse_test_and(P: _ParseState, closer: str) -> Optional[TsNode]:
    left = _parse_test_unary(P, closer)
    if not left:
        return None
    while True:
        _skip_blanks(P.L)
        if _peek(P.L) == '&' and _peek(P.L, 1) == '&':
            s = P.L.b
            _advance(P.L); _advance(P.L)
            op = _mk(P, '&&', s, P.L.b, [])
            right = _parse_test_unary(P, closer)
            if not right:
                break
            left = _mk(P, 'binary_expression', left.startIndex, right.endIndex,
                       [left, op, right])
        else:
            break
    return left


def _parse_test_unary(P: _ParseState, closer: str) -> Optional[TsNode]:
    _skip_blanks(P.L)
    c = _peek(P.L)
    if c == '(':
        s = P.L.b
        _advance(P.L)
        open_n = _mk(P, '(', s, P.L.b, [])
        inner = _parse_test_or(P, closer)
        _skip_blanks(P.L)
        if _peek(P.L) == ')':
            cs = P.L.b
            _advance(P.L)
            close = _mk(P, ')', cs, P.L.b, [])
        else:
            close = _mk(P, ')', P.L.b, P.L.b, [])
        kids = [open_n, inner, close] if inner else [open_n, close]
        return _mk(P, 'parenthesized_expression', open_n.startIndex,
                   close.endIndex, kids)
    return _parse_test_binary(P, closer)


def _parse_test_negatable_primary(P: _ParseState, closer: str) -> Optional[TsNode]:
    """Parse !-negated or test-operator (-f) or parenthesized primary."""
    _skip_blanks(P.L)
    c = _peek(P.L)
    if c == '!':
        s = P.L.b
        _advance(P.L)
        bang = _mk(P, '!', s, P.L.b, [])
        inner = _parse_test_negatable_primary(P, closer)
        if not inner:
            return bang
        return _mk(P, 'unary_expression', bang.startIndex, inner.endIndex,
                   [bang, inner])
    if c == '-' and _is_ident_start(_peek(P.L, 1)):
        s = P.L.b
        _advance(P.L)
        while _is_ident_char(_peek(P.L)):
            _advance(P.L)
        op = _mk(P, 'test_operator', s, P.L.b, [])
        _skip_blanks(P.L)
        arg = _parse_test_primary(P, closer)
        if not arg:
            return op
        return _mk(P, 'unary_expression', op.startIndex, arg.endIndex, [op, arg])
    return _parse_test_primary(P, closer)


def _parse_test_binary(P: _ParseState, closer: str) -> Optional[TsNode]:
    _skip_blanks(P.L)
    left = _parse_test_negatable_primary(P, closer)
    if not left:
        return None
    _skip_blanks(P.L)
    c = _peek(P.L)
    c1 = _peek(P.L, 1)
    op: Optional[TsNode] = None
    os = P.L.b
    if c == '=' and c1 == '=':
        _advance(P.L); _advance(P.L)
        op = _mk(P, '==', os, P.L.b, [])
    elif c == '!' and c1 == '=':
        _advance(P.L); _advance(P.L)
        op = _mk(P, '!=', os, P.L.b, [])
    elif c == '=' and c1 == '~':
        _advance(P.L); _advance(P.L)
        op = _mk(P, '=~', os, P.L.b, [])
    elif c == '=' and c1 != '=':
        _advance(P.L)
        op = _mk(P, '=', os, P.L.b, [])
    elif c == '<' and c1 != '<':
        _advance(P.L)
        op = _mk(P, '<', os, P.L.b, [])
    elif c == '>' and c1 != '>':
        _advance(P.L)
        op = _mk(P, '>', os, P.L.b, [])
    elif c == '-' and _is_ident_start(c1):
        _advance(P.L)
        while _is_ident_char(_peek(P.L)):
            _advance(P.L)
        op = _mk(P, 'test_operator', os, P.L.b, [])

    if not op:
        return left

    _skip_blanks(P.L)

    if closer == ']]':
        op_text = op.type
        if op_text == '=~':
            _skip_blanks(P.L)
            rc = _peek(P.L)
            rhs: Optional[TsNode] = None
            if rc in ('"', "'"):
                save = _save_lex(P.L)
                if rc == '"':
                    quoted = _parse_double_quoted(P)
                else:
                    quoted = _leaf(P, 'raw_string', _next_token(P.L, 'arg'))
                j = P.L.i
                while j < P.L.len and P.L.src[j] in (' ', '\t'):
                    j += 1
                nc = P.L.src[j] if j < P.L.len else ''
                nc1 = P.L.src[j + 1] if j + 1 < P.L.len else ''
                if ((nc == ']' and nc1 == ']') or
                        (nc == '&' and nc1 == '&') or
                        (nc == '|' and nc1 == '|') or
                        nc == '\n' or nc == ''):
                    rhs = quoted
                else:
                    _restore_lex(P.L, save)
            if not rhs:
                rhs = _parse_test_regex_rhs(P)
            if not rhs:
                return left
            return _mk(P, 'binary_expression', left.startIndex, rhs.endIndex,
                       [left, op, rhs])
        if op_text == '=':
            rhs = _parse_test_regex_rhs(P)
            if not rhs:
                return left
            return _mk(P, 'binary_expression', left.startIndex, rhs.endIndex,
                       [left, op, rhs])
        if op_text in ('==', '!='):
            parts = _parse_test_extglob_rhs(P)
            if not parts:
                return left
            last = parts[-1]
            return _mk(P, 'binary_expression', left.startIndex, last.endIndex,
                       [left, op] + parts)

    right = _parse_test_primary(P, closer)
    if not right:
        return left
    return _mk(P, 'binary_expression', left.startIndex, right.endIndex,
               [left, op, right])


def _parse_test_regex_rhs(P: _ParseState) -> Optional[TsNode]:
    """RHS of =~ in [[ ]] — scan as single (regex) node."""
    _skip_blanks(P.L)
    start = P.L.b
    paren_depth = 0
    bracket_depth = 0
    while P.L.i < P.L.len:
        c = _peek(P.L)
        if c == '\\' and P.L.i + 1 < P.L.len:
            _advance(P.L); _advance(P.L)
            continue
        if c == '\n':
            break
        if paren_depth == 0 and bracket_depth == 0:
            if c == ']' and _peek(P.L, 1) == ']':
                break
            if c in (' ', '\t'):
                j = P.L.i
                while j < P.L.len and P.L.src[j] in (' ', '\t'):
                    j += 1
                nc = P.L.src[j] if j < P.L.len else ''
                nc1 = P.L.src[j + 1] if j + 1 < P.L.len else ''
                if ((nc == ']' and nc1 == ']') or
                        (nc == '&' and nc1 == '&') or
                        (nc == '|' and nc1 == '|')):
                    break
                _advance(P.L)
                continue
        if c == '(':
            paren_depth += 1
        elif c == ')' and paren_depth > 0:
            paren_depth -= 1
        elif c == '[':
            bracket_depth += 1
        elif c == ']' and bracket_depth > 0:
            bracket_depth -= 1
        _advance(P.L)
    if P.L.b == start:
        return None
    return _mk(P, 'regex', start, P.L.b, [])


def _parse_test_extglob_rhs(P: _ParseState) -> List[TsNode]:
    """RHS of ==/!=/= in [[ ]] — returns array of parts."""
    _skip_blanks(P.L)
    parts: List[TsNode] = []
    seg_start = P.L.b
    seg_start_i = P.L.i
    paren_depth = 0

    def flush_seg() -> None:
        nonlocal seg_start, seg_start_i
        if P.L.i > seg_start_i:
            text = P.src[seg_start_i:P.L.i]
            type_ = 'number' if re.match(r'^\d+$', text) else 'extglob_pattern'
            parts.append(_mk(P, type_, seg_start, P.L.b, []))

    while P.L.i < P.L.len:
        c = _peek(P.L)
        if c == '\\' and P.L.i + 1 < P.L.len:
            _advance(P.L); _advance(P.L)
            continue
        if c == '\n':
            break
        if paren_depth == 0:
            if c == ']' and _peek(P.L, 1) == ']':
                break
            if c in (' ', '\t'):
                j = P.L.i
                while j < P.L.len and P.L.src[j] in (' ', '\t'):
                    j += 1
                nc = P.L.src[j] if j < P.L.len else ''
                nc1 = P.L.src[j + 1] if j + 1 < P.L.len else ''
                if ((nc == ']' and nc1 == ']') or
                        (nc == '&' and nc1 == '&') or
                        (nc == '|' and nc1 == '|')):
                    break
                _advance(P.L)
                continue
        if c == '$':
            c1 = _peek(P.L, 1)
            if (c1 == '(' or c1 == '{' or _is_ident_start(c1) or
                    c1 in SPECIAL_VARS):
                flush_seg()
                exp = _parse_dollar_like(P)
                if exp:
                    parts.append(exp)
                seg_start = P.L.b
                seg_start_i = P.L.i
                continue
        if c == '"':
            flush_seg()
            parts.append(_parse_double_quoted(P))
            seg_start = P.L.b
            seg_start_i = P.L.i
            continue
        if c == "'":
            flush_seg()
            tok = _next_token(P.L, 'arg')
            parts.append(_leaf(P, 'raw_string', tok))
            seg_start = P.L.b
            seg_start_i = P.L.i
            continue
        if c == '(':
            paren_depth += 1
        elif c == ')' and paren_depth > 0:
            paren_depth -= 1
        _advance(P.L)

    flush_seg()
    return parts


def _parse_test_primary(P: _ParseState, closer: str) -> Optional[TsNode]:
    _skip_blanks(P.L)
    if closer == ']' and _peek(P.L) == ']':
        return None
    if closer == ']]' and _peek(P.L) == ']' and _peek(P.L, 1) == ']':
        return None
    return _parse_word(P, 'arg')


# ───────────────────────────── Arithmetic ─────────────────────────────

ARITH_PREC = {
    '=': 2, '+=': 2, '-=': 2, '*=': 2, '/=': 2, '%=': 2,
    '<<=': 2, '>>=': 2, '&=': 2, '^=': 2, '|=': 2,
    '||': 4, '&&': 5, '|': 6, '^': 7, '&': 8,
    '==': 9, '!=': 9, '<': 10, '>': 10, '<=': 10, '>=': 10,
    '<<': 11, '>>': 11,
    '+': 12, '-': 12,
    '*': 13, '/': 13, '%': 13,
    '**': 14,
}

ARITH_RIGHT_ASSOC = {
    '=', '+=', '-=', '*=', '/=', '%=', '<<=', '>>=', '&=', '^=', '|=', '**'
}


def _parse_arith_expr(P: _ParseState, stop: str, mode: str = 'var') -> Optional[TsNode]:
    return _parse_arith_ternary(P, stop, mode)


def _parse_arith_comma_list(P: _ParseState, stop: str, mode: str = 'var') -> List[TsNode]:
    """Top-level: comma-separated list."""
    out: List[TsNode] = []
    while True:
        e = _parse_arith_ternary(P, stop, mode)
        if e:
            out.append(e)
        _skip_blanks(P.L)
        if _peek(P.L) == ',' and not _is_arith_stop(P, stop):
            _advance(P.L)
            continue
        break
    return out


def _parse_arith_ternary(P: _ParseState, stop: str, mode: str) -> Optional[TsNode]:
    cond = _parse_arith_binary(P, stop, 0, mode)
    if not cond:
        return None
    _skip_blanks(P.L)
    if _peek(P.L) == '?':
        qs = P.L.b
        _advance(P.L)
        q = _mk(P, '?', qs, P.L.b, [])
        t = _parse_arith_binary(P, ':', 0, mode)
        _skip_blanks(P.L)
        if _peek(P.L) == ':':
            cs = P.L.b
            _advance(P.L)
            colon = _mk(P, ':', cs, P.L.b, [])
        else:
            colon = _mk(P, ':', P.L.b, P.L.b, [])
        f = _parse_arith_ternary(P, stop, mode)
        last = f if f else colon
        kids: List[TsNode] = [cond, q]
        if t:
            kids.append(t)
        kids.append(colon)
        if f:
            kids.append(f)
        return _mk(P, 'ternary_expression', cond.startIndex, last.endIndex, kids)
    return cond


def _scan_arith_op(P: _ParseState) -> Optional[Tuple[str, int]]:
    """Scan next arithmetic binary operator; returns (text, length) or None."""
    c = _peek(P.L)
    c1 = _peek(P.L, 1)
    c2 = _peek(P.L, 2)
    # 3-char
    if c == '<' and c1 == '<' and c2 == '=':
        return ('<<=', 3)
    if c == '>' and c1 == '>' and c2 == '=':
        return ('>>=', 3)
    # 2-char
    if c == '*' and c1 == '*':
        return ('**', 2)
    if c == '<' and c1 == '<':
        return ('<<', 2)
    if c == '>' and c1 == '>':
        return ('>>', 2)
    if c == '=' and c1 == '=':
        return ('==', 2)
    if c == '!' and c1 == '=':
        return ('!=', 2)
    if c == '<' and c1 == '=':
        return ('<=', 2)
    if c == '>' and c1 == '=':
        return ('>=', 2)
    if c == '&' and c1 == '&':
        return ('&&', 2)
    if c == '|' and c1 == '|':
        return ('||', 2)
    if c == '+' and c1 == '=':
        return ('+=', 2)
    if c == '-' and c1 == '=':
        return ('-=', 2)
    if c == '*' and c1 == '=':
        return ('*=', 2)
    if c == '/' and c1 == '=':
        return ('/=', 2)
    if c == '%' and c1 == '=':
        return ('%=', 2)
    if c == '&' and c1 == '=':
        return ('&=', 2)
    if c == '^' and c1 == '=':
        return ('^=', 2)
    if c == '|' and c1 == '=':
        return ('|=', 2)
    # 1-char — but NOT ++ --
    if c == '+' and c1 != '+':
        return ('+', 1)
    if c == '-' and c1 != '-':
        return ('-', 1)
    if c == '*':
        return ('*', 1)
    if c == '/':
        return ('/', 1)
    if c == '%':
        return ('%', 1)
    if c == '<':
        return ('<', 1)
    if c == '>':
        return ('>', 1)
    if c == '&':
        return ('&', 1)
    if c == '|':
        return ('|', 1)
    if c == '^':
        return ('^', 1)
    if c == '=':
        return ('=', 1)
    return None


def _parse_arith_binary(P: _ParseState, stop: str, min_prec: int,
                         mode: str) -> Optional[TsNode]:
    """Precedence-climbing binary expression parser."""
    left = _parse_arith_unary(P, stop, mode)
    if not left:
        return None
    while True:
        _skip_blanks(P.L)
        if _is_arith_stop(P, stop):
            break
        if _peek(P.L) == ',':
            break
        op_info = _scan_arith_op(P)
        if not op_info:
            break
        op_text, op_len = op_info
        prec = ARITH_PREC.get(op_text)
        if prec is None or prec < min_prec:
            break
        os = P.L.b
        for _ in range(op_len):
            _advance(P.L)
        op = _mk(P, op_text, os, P.L.b, [])
        next_min = prec if op_text in ARITH_RIGHT_ASSOC else prec + 1
        right = _parse_arith_binary(P, stop, next_min, mode)
        if not right:
            break
        left = _mk(P, 'binary_expression', left.startIndex, right.endIndex,
                   [left, op, right])
    return left


def _parse_arith_unary(P: _ParseState, stop: str, mode: str) -> Optional[TsNode]:
    _skip_blanks(P.L)
    if _is_arith_stop(P, stop):
        return None
    c = _peek(P.L)
    c1 = _peek(P.L, 1)
    # Prefix ++ --
    if (c == '+' and c1 == '+') or (c == '-' and c1 == '-'):
        s = P.L.b
        _advance(P.L); _advance(P.L)
        op = _mk(P, c + c1, s, P.L.b, [])
        inner = _parse_arith_unary(P, stop, mode)
        if not inner:
            return op
        return _mk(P, 'unary_expression', op.startIndex, inner.endIndex, [op, inner])
    if c in ('-', '+', '!', '~'):
        if mode != 'var' and c == '-' and _is_digit(c1):
            s = P.L.b
            _advance(P.L)
            while _is_digit(_peek(P.L)):
                _advance(P.L)
            return _mk(P, 'number', s, P.L.b, [])
        s = P.L.b
        _advance(P.L)
        op = _mk(P, c, s, P.L.b, [])
        inner = _parse_arith_unary(P, stop, mode)
        if not inner:
            return op
        return _mk(P, 'unary_expression', op.startIndex, inner.endIndex, [op, inner])
    return _parse_arith_postfix(P, stop, mode)


def _parse_arith_postfix(P: _ParseState, stop: str, mode: str) -> Optional[TsNode]:
    prim = _parse_arith_primary(P, stop, mode)
    if not prim:
        return None
    c = _peek(P.L)
    c1 = _peek(P.L, 1)
    if (c == '+' and c1 == '+') or (c == '-' and c1 == '-'):
        s = P.L.b
        _advance(P.L); _advance(P.L)
        op = _mk(P, c + c1, s, P.L.b, [])
        return _mk(P, 'postfix_expression', prim.startIndex, op.endIndex, [prim, op])
    return prim


def _parse_arith_primary(P: _ParseState, stop: str, mode: str) -> Optional[TsNode]:
    _skip_blanks(P.L)
    if _is_arith_stop(P, stop):
        return None
    c = _peek(P.L)
    if c == '(':
        s = P.L.b
        _advance(P.L)
        open_n = _mk(P, '(', s, P.L.b, [])
        inners = _parse_arith_comma_list(P, ')', mode)
        _skip_blanks(P.L)
        if _peek(P.L) == ')':
            cs = P.L.b
            _advance(P.L)
            close = _mk(P, ')', cs, P.L.b, [])
        else:
            close = _mk(P, ')', P.L.b, P.L.b, [])
        return _mk(P, 'parenthesized_expression', open_n.startIndex,
                   close.endIndex, [open_n] + inners + [close])
    if c == '"':
        return _parse_double_quoted(P)
    if c == '$':
        return _parse_dollar_like(P)
    if _is_digit(c):
        s = P.L.b
        while _is_digit(_peek(P.L)):
            _advance(P.L)
        # Hex: 0x1f
        if (P.L.b - s == 1 and c == '0' and
                _peek(P.L) in ('x', 'X')):
            _advance(P.L)
            while _is_hex_digit(_peek(P.L)):
                _advance(P.L)
        # Base notation: BASE#DIGITS
        elif _peek(P.L) == '#':
            _advance(P.L)
            while _is_base_digit(_peek(P.L)):
                _advance(P.L)
        return _mk(P, 'number', s, P.L.b, [])
    if _is_ident_start(c):
        s = P.L.b
        while _is_ident_char(_peek(P.L)):
            _advance(P.L)
        nc = _peek(P.L)
        # Assignment in 'assign' mode
        if mode == 'assign':
            _skip_blanks(P.L)
            ac = _peek(P.L)
            ac1 = _peek(P.L, 1)
            if ac == '=' and ac1 != '=':
                vn = _mk(P, 'variable_name', s, P.L.b, [])
                es = P.L.b
                _advance(P.L)
                eq = _mk(P, '=', es, P.L.b, [])
                val = _parse_arith_ternary(P, stop, mode)
                end = val.endIndex if val else eq.endIndex
                kids = [vn, eq, val] if val else [vn, eq]
                return _mk(P, 'variable_assignment', s, end, kids)
        # Subscript
        if nc == '[':
            vn = _mk(P, 'variable_name', s, P.L.b, [])
            br_s = P.L.b
            _advance(P.L)
            br_open = _mk(P, '[', br_s, P.L.b, [])
            idx = _parse_arith_ternary(P, ']', 'var')
            if not idx:
                idx = _parse_dollar_like(P)
            _skip_blanks(P.L)
            if _peek(P.L) == ']':
                cs = P.L.b
                _advance(P.L)
                br_close = _mk(P, ']', cs, P.L.b, [])
            else:
                br_close = _mk(P, ']', P.L.b, P.L.b, [])
            kids = [vn, br_open, idx, br_close] if idx else [vn, br_open, br_close]
            return _mk(P, 'subscript', s, br_close.endIndex, kids)
        # Bare identifier
        ident_type = 'variable_name' if mode == 'var' else 'word'
        return _mk(P, ident_type, s, P.L.b, [])
    return None


def _is_arith_stop(P: _ParseState, stop: str) -> bool:
    c = _peek(P.L)
    if stop == '))':
        return c == ')' and _peek(P.L, 1) == ')'
    if stop == ')':
        return c == ')'
    if stop == ';':
        return c == ';'
    if stop == ':':
        return c == ':'
    if stop == ']':
        return c == ']'
    if stop == '}':
        return c == '}'
    if stop == ':}':
        return c in (':', '}')
    return c in ('', '\n')
