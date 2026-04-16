# 原始 TS: utils/words.ts
"""Random word slug generator for plan IDs (adjective + noun combos)."""

from __future__ import annotations

import os
import secrets
from typing import List, Optional

# ---------------------------------------------------------------------------
# Word lists — whimsical adjectives and nouns (Claude-flavored)
# ---------------------------------------------------------------------------

_ADJECTIVES: List[str] = [
    "abundant", "ancient", "bright", "calm", "cheerful", "clever", "cozy",
    "curious", "dapper", "dazzling", "deep", "delightful", "eager", "elegant",
    "enchanted", "fancy", "fluffy", "gentle", "gleaming", "golden", "graceful",
    "happy", "hidden", "humble", "jolly", "joyful", "keen", "kind", "lively",
    "lovely", "lucky", "luminous", "magical", "majestic", "mellow", "merry",
    "mighty", "misty", "noble", "peaceful", "playful", "polished", "precious",
    "proud", "quiet", "quirky", "radiant", "rosy", "serene", "shiny", "silly",
    "sleepy", "smooth", "snazzy", "snug", "snuggly", "soft", "sparkling",
    "spicy", "splendid", "sprightly", "starry", "steady", "sunny", "swift",
    "tender", "tidy", "toasty", "tranquil", "twinkly", "vibrant", "vivid",
    "warm", "whimsical", "wild", "witty", "wonderful", "zesty", "zippy",
]

_NOUNS: List[str] = [
    "aurora", "beacon", "blossom", "breeze", "brook", "candle", "canyon",
    "cascade", "castle", "cedar", "cherry", "cloud", "comet", "coral",
    "crystal", "dawn", "delta", "dew", "dream", "dune", "ember", "falcon",
    "fern", "fjord", "flame", "forest", "fountain", "galaxy", "garden",
    "glacier", "grove", "harbor", "haven", "heath", "hill", "horizon",
    "island", "jasmine", "jungle", "lagoon", "lake", "lantern", "laurel",
    "leaf", "legend", "light", "lily", "lotus", "meadow", "mist", "moon",
    "moss", "mountain", "nebula", "ocean", "olive", "opal", "orchid",
    "pebble", "pine", "pixel", "pond", "prism", "rain", "rainbow", "reef",
    "river", "rose", "sage", "sand", "shimmer", "shore", "sky", "snow",
    "spark", "spring", "star", "stone", "stream", "summit", "sun", "sunset",
    "temple", "tide", "torch", "trail", "tree", "vale", "valley", "violet",
    "wave", "willow", "wind", "wood", "zenith",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_word_slug(separator: str = "-", num_words: int = 2) -> str:
    """Return a random adjective-noun slug like ``"golden-river"``.

    Args:
        separator: Character(s) between words (default ``"-"``).
        num_words: Total word count (1 = noun only, 2 = adj+noun, 3 = adj+adj+noun).
    """
    words: List[str] = []
    for _ in range(max(0, num_words - 1)):
        words.append(secrets.choice(_ADJECTIVES))
    words.append(secrets.choice(_NOUNS))
    return separator.join(words)


def generate_slug_with_number(separator: str = "-") -> str:
    """Return a slug like ``"golden-river-42"`` with a random 2-digit number."""
    base = generate_word_slug(separator=separator)
    number = secrets.randbelow(90) + 10  # 10..99
    return f"{base}{separator}{number}"
