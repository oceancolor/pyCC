# 原始 TS: keybindings/
"""键绑定系统"""
from .types import KeyBinding, KeyAction
from .registry import KeyBindingRegistry

__all__ = ["KeyBinding", "KeyAction", "KeyBindingRegistry"]
