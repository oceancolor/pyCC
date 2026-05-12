"""
heredoc.py - Heredoc extraction and restoration utilities.

Port of TypeScript heredoc.ts.
"""

import re
import os
from typing import Dict, List, Optional, Tuple


HEREDOC_PLACEHOLDER_PREFIX = '__HEREDOC_'
HEREDOC_PLACEHOLDER_SUFFIX = '__'

HEREDOC_START_PATTERN = re.compile(
    r'(?<!<)<<(?!<)(-)?[ \t]*(?:([\'"])(\\?\w+)\2|\\?(\w+))'
)


class HeredocInfo:
    """Information about a single heredoc."""
    def __init__(
        self,
        full_text: str,
        delimiter: str,
        operator_start_index: int,
        operator_end_index: int,
        content_start_index: int,
        content_end_index: int,
    ):
        self.full_text = full_text
        self.delimiter = delimiter
        self.operator_start_index = operator_start_index
        self.operator_end_index = operator_end_index
        self.content_start_index = content_start_index
        self.content_end_index = content_end_index


class HeredocExtractionResult:
    """Result of heredoc extraction."""
    def __init__(self, processed_command: str, heredocs: Dict[str, HeredocInfo]):
        self.processed_command = processed_command
        self.heredocs = heredocs


def _generate_placeholder_salt() -> str:
    """Generates a random hex string for placeholder uniqueness."""
    return os.urandom(8).hex()


def extract_heredocs(
    command: str,
    quoted_only: bool = False,
) -> HeredocExtractionResult:
    """
    Extracts heredocs from a command string and replaces them with placeholders.
    """
    heredocs: Dict[str, HeredocInfo] = {}

    if '<<' not in command:
        return HeredocExtractionResult(command, heredocs)

    # Security pre-validation
    if re.search(r"\$['\"]", command):
        return HeredocExtractionResult(command, heredocs)

    first_heredoc_pos = command.index('<<')
    if first_heredoc_pos > 0 and '`' in command[:first_heredoc_pos]:
        return HeredocExtractionResult(command, heredocs)

    if first_heredoc_pos > 0:
        before = command[:first_heredoc_pos]
        open_arith = len(re.findall(r'\(\(', before))
        close_arith = len(re.findall(r'\)\)', before))
        if open_arith > close_arith:
            return HeredocExtractionResult(command, heredocs)

    heredoc_matches: List[HeredocInfo] = []
    skipped_heredoc_ranges: List[Tuple[int, int]] = []

    # Incremental scanner state
    scan_pos = 0
    scan_in_single_quote = False
    scan_in_double_quote = False
    scan_in_comment = False
    scan_dq_escape_next = False
    scan_pending_backslashes = 0

    def advance_scan(target: int) -> None:
        nonlocal scan_pos, scan_in_single_quote, scan_in_double_quote
        nonlocal scan_in_comment, scan_dq_escape_next, scan_pending_backslashes

        for i in range(scan_pos, target):
            if i >= len(command):
                break
            ch = command[i]

            if ch == '\n':
                scan_in_comment = False

            if scan_in_single_quote:
                if ch == "'":
                    scan_in_single_quote = False
                continue

            if scan_in_double_quote:
                if scan_dq_escape_next:
                    scan_dq_escape_next = False
                    continue
                if ch == '\\':
                    scan_dq_escape_next = True
                    continue
                if ch == '"':
                    scan_in_double_quote = False
                continue

            if ch == '\\':
                scan_pending_backslashes += 1
                continue

            escaped = scan_pending_backslashes % 2 == 1
            scan_pending_backslashes = 0
            if escaped:
                continue

            if ch == "'":
                scan_in_single_quote = True
            elif ch == '"':
                scan_in_double_quote = True
            elif not scan_in_comment and ch == '#':
                scan_in_comment = True

        scan_pos = target

    for match in HEREDOC_START_PATTERN.finditer(command):
        start_index = match.start()
        advance_scan(start_index)

        if scan_in_single_quote or scan_in_double_quote:
            continue

        if scan_in_comment:
            continue

        if scan_pending_backslashes % 2 == 1:
            continue

        # Check inside skipped heredoc ranges
        inside_skipped = False
        for (s_start, s_end) in skipped_heredoc_ranges:
            if s_start < start_index < s_end:
                inside_skipped = True
                break
        if inside_skipped:
            continue

        full_match = match.group(0)
        is_dash = match.group(1) == '-'
        delimiter = match.group(3) or match.group(4)
        if not delimiter:
            continue

        operator_end_index = start_index + len(full_match)
        quote_char = match.group(2)

        if quote_char and (operator_end_index == 0 or command[operator_end_index - 1] != quote_char):
            continue

        is_escaped_delimiter = '\\' in full_match
        is_quoted_or_escaped = bool(quote_char) or is_escaped_delimiter

        if operator_end_index < len(command):
            next_char = command[operator_end_index]
            if not re.match(r'^[ \t\n|&;()<>]$', next_char):
                continue

        # Find first unquoted newline after operator
        first_newline_offset = -1
        in_sq = False
        in_dq = False
        for k in range(operator_end_index, len(command)):
            ch = command[k]
            if in_sq:
                if ch == "'":
                    in_sq = False
                continue
            if in_dq:
                if ch == '\\':
                    k += 1
                    continue
                if ch == '"':
                    in_dq = False
                continue
            if ch == '\n':
                first_newline_offset = k - operator_end_index
                break
            backslash_count = 0
            j = k - 1
            while j >= operator_end_index and command[j] == '\\':
                backslash_count += 1
                j -= 1
            if backslash_count % 2 == 1:
                continue
            if ch == "'":
                in_sq = True
            elif ch == '"':
                in_dq = True

        if first_newline_offset == -1:
            continue

        same_line_content = command[operator_end_index:operator_end_index + first_newline_offset]
        trailing_backslashes = 0
        for j in range(len(same_line_content) - 1, -1, -1):
            if same_line_content[j] == '\\':
                trailing_backslashes += 1
            else:
                break
        if trailing_backslashes % 2 == 1:
            continue

        content_start_index = operator_end_index + first_newline_offset
        after_newline = command[content_start_index + 1:]
        content_lines = after_newline.split('\n')

        closing_line_index = -1
        for i, line in enumerate(content_lines):
            if is_dash:
                stripped = re.sub(r'^\t*', '', line)
                if stripped == delimiter:
                    closing_line_index = i
                    break
            else:
                if line == delimiter:
                    closing_line_index = i
                    break

            eof_check_line = re.sub(r'^\t*', '', line) if is_dash else line
            if (len(eof_check_line) > len(delimiter)
                    and eof_check_line.startswith(delimiter)):
                char_after = eof_check_line[len(delimiter)]
                if re.match(r'^[)}`|&;(<>]$', char_after):
                    closing_line_index = -1
                    break

        if quoted_only and not is_quoted_or_escaped:
            if closing_line_index == -1:
                skip_end = len(command)
            else:
                skip_lines = content_lines[:closing_line_index + 1]
                skip_content_length = len('\n'.join(skip_lines))
                skip_end = content_start_index + 1 + skip_content_length
            skipped_heredoc_ranges.append((content_start_index, skip_end))
            continue

        if closing_line_index == -1:
            continue

        lines_up_to_closing = content_lines[:closing_line_index + 1]
        content_length = len('\n'.join(lines_up_to_closing))
        content_end_index = content_start_index + 1 + content_length

        overlaps_skipped = False
        for (s_start, s_end) in skipped_heredoc_ranges:
            if content_start_index < s_end and s_start < content_end_index:
                overlaps_skipped = True
                break
        if overlaps_skipped:
            continue

        operator_text = command[start_index:operator_end_index]
        content_text = command[content_start_index:content_end_index]
        full_text = operator_text + content_text

        heredoc_matches.append(HeredocInfo(
            full_text=full_text,
            delimiter=delimiter,
            operator_start_index=start_index,
            operator_end_index=operator_end_index,
            content_start_index=content_start_index,
            content_end_index=content_end_index,
        ))

    if not heredoc_matches:
        return HeredocExtractionResult(command, heredocs)

    # Filter nested heredocs
    top_level_heredocs = [
        candidate for candidate in heredoc_matches
        if not any(
            other is not candidate
            and other.content_start_index < candidate.operator_start_index < other.content_end_index
            for other in heredoc_matches
        )
    ]

    if not top_level_heredocs:
        return HeredocExtractionResult(command, heredocs)

    # Check for duplicated content start positions
    content_start_positions = set(h.content_start_index for h in top_level_heredocs)
    if len(content_start_positions) < len(top_level_heredocs):
        return HeredocExtractionResult(command, heredocs)

    # Sort descending by content_end_index for safe replacement
    top_level_heredocs.sort(key=lambda h: h.content_end_index, reverse=True)

    salt = _generate_placeholder_salt()
    processed_command = command

    for index, info in enumerate(top_level_heredocs):
        placeholder_index = len(top_level_heredocs) - 1 - index
        placeholder = f"{HEREDOC_PLACEHOLDER_PREFIX}{placeholder_index}_{salt}{HEREDOC_PLACEHOLDER_SUFFIX}"

        heredocs[placeholder] = info

        processed_command = (
            processed_command[:info.operator_start_index]
            + placeholder
            + processed_command[info.operator_end_index:info.content_start_index]
            + processed_command[info.content_end_index:]
        )

    return HeredocExtractionResult(processed_command, heredocs)


def restore_heredocs(
    parts: List[str],
    heredocs: Dict[str, HeredocInfo],
) -> List[str]:
    """Restores heredoc placeholders in an array of strings."""
    if not heredocs:
        return parts

    result = []
    for part in parts:
        for placeholder, info in heredocs.items():
            part = part.replace(placeholder, info.full_text)
        result.append(part)
    return result


def contains_heredoc(command: str) -> bool:
    """Checks if a command contains heredoc syntax."""
    return bool(HEREDOC_START_PATTERN.search(command))
