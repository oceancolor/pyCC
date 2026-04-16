"""Todo/task management. Ported from utils/todo/."""
from __future__ import annotations
from typing import Any, List

_todos: List[dict] = []

def get_todos() -> List[dict]:
    return list(_todos)

def add_todo(item: str) -> None:
    _todos.append({"text": item, "done": False})

def complete_todo(index: int) -> None:
    if 0 <= index < len(_todos):
        _todos[index]["done"] = True
