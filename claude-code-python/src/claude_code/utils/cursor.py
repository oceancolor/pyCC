# 原始 TS: utils/cursor.ts (光标工具，非 Cursor IDE)
"""终端光标控制和文本光标实现

包含两部分：
1. ANSI 终端光标控制码（来自原 stub）
2. Cursor / MeasuredText 类 — 文本输入行编辑器光标（从 Cursor.ts 移植）
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# ANSI terminal cursor control codes (original stub content)
# ---------------------------------------------------------------------------

def cursor_up(count: int = 1) -> str:
    """Move cursor up N lines."""
    return f"\x1b[{count}A"

def cursor_down(count: int = 1) -> str:
    """Move cursor down N lines."""
    return f"\x1b[{count}B"

def cursor_forward(count: int = 1) -> str:
    """Move cursor forward (right) N columns."""
    return f"\x1b[{count}C"

def cursor_back(count: int = 1) -> str:
    """Move cursor backward (left) N columns."""
    return f"\x1b[{count}D"

def cursor_to_column(col: int) -> str:
    """Move cursor to column N (1-based)."""
    return f"\x1b[{col}G"

def cursor_hide() -> str:
    """Hide the cursor."""
    return "\x1b[?25l"

def cursor_show() -> str:
    """Show the cursor."""
    return "\x1b[?25h"

def erase_line() -> str:
    """Erase from cursor to end of line."""
    return "\x1b[K"

def erase_lines(count: int) -> str:
    """Erase N lines above cursor."""
    result = ""
    for _ in range(count):
        result += erase_line() + cursor_up() + "\r"
    return result


# ---------------------------------------------------------------------------
# Kill ring (for Emacs-style kill/yank)
# ---------------------------------------------------------------------------

_kill_ring: List[str] = []
_kill_ring_index: int = 0
_last_yank_start: int = 0
_last_yank_length: int = 0
_KILL_RING_MAX = 60


def get_last_kill() -> str:
    return _kill_ring[0] if _kill_ring else ''


def get_kill_ring_entry(index: int) -> str:
    if not _kill_ring:
        return ''
    return _kill_ring[index % len(_kill_ring)]


def push_kill(text: str) -> None:
    global _kill_ring, _kill_ring_index
    if not text:
        return
    _kill_ring.insert(0, text)
    if len(_kill_ring) > _KILL_RING_MAX:
        _kill_ring = _kill_ring[:_KILL_RING_MAX]
    _kill_ring_index = 0


def rotate_kill_ring() -> None:
    global _kill_ring_index
    if _kill_ring:
        _kill_ring_index = (_kill_ring_index + 1) % len(_kill_ring)


def peek_kill_ring() -> dict:
    """Return {text, start, length} for yank operation."""
    text = _kill_ring[_kill_ring_index] if _kill_ring else ''
    return {'text': text, 'start': _last_yank_start, 'length': _last_yank_length}


def set_last_yank(start: int, length: int) -> None:
    global _last_yank_start, _last_yank_length
    _last_yank_start = start
    _last_yank_length = length


# ---------------------------------------------------------------------------
# Grapheme / string-width helpers (simplified — no full Unicode Segmentation)
# ---------------------------------------------------------------------------

def _string_width(text: str) -> int:
    """Approximate display width of text (East Asian wide chars count as 2)."""
    width = 0
    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        if eaw in ('W', 'F'):
            width += 2
        elif unicodedata.category(ch) in ('Mn', 'Me', 'Cf'):
            pass  # zero-width combining / format chars
        else:
            width += 1
    return width


# ANSI escape sequence pattern
_ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]|\x1b[()][0-9A-Za-z]')


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub('', text)


def _wrap_ansi(text: str, columns: int) -> str:
    """Very simple word-wrap at display-width boundary (no ANSI awareness)."""
    if columns <= 0:
        return text
    lines: List[str] = []
    current = ''
    current_width = 0
    for ch in text:
        if ch == '\n':
            lines.append(current)
            current = ''
            current_width = 0
            continue
        w = _string_width(ch)
        if current_width + w > columns:
            lines.append(current)
            current = ch
            current_width = w
        else:
            current += ch
            current_width += w
    lines.append(current)
    return '\n'.join(lines)


def _get_grapheme_boundaries(text: str) -> List[int]:
    """
    Return list of byte (code-unit) offsets at which grapheme clusters start,
    plus a final sentinel equal to len(text).
    Simplified: treat each Unicode code point as a grapheme cluster except
    combining marks that follow a base character.
    """
    if not text:
        return [0]
    boundaries = [0]
    combining_cats = {'Mn', 'Me', 'Cf'}
    i = 0
    while i < len(text):
        cat = unicodedata.category(text[i])
        i += 1
        # skip following combining chars
        while i < len(text) and unicodedata.category(text[i]) in combining_cats:
            i += 1
        boundaries.append(i)
    # ensure final sentinel
    if boundaries[-1] != len(text):
        boundaries.append(len(text))
    return boundaries


@dataclass
class _WrappedLine:
    """One visual line after wrapping."""
    text: str
    start_offset: int           # byte offset in original text where this line starts
    ends_with_newline: bool = False
    is_preceded_by_newline: bool = False


@dataclass
class Position:
    line: int
    column: int


# ---------------------------------------------------------------------------
# MeasuredText: pre-computes grapheme boundaries and wrapped lines
# ---------------------------------------------------------------------------

class MeasuredText:
    """
    Wraps a text string with pre-computed grapheme boundaries and wrapped lines.
    Ported from the inner class in Cursor.ts.
    """

    def __init__(self, text: str, columns: int) -> None:
        self.text = text
        self.columns = columns
        self._boundaries: Optional[List[int]] = None
        self._wrapped_lines: Optional[List[_WrappedLine]] = None
        self.navigation_cache: Dict[str, int] = {}

    # -- grapheme boundaries -------------------------------------------------

    def get_grapheme_boundaries(self) -> List[int]:
        if self._boundaries is None:
            self._boundaries = _get_grapheme_boundaries(self.text)
        return self._boundaries

    def _binary_search_boundary(self, boundaries: List[int], offset: int, forward: bool) -> int:
        lo, hi = 0, len(boundaries) - 1
        if forward:
            # find smallest boundary > offset
            result = len(self.text)
            while lo <= hi:
                mid = (lo + hi) // 2
                if boundaries[mid] > offset:
                    result = boundaries[mid]
                    hi = mid - 1
                else:
                    lo = mid + 1
            return result
        else:
            # find largest boundary < offset
            result = 0
            while lo <= hi:
                mid = (lo + hi) // 2
                if boundaries[mid] < offset:
                    result = boundaries[mid]
                    lo = mid + 1
                else:
                    hi = mid - 1
            return result

    def next_offset(self, offset: int) -> int:
        key = f"next:{offset}"
        if key in self.navigation_cache:
            return self.navigation_cache[key]
        boundaries = self.get_grapheme_boundaries()
        result = self._binary_search_boundary(boundaries, offset, True)
        self.navigation_cache[key] = result
        return result

    def prev_offset(self, offset: int) -> int:
        if offset <= 0:
            return 0
        key = f"prev:{offset}"
        if key in self.navigation_cache:
            return self.navigation_cache[key]
        boundaries = self.get_grapheme_boundaries()
        result = self._binary_search_boundary(boundaries, offset, False)
        self.navigation_cache[key] = result
        return result

    def snap_to_grapheme_boundary(self, offset: int) -> int:
        if offset <= 0:
            return 0
        if offset >= len(self.text):
            return len(self.text)
        boundaries = self.get_grapheme_boundaries()
        lo, hi = 0, len(boundaries) - 1
        while lo < hi:
            mid = (lo + hi + 1) >> 1
            if boundaries[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return boundaries[lo]

    # -- wrapped lines -------------------------------------------------------

    @property
    def wrapped_lines(self) -> List[_WrappedLine]:
        if self._wrapped_lines is None:
            self._wrapped_lines = self._compute_wrapped_lines()
        return self._wrapped_lines

    def _compute_wrapped_lines(self) -> List[_WrappedLine]:
        """Split text into visual wrapped lines."""
        if not self.text:
            return [_WrappedLine(text='', start_offset=0, ends_with_newline=False,
                                 is_preceded_by_newline=True)]
        lines: List[_WrappedLine] = []
        # Split on hard newlines first
        parts = self.text.split('\n')
        offset = 0
        for part_idx, part in enumerate(parts):
            preceded_by_newline = part_idx == 0 or True  # first line or after \n
            # Wrap each part to columns
            if self.columns > 0:
                wrapped_parts = self._soft_wrap(part, self.columns)
            else:
                wrapped_parts = [part] if part else ['']
            for w_idx, wtext in enumerate(wrapped_parts):
                is_preceded = w_idx == 0  # first wrapped chunk of this hard line
                ends_with_nl = (part_idx < len(parts) - 1) and (w_idx == len(wrapped_parts) - 1)
                lines.append(_WrappedLine(
                    text=wtext,
                    start_offset=offset,
                    ends_with_newline=ends_with_nl,
                    is_preceded_by_newline=is_preceded,
                ))
                offset += len(wtext)
            if part_idx < len(parts) - 1:
                offset += 1  # for the '\n'
        if not lines:
            lines.append(_WrappedLine(text='', start_offset=0, ends_with_newline=False,
                                      is_preceded_by_newline=True))
        return lines

    def _soft_wrap(self, text: str, columns: int) -> List[str]:
        """Break a single (no-newline) string into visual lines of at most `columns` width."""
        if not text:
            return ['']
        result: List[str] = []
        current = ''
        current_width = 0
        for ch in text:
            w = _string_width(ch)
            if current_width + w > columns:
                result.append(current)
                current = ch
                current_width = w
            else:
                current += ch
                current_width += w
        result.append(current)
        return result

    def get_line(self, line_num: int) -> _WrappedLine:
        lines = self.wrapped_lines
        if line_num < 0 or line_num >= len(lines):
            # return empty sentinel
            return _WrappedLine(text='', start_offset=len(self.text),
                                ends_with_newline=False, is_preceded_by_newline=False)
        return lines[line_num]

    def get_offset(self, position: Position) -> int:
        """Return byte offset for a given (line, column) position."""
        wrapped_line = self.get_line(position.line)
        if not wrapped_line.text and position.column == 0:
            return wrapped_line.start_offset

        leading_whitespace = len(wrapped_line.text) - len(wrapped_line.text.lstrip())
        display_column_with_leading = position.column + leading_whitespace
        string_index = self._display_width_to_string_index(wrapped_line.text,
                                                           display_column_with_leading)
        offset = wrapped_line.start_offset + string_index
        line_end = wrapped_line.start_offset + len(wrapped_line.text)
        max_offset = line_end
        line_display_width = _string_width(wrapped_line.text)
        if wrapped_line.ends_with_newline and position.column > line_display_width:
            max_offset = line_end + 1
        return min(offset, max_offset)

    def get_line_length(self, line: int) -> int:
        return _string_width(self.get_line(line).text)

    def get_position_from_offset(self, offset: int) -> Position:
        lines = self.wrapped_lines
        for line_num, current_line in enumerate(lines):
            next_line = lines[line_num + 1] if line_num + 1 < len(lines) else None
            if (offset >= current_line.start_offset and
                    (next_line is None or offset < next_line.start_offset)):
                string_pos_in_line = offset - current_line.start_offset
                if current_line.is_preceded_by_newline:
                    display_column = self._string_index_to_display_width(
                        current_line.text, string_pos_in_line)
                else:
                    leading = len(current_line.text) - len(current_line.text.lstrip())
                    if string_pos_in_line < leading:
                        display_column = 0
                    else:
                        trimmed = current_line.text.lstrip()
                        pos_in_trimmed = string_pos_in_line - leading
                        display_column = self._string_index_to_display_width(
                            trimmed, pos_in_trimmed)
                return Position(line=line_num, column=max(0, display_column))
        # past end
        line = len(lines) - 1
        last_line = lines[line]
        return Position(line=line, column=_string_width(last_line.text))

    @property
    def line_count(self) -> int:
        return len(self.wrapped_lines)

    def _display_width_to_string_index(self, text: str, display_width: int) -> int:
        """Return the string index at which the given display width is reached."""
        width = 0
        for i, ch in enumerate(text):
            w = _string_width(ch)
            if width + w > display_width:
                return i
            width += w
        return len(text)

    def _string_index_to_display_width(self, text: str, string_index: int) -> int:
        """Return display width of text[:string_index]."""
        return _string_width(text[:string_index])


# ---------------------------------------------------------------------------
# WordBoundary helpers
# ---------------------------------------------------------------------------

@dataclass
class _WordBoundary:
    offset: int
    is_word_like: bool


def _get_word_boundaries(text: str) -> List[_WordBoundary]:
    """
    Return word boundaries for word-motion commands (Emacs-style).
    A boundary is placed at the start and end of each alphanumeric run.
    """
    boundaries: List[_WordBoundary] = [_WordBoundary(offset=0, is_word_like=False)]
    in_word = False
    for i, ch in enumerate(text):
        is_word_char = ch.isalnum() or ch == '_'
        if is_word_char and not in_word:
            boundaries.append(_WordBoundary(offset=i, is_word_like=True))
            in_word = True
        elif not is_word_char and in_word:
            boundaries.append(_WordBoundary(offset=i, is_word_like=False))
            in_word = False
    boundaries.append(_WordBoundary(offset=len(text), is_word_like=False))
    return boundaries


# ---------------------------------------------------------------------------
# Cursor class — text-editing cursor (ported from Cursor.ts)
# ---------------------------------------------------------------------------

class Cursor:
    """
    Immutable text-editing cursor.
    Holds a text string and an offset (byte index). All mutation methods
    return new Cursor instances.

    Ported from utils/Cursor.ts.
    """

    def __init__(self, text: str, offset: int, columns: int = 80) -> None:
        self._text = text
        self._offset = max(0, min(offset, len(text)))
        self._columns = columns
        self._measured: Optional[MeasuredText] = None

    # -- properties ----------------------------------------------------------

    @property
    def text(self) -> str:
        return self._text

    @property
    def offset(self) -> int:
        return self._offset

    @property
    def columns(self) -> int:
        return self._columns

    @property
    def measured_text(self) -> MeasuredText:
        if self._measured is None:
            self._measured = MeasuredText(self._text, self._columns)
        return self._measured

    # -- factory helpers -----------------------------------------------------

    def _with(self, text: Optional[str] = None, offset: Optional[int] = None) -> 'Cursor':
        t = text if text is not None else self._text
        o = offset if offset is not None else self._offset
        return Cursor(t, o, self._columns)

    # -- grapheme accessors --------------------------------------------------

    def grapheme_at(self, pos: int) -> str:
        """Return the grapheme cluster starting at pos, or '' if at end."""
        if pos >= len(self._text):
            return ''
        end = self.measured_text.next_offset(pos)
        return self._text[pos:end]

    # -- basic navigation ----------------------------------------------------

    def left(self) -> 'Cursor':
        new_offset = self.measured_text.prev_offset(self._offset)
        return self._with(offset=new_offset)

    def right(self) -> 'Cursor':
        if self._offset >= len(self._text):
            return self
        new_offset = self.measured_text.next_offset(self._offset)
        return self._with(offset=new_offset)

    def start_of_first_line(self) -> 'Cursor':
        return self._with(offset=0)

    def end_of_last_line(self) -> 'Cursor':
        return self._with(offset=len(self._text))

    def end_of_line(self) -> 'Cursor':
        """Move to end of current visual line (before newline if present)."""
        pos = self._offset
        while pos < len(self._text) and self._text[pos] != '\n':
            pos = self.measured_text.next_offset(pos)
            if pos == len(self._text):
                break
        return self._with(offset=pos)

    def start_of_line(self) -> 'Cursor':
        """Move to start of current visual line."""
        pos = self._offset
        while pos > 0 and self._text[pos - 1] != '\n':
            pos = self.measured_text.prev_offset(pos)
        return self._with(offset=pos)

    def first_non_blank_in_logical_line(self) -> 'Cursor':
        """Move to first non-whitespace char in logical line."""
        start = self._get_logical_line_bounds()[0]
        pos = start
        while pos < len(self._text) and self._text[pos] in (' ', '\t'):
            pos += 1
        return self._with(offset=pos)

    def _get_logical_line_bounds(self) -> Tuple[int, int]:
        """Return (start, end) byte offsets of the logical (hard) line."""
        start = self._offset
        while start > 0 and self._text[start - 1] != '\n':
            start -= 1
        end = self._offset
        while end < len(self._text) and self._text[end] != '\n':
            end += 1
        return start, end

    def up(self) -> 'Cursor':
        """Move one visual line up."""
        pos = self.measured_text.get_position_from_offset(self._offset)
        if pos.line == 0:
            return self._with(offset=0)
        new_pos = Position(line=pos.line - 1, column=pos.column)
        new_offset = self.measured_text.get_offset(new_pos)
        return self._with(offset=new_offset)

    def down(self) -> 'Cursor':
        """Move one visual line down."""
        pos = self.measured_text.get_position_from_offset(self._offset)
        if pos.line >= self.measured_text.line_count - 1:
            return self._with(offset=len(self._text))
        new_pos = Position(line=pos.line + 1, column=pos.column)
        new_offset = self.measured_text.get_offset(new_pos)
        return self._with(offset=new_offset)

    # -- word motion ---------------------------------------------------------

    def word_right(self) -> 'Cursor':
        """Move forward to start of next word (Emacs forward-word)."""
        boundaries = _get_word_boundaries(self._text)
        for b in boundaries:
            if b.is_word_like and b.offset > self._offset:
                return self._with(offset=b.offset)
        return self._with(offset=len(self._text))

    def word_left(self) -> 'Cursor':
        """Move backward to start of previous word."""
        boundaries = _get_word_boundaries(self._text)
        result_offset = 0
        for b in boundaries:
            if b.is_word_like and b.offset < self._offset:
                result_offset = b.offset
        return self._with(offset=result_offset)

    def word_right_end(self) -> 'Cursor':
        """Move forward to end of current/next word."""
        boundaries = _get_word_boundaries(self._text)
        for i, b in enumerate(boundaries):
            if not b.is_word_like and b.offset > self._offset:
                # end of word is one before this boundary
                prev_b = boundaries[i - 1] if i > 0 else b
                return self._with(offset=b.offset)
        return self._with(offset=len(self._text))

    # -- insert / delete -----------------------------------------------------

    def insert(self, s: str) -> 'Cursor':
        """Insert text at current position."""
        new_text = self._text[:self._offset] + s + self._text[self._offset:]
        return self._with(text=new_text, offset=self._offset + len(s))

    def delete_left(self) -> 'Cursor':
        """Delete grapheme cluster to the left (backspace)."""
        if self._offset == 0:
            return self
        prev = self.measured_text.prev_offset(self._offset)
        new_text = self._text[:prev] + self._text[self._offset:]
        return self._with(text=new_text, offset=prev)

    def delete_right(self) -> 'Cursor':
        """Delete grapheme cluster to the right (delete key)."""
        if self._offset >= len(self._text):
            return self
        next_off = self.measured_text.next_offset(self._offset)
        new_text = self._text[:self._offset] + self._text[next_off:]
        return self._with(text=new_text, offset=self._offset)

    def delete_word_left(self) -> 'Cursor':
        """Delete from cursor to beginning of previous word (Emacs backward-kill-word)."""
        target = self.word_left()
        deleted = self._text[target.offset:self._offset]
        push_kill(deleted)
        new_text = self._text[:target.offset] + self._text[self._offset:]
        return self._with(text=new_text, offset=target.offset)

    def delete_word_right(self) -> 'Cursor':
        """Delete from cursor to end of current/next word."""
        target = self.word_right_end()
        deleted = self._text[self._offset:target.offset]
        push_kill(deleted)
        new_text = self._text[:self._offset] + self._text[target.offset:]
        return self._with(text=new_text, offset=self._offset)

    def kill_line(self) -> 'Cursor':
        """Kill from cursor to end of line (Emacs C-k)."""
        end = self.end_of_line()
        if end.offset == self._offset and self._offset < len(self._text):
            # at newline — kill the newline
            new_text = self._text[:self._offset] + self._text[self._offset + 1:]
            push_kill('\n')
            return self._with(text=new_text, offset=self._offset)
        killed = self._text[self._offset:end.offset]
        push_kill(killed)
        new_text = self._text[:self._offset] + self._text[end.offset:]
        return self._with(text=new_text, offset=self._offset)

    def kill_to_start_of_line(self) -> 'Cursor':
        """Kill from cursor to start of line (Emacs C-u)."""
        start = self.start_of_line()
        killed = self._text[start.offset:self._offset]
        push_kill(killed)
        new_text = self._text[:start.offset] + self._text[self._offset:]
        return self._with(text=new_text, offset=start.offset)

    def yank(self) -> 'Cursor':
        """Yank (paste) from kill ring at cursor position."""
        entry = peek_kill_ring()
        text_to_insert = entry['text']
        if not text_to_insert:
            return self
        set_last_yank(self._offset, len(text_to_insert))
        return self.insert(text_to_insert)

    def yank_pop(self) -> 'Cursor':
        """Replace last yank with next kill-ring entry."""
        rotate_kill_ring()
        # Remove previously yanked text
        new_text = self._text[:_last_yank_start] + self._text[_last_yank_start + _last_yank_length:]
        temp = Cursor(new_text, _last_yank_start, self._columns)
        return temp.yank()

    # -- set text / offset ---------------------------------------------------

    def set_text(self, text: str) -> 'Cursor':
        return self._with(text=text, offset=min(self._offset, len(text)))

    def set_offset(self, offset: int) -> 'Cursor':
        return self._with(offset=max(0, min(offset, len(self._text))))

    # -- predicates ----------------------------------------------------------

    def is_at_end(self) -> bool:
        return self._offset >= len(self._text)

    def is_at_start(self) -> bool:
        return self._offset == 0

    # -- render --------------------------------------------------------------

    def render(
        self,
        cursor_char: str,
        mask: str,
        invert: Callable[[str], str],
    ) -> str:
        """
        Render the text with the cursor character inserted/highlighted.

        Args:
            cursor_char: character shown as cursor (e.g. '█' or ' ')
            mask: if non-empty, replace all visible characters with this
            invert: function to invert/highlight the cursor character
        Returns:
            rendered string
        """
        text = self._text
        if mask:
            # Replace non-newline characters with mask
            text = re.sub(r'[^\n]', mask, text)

        before = text[:self._offset]
        at = text[self._offset:self._offset + 1] if self._offset < len(text) else ''
        after = text[self._offset + 1:] if self._offset < len(text) else ''

        if at:
            return before + invert(at) + after
        else:
            return before + invert(cursor_char)

    # -- find / search -------------------------------------------------------

    def find_next(self, pattern: str) -> Optional['Cursor']:
        """Find next occurrence of pattern after current position."""
        idx = self._text.find(pattern, self._offset + 1)
        if idx == -1:
            return None
        return self._with(offset=idx)

    def find_prev(self, pattern: str) -> Optional['Cursor']:
        """Find previous occurrence of pattern before current position."""
        idx = self._text.rfind(pattern, 0, self._offset)
        if idx == -1:
            return None
        return self._with(offset=idx)

    # -- misc ----------------------------------------------------------------

    def __repr__(self) -> str:
        return (f"Cursor(offset={self._offset}, "
                f"text={self._text[:20]!r}{'...' if len(self._text) > 20 else ''})")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Cursor):
            return NotImplemented
        return self._text == other._text and self._offset == other._offset

    def __hash__(self) -> int:
        return hash((self._text, self._offset))
