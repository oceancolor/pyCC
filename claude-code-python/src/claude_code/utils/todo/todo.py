"""
Todo/task management utility.
Ported from utils/todo/ (no direct TS source, implemented based on context)

Provides a lightweight in-memory TODO list with persistence support.
Supports create, read, update, delete, and status transitions.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class TodoStatus(str, Enum):
    """Status of a todo item."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TodoPriority(str, Enum):
    """Priority level of a todo item."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class TodoItem:
    """A single todo/task item."""
    id: int
    text: str
    status: TodoStatus = TodoStatus.PENDING
    priority: TodoPriority = TodoPriority.MEDIUM
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    notes: str = ""

    def is_done(self) -> bool:
        """Return True if this item is in a terminal state."""
        return self.status in (TodoStatus.COMPLETED, TodoStatus.CANCELLED)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["priority"] = self.priority.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "TodoItem":
        return cls(
            id=data["id"],
            text=data["text"],
            status=TodoStatus(data.get("status", "pending")),
            priority=TodoPriority(data.get("priority", "medium")),
            tags=data.get("tags", []),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            completed_at=data.get("completed_at"),
            notes=data.get("notes", ""),
        )


class TodoList:
    """
    In-memory TODO list with optional JSON file persistence.

    Usage:
        todos = TodoList()
        item = todos.add("Write tests")
        todos.complete(item.id)
        todos.save("/path/to/todos.json")
    """

    def __init__(self, persist_path: Optional[str] = None) -> None:
        self._items: dict[int, TodoItem] = {}
        self._next_id: int = 1
        self._persist_path = persist_path
        if persist_path and Path(persist_path).exists():
            self.load(persist_path)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(
        self,
        text: str,
        priority: TodoPriority = TodoPriority.MEDIUM,
        tags: Optional[list[str]] = None,
        notes: str = "",
    ) -> TodoItem:
        """Create and return a new todo item."""
        item = TodoItem(
            id=self._next_id,
            text=text,
            priority=priority,
            tags=tags or [],
            notes=notes,
        )
        self._items[item.id] = item
        self._next_id += 1
        self._auto_save()
        return item

    def get(self, item_id: int) -> Optional[TodoItem]:
        """Return the item with the given id, or None."""
        return self._items.get(item_id)

    def update(
        self,
        item_id: int,
        text: Optional[str] = None,
        priority: Optional[TodoPriority] = None,
        tags: Optional[list[str]] = None,
        notes: Optional[str] = None,
    ) -> Optional[TodoItem]:
        """Update fields on an existing item. Returns updated item or None."""
        item = self._items.get(item_id)
        if item is None:
            return None
        if text is not None:
            item.text = text
        if priority is not None:
            item.priority = priority
        if tags is not None:
            item.tags = tags
        if notes is not None:
            item.notes = notes
        item.updated_at = time.time()
        self._auto_save()
        return item

    def delete(self, item_id: int) -> bool:
        """Remove an item. Returns True if it existed."""
        existed = item_id in self._items
        self._items.pop(item_id, None)
        self._auto_save()
        return existed

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------

    def start(self, item_id: int) -> Optional[TodoItem]:
        """Mark an item as in-progress."""
        return self._set_status(item_id, TodoStatus.IN_PROGRESS)

    def complete(self, item_id: int) -> Optional[TodoItem]:
        """Mark an item as completed."""
        item = self._set_status(item_id, TodoStatus.COMPLETED)
        if item:
            item.completed_at = time.time()
            self._auto_save()
        return item

    def cancel(self, item_id: int) -> Optional[TodoItem]:
        """Mark an item as cancelled."""
        return self._set_status(item_id, TodoStatus.CANCELLED)

    def reopen(self, item_id: int) -> Optional[TodoItem]:
        """Move a completed/cancelled item back to pending."""
        item = self._items.get(item_id)
        if item is None:
            return None
        item.status = TodoStatus.PENDING
        item.completed_at = None
        item.updated_at = time.time()
        self._auto_save()
        return item

    def _set_status(self, item_id: int, status: TodoStatus) -> Optional[TodoItem]:
        item = self._items.get(item_id)
        if item is None:
            return None
        item.status = status
        item.updated_at = time.time()
        self._auto_save()
        return item

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def all(self) -> list[TodoItem]:
        """Return all items sorted by id."""
        return sorted(self._items.values(), key=lambda i: i.id)

    def pending(self) -> list[TodoItem]:
        """Return items that are pending or in-progress."""
        return [i for i in self.all() if not i.is_done()]

    def completed(self) -> list[TodoItem]:
        """Return items in a terminal state."""
        return [i for i in self.all() if i.is_done()]

    def by_priority(self, priority: TodoPriority) -> list[TodoItem]:
        """Return items with the given priority."""
        return [i for i in self.all() if i.priority == priority]

    def by_tag(self, tag: str) -> list[TodoItem]:
        """Return items that have the given tag."""
        return [i for i in self.all() if tag in i.tags]

    def search(self, query: str) -> list[TodoItem]:
        """Return items whose text or notes contain the query (case-insensitive)."""
        q = query.lower()
        return [
            i for i in self.all()
            if q in i.text.lower() or q in i.notes.lower()
        ]

    def __len__(self) -> int:
        return len(self._items)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Optional[str] = None) -> None:
        """Serialize todos to JSON file."""
        target = path or self._persist_path
        if not target:
            return
        data = {
            "next_id": self._next_id,
            "items": [item.to_dict() for item in self.all()],
        }
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load(self, path: str) -> None:
        """Deserialize todos from a JSON file."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self._next_id = data.get("next_id", 1)
        self._items = {}
        for item_data in data.get("items", []):
            item = TodoItem.from_dict(item_data)
            self._items[item.id] = item

    def _auto_save(self) -> None:
        if self._persist_path:
            self.save()


# ---------------------------------------------------------------------------
# Module-level convenience API (mirrors the original stub interface)
# ---------------------------------------------------------------------------

_default_list: TodoList = TodoList()


def get_todos() -> list[dict]:
    """Return all todos as dicts."""
    return [item.to_dict() for item in _default_list.all()]


def add_todo(
    text: str,
    priority: str = "medium",
    tags: Optional[list[str]] = None,
) -> dict:
    """Add a todo to the default list. Returns the created item as a dict."""
    item = _default_list.add(
        text=text,
        priority=TodoPriority(priority),
        tags=tags,
    )
    return item.to_dict()


def complete_todo(index: int) -> bool:
    """
    Mark the todo at the given 0-based index as complete.
    Returns True if successful.

    Note: index is 0-based for backwards-compatibility with the original stub.
    """
    items = _default_list.all()
    if 0 <= index < len(items):
        _default_list.complete(items[index].id)
        return True
    return False


def delete_todo(index: int) -> bool:
    """Delete the todo at the given 0-based index. Returns True if successful."""
    items = _default_list.all()
    if 0 <= index < len(items):
        return _default_list.delete(items[index].id)
    return False


def pending_todos() -> list[dict]:
    """Return todos that are not yet done."""
    return [item.to_dict() for item in _default_list.pending()]
