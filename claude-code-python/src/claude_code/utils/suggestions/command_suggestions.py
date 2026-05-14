"""Command suggestions with fuzzy search. Ported from utils/suggestions/commandSuggestions.ts"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple

# Word-separator characters for command search
_SEPARATORS = re.compile(r'[:_\-]')


@dataclass
class SuggestionItem:
    """A single autocomplete suggestion."""

    value: str
    label: str
    description: Optional[str] = None
    score: float = 0.0


def _clean_word(word: str) -> str:
    """Strip leading/trailing punctuation from a word for indexing."""
    return re.sub(r'[^\w]', '', word)


def _split_words(text: str) -> List[str]:
    """Split text into searchable words."""
    return [w for w in text.split() if _clean_word(w)]


def _score_match(query: str, target: str, weight: float = 1.0) -> float:
    """Simple scoring: exact prefix match scores highest, substring match scores lower."""
    q = query.lower()
    t = target.lower()
    if t == q:
        return weight * 1.0
    if t.startswith(q):
        return weight * 0.8
    if q in t:
        return weight * 0.5
    return 0.0


def search_commands(
    query: str,
    commands: List[Dict[str, Any]],
    max_results: int = 10,
) -> List[SuggestionItem]:
    """Fuzzy-search a list of command dicts and return matching suggestions.

    Each command dict is expected to have at least:
    - ``name`` (str): the command name
    - ``description`` (str, optional): human-readable description
    - ``aliases`` (list, optional): alternative names
    - ``is_hidden`` (bool, optional): skip if True

    Args:
        query: The user's partial input (without the leading ``/``).
        commands: List of command descriptors.
        max_results: Maximum number of results to return.

    Returns:
        Scored and sorted list of :class:`SuggestionItem`.
    """
    if not query:
        return []

    results: List[Tuple[float, SuggestionItem]] = []

    for cmd in commands:
        if cmd.get("is_hidden"):
            continue

        name: str = cmd.get("name", "")
        description: str = cmd.get("description", "")
        aliases: List[str] = cmd.get("aliases", []) or []

        parts = [p for p in _SEPARATORS.split(name) if p]
        score = 0.0

        # Name gets the highest weight
        score = max(score, _score_match(query, name, weight=3.0))
        # Parts of the name
        for part in parts:
            score = max(score, _score_match(query, part, weight=2.0))
        # Aliases
        for alias in aliases:
            score = max(score, _score_match(query, alias, weight=2.0))
        # Description words (lower weight)
        for word in _split_words(description):
            score = max(score, _score_match(query, _clean_word(word), weight=0.5))

        if score > 0:
            results.append(
                (
                    score,
                    SuggestionItem(
                        value=name,
                        label=name,
                        description=description or None,
                        score=score,
                    ),
                )
            )

    results.sort(key=lambda t: -t[0])
    return [item for _, item in results[:max_results]]
