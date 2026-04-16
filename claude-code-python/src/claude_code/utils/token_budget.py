"""Token budget parsing and management utilities.

Ported from tokenBudget.ts.
"""

import re
from typing import Optional

# Shorthand (+500k) anchored to start/end to avoid false positives.
SHORTHAND_START_RE = re.compile(r'^\s*\+(\d+(?:\.\d+)?)\s*(k|m|b)\b', re.IGNORECASE)
SHORTHAND_END_RE = re.compile(r'\s\+(\d+(?:\.\d+)?)\s*(k|m|b)\s*[.!?]?\s*$', re.IGNORECASE)
VERBOSE_RE = re.compile(r'\b(?:use|spend)\s+(\d+(?:\.\d+)?)\s*(k|m|b)\s*tokens?\b', re.IGNORECASE)

MULTIPLIERS: dict[str, int] = {
    'k': 1_000,
    'm': 1_000_000,
    'b': 1_000_000_000,
}


def _parse_budget_match(value: str, suffix: str) -> int:
    return int(float(value) * MULTIPLIERS[suffix.lower()])


def parse_token_budget(text: str) -> Optional[int]:
    """Parse a token budget from text like '+500k', '+2m', 'use 100k tokens'."""
    m = SHORTHAND_START_RE.match(text)
    if m:
        return _parse_budget_match(m.group(1), m.group(2))
    m = SHORTHAND_END_RE.search(text)
    if m:
        return _parse_budget_match(m.group(1), m.group(2))
    m = VERBOSE_RE.search(text)
    if m:
        return _parse_budget_match(m.group(1), m.group(2))
    return None


def find_token_budget_positions(text: str) -> list[dict[str, int]]:
    """Find start/end positions of token budget expressions in text."""
    positions: list[dict[str, int]] = []

    m = SHORTHAND_START_RE.match(text)
    if m:
        # Strip leading whitespace offset
        stripped = m.group(0).lstrip()
        offset = m.start() + (len(m.group(0)) - len(stripped))
        positions.append({'start': offset, 'end': m.end()})

    m = SHORTHAND_END_RE.search(text)
    if m:
        end_start = m.start() + 1  # +1: regex includes leading \s
        already_covered = any(
            p['start'] <= end_start < p['end'] for p in positions
        )
        if not already_covered:
            positions.append({'start': end_start, 'end': m.end()})

    for m in VERBOSE_RE.finditer(text):
        positions.append({'start': m.start(), 'end': m.end()})

    return positions


def get_budget_continuation_message(pct: int, turn_tokens: int, budget: int) -> str:
    """Return a message to continue working when a token budget percentage is hit."""
    def fmt(n: int) -> str:
        return f'{n:,}'

    return (
        f'Stopped at {pct}% of token target '
        f'({fmt(turn_tokens)} / {fmt(budget)}). '
        f'Keep working \u2014 do not summarize.'
    )
