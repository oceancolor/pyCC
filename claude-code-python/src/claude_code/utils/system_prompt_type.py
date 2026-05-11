"""Branded system-prompt type. Ported from utils/systemPromptType.ts

Intentionally dependency-free so it can be imported from anywhere
without risking circular initialisation issues.
"""
from __future__ import annotations
from typing import List, Sequence, Tuple


# In TypeScript this is a branded ``readonly string[]``.  In Python we use a
# plain tuple (immutable, hashable) and a NewType-style wrapper so call-sites
# can annotate with ``SystemPrompt`` without any runtime overhead.

class SystemPrompt(tuple):
    """Immutable sequence of system-prompt strings.

    Behaves exactly like a ``tuple[str, ...]``.  The class wrapping provides
    the nominal typing that mirrors the TypeScript brand.
    """
    __slots__ = ()

    def __new__(cls, iterable: Sequence[str] = ()) -> "SystemPrompt":
        return super().__new__(cls, iterable)


def as_system_prompt(value: Sequence[str]) -> SystemPrompt:
    """Wrap *value* as a ``SystemPrompt``.

    Mirrors the TypeScript ``asSystemPrompt`` cast helper.
    """
    if isinstance(value, SystemPrompt):
        return value
    return SystemPrompt(value)
