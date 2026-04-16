"""
Extended thinking configuration and utilities.
Ported from thinking.ts.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Union


# ---------------------------------------------------------------------------
# ThinkingConfig – mirrors the TS discriminated union
# ---------------------------------------------------------------------------

@dataclass
class ThinkingConfigAdaptive:
    type: Literal["adaptive"] = field(default="adaptive", init=False)


@dataclass
class ThinkingConfigEnabled:
    budget_tokens: int
    type: Literal["enabled"] = field(default="enabled", init=False)


@dataclass
class ThinkingConfigDisabled:
    type: Literal["disabled"] = field(default="disabled", init=False)


ThinkingConfig = Union[ThinkingConfigAdaptive, ThinkingConfigEnabled, ThinkingConfigDisabled]

# ---------------------------------------------------------------------------
# Ultrathink keyword helpers
# ---------------------------------------------------------------------------

_ULTRATHINK_RE = re.compile(r"\bultrathink\b", re.IGNORECASE)


def has_ultrathink_keyword(text: str) -> bool:
    """Return True if text contains the 'ultrathink' keyword."""
    return bool(_ULTRATHINK_RE.search(text))


def find_thinking_trigger_positions(text: str) -> list[dict[str, Any]]:
    """
    Find positions of 'ultrathink' keyword in text.

    Returns a list of dicts with keys: word, start, end.
    """
    positions: list[dict[str, Any]] = []
    for match in re.finditer(r"\bultrathink\b", text, re.IGNORECASE):
        positions.append(
            {
                "word": match.group(0),
                "start": match.start(),
                "end": match.end(),
            }
        )
    return positions


# ---------------------------------------------------------------------------
# Rainbow color helpers (UI theming)
# ---------------------------------------------------------------------------

RAINBOW_COLORS = [
    "rainbow_red",
    "rainbow_orange",
    "rainbow_yellow",
    "rainbow_green",
    "rainbow_blue",
    "rainbow_indigo",
    "rainbow_violet",
]

RAINBOW_SHIMMER_COLORS = [
    "rainbow_red_shimmer",
    "rainbow_orange_shimmer",
    "rainbow_yellow_shimmer",
    "rainbow_green_shimmer",
    "rainbow_blue_shimmer",
    "rainbow_indigo_shimmer",
    "rainbow_violet_shimmer",
]


def get_rainbow_color(char_index: int, shimmer: bool = False) -> str:
    """Return a rainbow theme color key for the given character index."""
    colors = RAINBOW_SHIMMER_COLORS if shimmer else RAINBOW_COLORS
    return colors[char_index % len(colors)]


# ---------------------------------------------------------------------------
# Thinking-block extraction (for content arrays from the API)
# ---------------------------------------------------------------------------

def parse_thinking_blocks(content: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Extract thinking blocks from an API content array.

    Each content block with type == 'thinking' is returned.
    """
    return [block for block in content if block.get("type") == "thinking"]


# ---------------------------------------------------------------------------
# Model capability stubs (full implementation needs provider/settings layer)
# ---------------------------------------------------------------------------

def model_supports_thinking(model: str) -> bool:
    """Return True if the model supports extended thinking. Simplified stub."""
    canonical = model.lower()
    # Exclude claude-3 family; all claude-4+ support thinking
    if "claude-3-" in canonical:
        return False
    return True


def model_supports_adaptive_thinking(model: str) -> bool:
    """Return True if the model supports adaptive thinking. Simplified stub."""
    canonical = model.lower()
    if "opus-4-6" in canonical or "sonnet-4-6" in canonical:
        return True
    if "opus" in canonical or "sonnet" in canonical or "haiku" in canonical:
        return False
    # Default True for unknown newer models
    return True


def should_enable_thinking_by_default() -> bool:
    """Return True if thinking should be enabled by default."""
    max_tokens_env = os.environ.get("MAX_THINKING_TOKENS")
    if max_tokens_env is not None:
        return int(max_tokens_env) > 0
    # Enable by default unless explicitly disabled
    return True
