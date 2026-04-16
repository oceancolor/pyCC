# 原始 TS: keybindings/registry.ts
"""键绑定注册表"""
from typing import Dict, List, Optional
from .types import KeyBinding, KeyAction


DEFAULT_BINDINGS: List[KeyBinding] = [
    KeyBinding("enter",      KeyAction.SUBMIT,       "提交输入"),
    KeyBinding("ctrl+j",     KeyAction.NEWLINE,      "插入换行"),
    KeyBinding("ctrl+c",     KeyAction.ABORT,        "中止当前操作"),
    KeyBinding("ctrl+l",     KeyAction.CLEAR,        "清除屏幕"),
    KeyBinding("up",         KeyAction.HISTORY_UP,   "上一条历史"),
    KeyBinding("down",       KeyAction.HISTORY_DOWN, "下一条历史"),
    KeyBinding("ctrl+k",     KeyAction.COMPACT,      "压缩对话"),
    KeyBinding("ctrl+v",     KeyAction.PASTE,        "粘贴"),
    KeyBinding("tab",        KeyAction.AUTOCOMPLETE, "自动补全"),
    KeyBinding("escape",     KeyAction.QUIT,         "退出"),
]


class KeyBindingRegistry:
    def __init__(self) -> None:
        self._bindings: Dict[str, KeyBinding] = {}
        for b in DEFAULT_BINDINGS:
            self._bindings[b.key] = b

    def register(self, binding: KeyBinding) -> None:
        self._bindings[binding.key] = binding

    def get(self, key: str) -> Optional[KeyBinding]:
        return self._bindings.get(key)

    def get_action(self, key: str) -> Optional[KeyAction]:
        b = self.get(key)
        return b.action if b else None

    def all_bindings(self) -> List[KeyBinding]:
        return list(self._bindings.values())

    def help_text(self) -> str:
        lines = [f"  {b.key:<15} {b.description}" for b in self.all_bindings() if b.description]
        return "\n".join(lines)
