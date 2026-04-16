"""
FileEditTool string-replacement utilities.
Ported from FileEditTool/utils.ts (775 lines → core).
"""
from __future__ import annotations

LEFT_SINGLE_CURLY_QUOTE = "\u2018"
RIGHT_SINGLE_CURLY_QUOTE = "\u2019"
LEFT_DOUBLE_CURLY_QUOTE = "\u201C"
RIGHT_DOUBLE_CURLY_QUOTE = "\u201D"


def normalize_quotes(s: str) -> str:
    """Convert curly quotes to straight quotes."""
    return (
        s.replace(LEFT_SINGLE_CURLY_QUOTE, "'")
         .replace(RIGHT_SINGLE_CURLY_QUOTE, "'")
         .replace(LEFT_DOUBLE_CURLY_QUOTE, '"')
         .replace(RIGHT_DOUBLE_CURLY_QUOTE, '"')
    )


def apply_edit(content: str, old_string: str, new_string: str,
               replace_all: bool = False) -> tuple[str, int]:
    """
    Apply old_string → new_string substitution.
    Returns (new_content, count_of_replacements).
    Raises ValueError if old_string not found or not unique (when replace_all=False).
    """
    # Normalize curly quotes
    old_norm = normalize_quotes(old_string)
    new_norm = normalize_quotes(new_string)
    content_norm = normalize_quotes(content)

    count = content_norm.count(old_norm)
    if count == 0:
        raise ValueError(
            f"String not found in file: {old_string[:80]!r}"
        )
    if not replace_all and count > 1:
        raise ValueError(
            f"old_string is not unique in the file ({count} occurrences). "
            "Use replace_all=true or provide more context to make it unique."
        )

    if replace_all:
        result = content_norm.replace(old_norm, new_norm)
        return result, count
    else:
        result = content_norm.replace(old_norm, new_norm, 1)
        return result, 1


def count_lines_changed(old: str, new: str) -> dict:
    old_lines = set(old.splitlines())
    new_lines = set(new.splitlines())
    added = len(new_lines - old_lines)
    removed = len(old_lines - new_lines)
    return {"added": added, "removed": removed}
