"""
Python port of utils/markdown.ts
Source: claude-code-source/utils/markdown.ts (381 lines)

Markdown rendering / formatting utilities for terminal (ANSI) output.
Uses the 'rich' library for terminal rendering, with a lightweight
fallback for environments where 'rich' is not available.
"""

from __future__ import annotations

import re
import textwrap
from io import StringIO
from typing import Optional

# ---------------------------------------------------------------------------
# ANSI escape helpers
# ---------------------------------------------------------------------------

_ANSI_RESET = "\x1b[0m"
_ANSI_BOLD = "\x1b[1m"
_ANSI_ITALIC = "\x1b[3m"
_ANSI_UNDERLINE = "\x1b[4m"
_ANSI_DIM = "\x1b[2m"
_ANSI_CODE_BG = "\x1b[48;5;236m"  # dark grey background for inline code


def _ansi_bold(text: str) -> str:
    return f"{_ANSI_BOLD}{text}{_ANSI_RESET}"


def _ansi_italic(text: str) -> str:
    return f"{_ANSI_ITALIC}{text}{_ANSI_RESET}"


def _ansi_bold_italic_underline(text: str) -> str:
    return f"{_ANSI_BOLD}{_ANSI_ITALIC}{_ANSI_UNDERLINE}{text}{_ANSI_RESET}"


def _ansi_dim(text: str) -> str:
    return f"{_ANSI_DIM}{text}{_ANSI_RESET}"


def _ansi_code(text: str) -> str:
    return f"{_ANSI_CODE_BG}{text}{_ANSI_RESET}"


def _strip_ansi(text: str) -> str:
    """Remove all ANSI escape sequences from a string."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


# ---------------------------------------------------------------------------
# Strip-markdown: remove formatting marks to get plain text
# ---------------------------------------------------------------------------

# Patterns to strip (order matters)
_STRIP_PATTERNS: list[tuple[str, str]] = [
    # ATX headings: ## Title → Title
    (r"^#{1,6}\s+", ""),
    # Bold + italic: ***text*** or ___text___
    (r"\*{3}(.+?)\*{3}", r"\1"),
    (r"_{3}(.+?)_{3}", r"\1"),
    # Bold: **text** or __text__
    (r"\*{2}(.+?)\*{2}", r"\1"),
    (r"_{2}(.+?)_{2}", r"\1"),
    # Italic: *text* or _text_
    (r"\*(.+?)\*", r"\1"),
    (r"_(.+?)_", r"\1"),
    # Inline code: `code`
    (r"`(.+?)`", r"\1"),
    # Links: [text](url) → text
    (r"\[([^\]]+)\]\([^\)]+\)", r"\1"),
    # Images: ![alt](url) → alt
    (r"!\[([^\]]*)\]\([^\)]+\)", r"\1"),
    # Strikethrough: ~~text~~
    (r"~~(.+?)~~", r"\1"),
    # Horizontal rule
    (r"^(\*{3,}|-{3,}|_{3,})$", ""),
    # Blockquote prefix
    (r"^>\s?", ""),
    # Unordered list bullets
    (r"^[-*+]\s+", ""),
    # Ordered list numbers
    (r"^\d+\.\s+", ""),
]

_COMPILED_STRIP_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pat, re.MULTILINE), repl)
    for pat, repl in _STRIP_PATTERNS
]


def strip_markdown(text: str) -> str:
    """
    Remove Markdown formatting marks, returning plain text.

    Mirrors TS ``stripMarkdown / stripAnsi`` usage in the codebase.
    """
    result = text
    for pattern, replacement in _COMPILED_STRIP_PATTERNS:
        result = pattern.sub(replacement, result)
    # Collapse multiple blank lines
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


# ---------------------------------------------------------------------------
# Format code block
# ---------------------------------------------------------------------------

def format_code_block(code: str, language: str = "") -> str:
    """
    Format a code block for terminal output.

    Tries to use Pygments for syntax highlighting if available,
    otherwise falls back to simple dim styling.

    Mirrors TS ``highlight.highlight(token.text, { language })``.
    """
    try:
        from pygments import highlight
        from pygments.formatters import Terminal256Formatter
        from pygments.lexers import get_lexer_by_name, TextLexer
        from pygments.util import ClassNotFound

        try:
            lexer = get_lexer_by_name(language or "text", stripall=False)
        except ClassNotFound:
            lexer = TextLexer()

        formatter = Terminal256Formatter(style="monokai")
        return highlight(code, lexer, formatter).rstrip("\n")
    except ImportError:
        # No Pygments available — return with dim styling
        lines = code.splitlines()
        return "\n".join(f"  {_ansi_dim(line)}" for line in lines)


# ---------------------------------------------------------------------------
# Markdown → ANSI renderer
# ---------------------------------------------------------------------------

def _render_heading(text: str, level: int) -> str:
    if level == 1:
        return _ansi_bold_italic_underline(text) + "\n\n"
    elif level == 2:
        return _ansi_bold(text) + "\n\n"
    else:
        return _ansi_bold(text) + "\n\n"


def _render_blockquote(text: str) -> str:
    bar = _ansi_dim("│")
    rendered = render_markdown(text)  # recurse on inner content
    lines = rendered.splitlines()
    return "\n".join(f"{bar} {_ansi_italic(line)}" if line.strip() else line for line in lines) + "\n"


def _pad_aligned(
    content: str,
    display_width: int,
    target_width: int,
    align: Optional[str],
) -> str:
    """Pad content to target_width according to alignment."""
    padding = max(0, target_width - display_width)
    if align == "center":
        left = padding // 2
        return " " * left + content + " " * (padding - left)
    if align == "right":
        return " " * padding + content
    return content + " " * padding


def _render_table(
    headers: list[str],
    rows: list[list[str]],
    aligns: list[Optional[str]],
) -> str:
    """Render a Markdown table as an ANSI-formatted string."""
    col_count = len(headers)
    # compute column widths
    widths = [max(len(_strip_ansi(h)), 3) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < col_count:
                widths[i] = max(widths[i], len(_strip_ansi(cell)))

    def fmt_row(cells: list[str], bold: bool = False) -> str:
        parts = []
        for i, cell in enumerate(cells):
            width = widths[i] if i < len(widths) else len(_strip_ansi(cell))
            align = aligns[i] if i < len(aligns) else None
            padded = _pad_aligned(cell, len(_strip_ansi(cell)), width, align)
            parts.append(_ansi_bold(padded) if bold else padded)
        return "| " + " | ".join(parts) + " |"

    sep_row = "|" + "|".join("-" * (w + 2) for w in widths) + "|"
    lines = [fmt_row(headers, bold=True), sep_row]
    for row in rows:
        # pad row to col_count
        padded_row = row[:col_count] + [""] * max(0, col_count - len(row))
        lines.append(fmt_row(padded_row))
    return "\n".join(lines) + "\n\n"


# ---------------------------------------------------------------------------
# Main render function using a simple regex-based tokenizer
# ---------------------------------------------------------------------------

def render_markdown(text: str) -> str:
    """
    Render Markdown to ANSI terminal-formatted string.

    Handles: headings, bold, italic, inline code, fenced code blocks,
    unordered/ordered lists, blockquotes, horizontal rules, links, tables.

    Mirrors TS ``applyMarkdown(content, theme, highlight)``.
    """
    if not text:
        return ""

    output: list[str] = []
    lines = text.splitlines(keepends=True)
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip("\n").rstrip("\r")

        # --- Fenced code block ---
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            code_lines: list[str] = []
            i += 1
            while i < len(lines):
                inner = lines[i].rstrip("\n").rstrip("\r")
                if inner.startswith("```"):
                    i += 1
                    break
                code_lines.append(lines[i])
                i += 1
            code = "".join(code_lines).rstrip("\n")
            output.append(format_code_block(code, lang) + "\n")
            continue

        # --- ATX Heading ---
        heading_match = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            content = _inline_format(heading_match.group(2))
            output.append(_render_heading(content, level))
            i += 1
            continue

        # --- Horizontal rule ---
        if re.match(r"^(\*{3,}|-{3,}|_{3,})\s*$", stripped):
            output.append("---\n")
            i += 1
            continue

        # --- Blockquote ---
        if stripped.startswith(">"):
            bq_lines: list[str] = []
            while i < len(lines) and lines[i].rstrip("\n").startswith(">"):
                bq_lines.append(lines[i].rstrip("\n").lstrip(">").lstrip(" "))
                i += 1
            inner = "\n".join(bq_lines)
            bar = _ansi_dim("│")
            rendered_inner = render_markdown(inner)
            bq_out = "\n".join(
                f"{bar} {_ansi_italic(l)}" if l.strip() else l
                for l in rendered_inner.splitlines()
            )
            output.append(bq_out + "\n")
            continue

        # --- Table (simple detection: line with |) ---
        if "|" in stripped and i + 1 < len(lines) and re.match(r"^\|?[\s\-:]+\|", lines[i + 1]):
            # Parse table
            def parse_cells(row_line: str) -> list[str]:
                row_line = row_line.strip()
                if row_line.startswith("|"):
                    row_line = row_line[1:]
                if row_line.endswith("|"):
                    row_line = row_line[:-1]
                return [c.strip() for c in row_line.split("|")]

            headers = [_inline_format(c) for c in parse_cells(stripped)]
            i += 1  # skip separator
            sep_line = lines[i].rstrip("\n")
            aligns: list[Optional[str]] = []
            for cell in parse_cells(sep_line):
                if cell.startswith(":") and cell.endswith(":"):
                    aligns.append("center")
                elif cell.endswith(":"):
                    aligns.append("right")
                else:
                    aligns.append(None)
            i += 1
            table_rows: list[list[str]] = []
            while i < len(lines) and "|" in lines[i]:
                row_stripped = lines[i].rstrip("\n")
                if not row_stripped.strip():
                    break
                table_rows.append([_inline_format(c) for c in parse_cells(row_stripped)])
                i += 1
            output.append(_render_table(headers, table_rows, aligns))
            continue

        # --- Unordered list item ---
        ul_match = re.match(r"^(\s*)([-*+])\s+(.*)", stripped)
        if ul_match:
            indent = len(ul_match.group(1))
            depth = indent // 2
            content = _inline_format(ul_match.group(3))
            prefix = "  " * depth + "-"
            output.append(f"{prefix} {content}\n")
            i += 1
            continue

        # --- Ordered list item ---
        ol_match = re.match(r"^(\s*)(\d+)\.\s+(.*)", stripped)
        if ol_match:
            indent = len(ol_match.group(1))
            depth = indent // 2
            num = ol_match.group(2)
            content = _inline_format(ol_match.group(3))
            prefix = "  " * depth + f"{num}."
            output.append(f"{prefix} {content}\n")
            i += 1
            continue

        # --- Blank line ---
        if not stripped:
            output.append("\n")
            i += 1
            continue

        # --- Paragraph / plain text ---
        output.append(_inline_format(stripped) + "\n")
        i += 1

    return "".join(output).strip()


# ---------------------------------------------------------------------------
# Inline formatting (bold, italic, code, links)
# ---------------------------------------------------------------------------

def _inline_format(text: str) -> str:
    """Apply inline Markdown formatting: bold, italic, code, links."""

    # Inline code (highest priority to avoid double-processing)
    parts: list[str] = []
    last = 0
    for m in re.finditer(r"`([^`]+)`", text):
        parts.append(_apply_inline_no_code(text[last:m.start()]))
        parts.append(_ansi_code(m.group(1)))
        last = m.end()
    parts.append(_apply_inline_no_code(text[last:]))
    return "".join(parts)


def _apply_inline_no_code(text: str) -> str:
    """Apply bold, italic, links (but not code) to a text segment."""

    # Bold + italic: ***text*** or ___text___
    text = re.sub(
        r"\*{3}(.+?)\*{3}|_{3}(.+?)_{3}",
        lambda m: _ansi_bold(_ansi_italic(m.group(1) or m.group(2))),
        text,
    )
    # Bold: **text** or __text__
    text = re.sub(
        r"\*{2}(.+?)\*{2}|_{2}(.+?)_{2}",
        lambda m: _ansi_bold(m.group(1) or m.group(2)),
        text,
    )
    # Italic: *text* or _text_  (single, not double)
    text = re.sub(
        r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)",
        lambda m: _ansi_italic(m.group(1) or m.group(2)),
        text,
    )
    # Links: [text](url)
    def _format_link(m: re.Match[str]) -> str:
        link_text = m.group(1)
        url = m.group(2)
        if url.startswith("mailto:"):
            return url[len("mailto:"):]
        if link_text and link_text != url:
            # OSC 8 hyperlink if terminal supports it
            return f"\x1b]8;;{url}\x1b\\{link_text}\x1b]8;;\x1b\\"
        return url

    text = re.sub(r"\[([^\]]+)\]\(([^\)]+)\)", _format_link, text)
    # Images: ![alt](url) → show URL
    text = re.sub(r"!\[([^\]]*)\]\(([^\)]+)\)", lambda m: m.group(2), text)
    return text
