"""
Keybindings package.
Ported from: src/keybindings/ (TypeScript)

Provides the keyboard binding system for the Claude Code REPL:
  - KeyAction   — enum of bindable actions
  - KeyBinding  — a single key → action mapping
  - KeyBindingRegistry — loads and resolves keybindings
"""
from __future__ import annotations

from .types import (
    KeyAction,
    KeyBinding,
)
from .registry import (
    KeyBindingRegistry,
    DEFAULT_BINDINGS,
)

__all__ = [
    "KeyAction",
    "KeyBinding",
    "KeyBindingRegistry",
    "DEFAULT_BINDINGS",
]
