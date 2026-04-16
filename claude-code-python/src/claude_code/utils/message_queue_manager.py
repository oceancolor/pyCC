"""
message_queue_manager.py
多代理消息队列管理，支持优先级（now > next > later）和可选超时。
移植自 messageQueueManager.ts
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Priority
# ---------------------------------------------------------------------------

QueuePriority = str   # Literal['now', 'next', 'later']

_PRIORITY_ORDER: dict[QueuePriority, int] = {
    "now": 0,
    "next": 1,
    "later": 2,
}


def _priority_rank(p: Optional[QueuePriority]) -> int:
    return _PRIORITY_ORDER.get(p or "next", 1)


# ---------------------------------------------------------------------------
# Queued command dataclass
# ---------------------------------------------------------------------------

@dataclass
class QueuedCommand:
    value: str
    mode: str = "prompt"
    priority: QueuePriority = "next"
    pasted_contents: Optional[dict[int, Any]] = None
    skip_slash_commands: bool = False
    pre_expansion_value: Optional[str] = None
    uuid: Optional[str] = None
    is_meta: bool = False
    agent_id: Optional[str] = None
    workload: Optional[str] = None
    # Internal: enqueue timestamp (seconds) for FIFO within same priority
    _enqueued_at: float = field(default_factory=time.monotonic, compare=False, repr=False)


# ---------------------------------------------------------------------------
# MessageQueueManager
# ---------------------------------------------------------------------------

class MessageQueueManager:
    """
    Priority-aware FIFO command queue.

    Priority order: 'now' (0) > 'next' (1) > 'later' (2).
    Within the same priority, commands are processed FIFO by enqueue time.

    Async subscribers are notified on every mutation via asyncio.Event.
    """

    def __init__(self) -> None:
        self._queue: list[QueuedCommand] = []
        self._changed = asyncio.Event()    # pulsed on every mutation
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def enqueue(self, command: QueuedCommand) -> None:
        """Add a command with default priority 'next'."""
        if command.priority not in _PRIORITY_ORDER:
            command.priority = "next"
        command._enqueued_at = time.monotonic()
        self._queue.append(command)
        self._notify()

    def enqueue_pending_notification(self, command: QueuedCommand) -> None:
        """Convenience: enqueue with 'later' priority (never starves user input)."""
        command.priority = command.priority if command.priority in _PRIORITY_ORDER else "later"
        self.enqueue(command)

    def dequeue(
        self,
        filter_fn: Optional[Callable[[QueuedCommand], bool]] = None,
    ) -> Optional[QueuedCommand]:
        """
        Remove and return the highest-priority command.
        Within the same priority, FIFO order (earliest enqueue_at first).
        Optional filter_fn restricts candidates; non-matching items stay queued.
        """
        if not self._queue:
            return None
        best_idx = self._best_index(filter_fn)
        if best_idx == -1:
            return None
        cmd = self._queue.pop(best_idx)
        self._notify()
        return cmd

    def dequeue_all(self) -> list[QueuedCommand]:
        """Remove and return all commands (in priority-FIFO order)."""
        if not self._queue:
            return []
        cmds = sorted(self._queue, key=lambda c: (_priority_rank(c.priority), c._enqueued_at))
        self._queue.clear()
        self._notify()
        return cmds

    def dequeue_all_matching(
        self,
        predicate: Callable[[QueuedCommand], bool],
    ) -> list[QueuedCommand]:
        """Remove commands matching predicate; leave the rest."""
        matched = [c for c in self._queue if predicate(c)]
        if not matched:
            return []
        self._queue[:] = [c for c in self._queue if not predicate(c)]
        self._notify()
        return matched

    def remove(self, commands_to_remove: list[QueuedCommand]) -> None:
        """Remove specific commands by identity reference."""
        if not commands_to_remove:
            return
        remove_set = set(id(c) for c in commands_to_remove)
        before = len(self._queue)
        self._queue[:] = [c for c in self._queue if id(c) not in remove_set]
        if len(self._queue) != before:
            self._notify()

    def remove_by_filter(
        self,
        predicate: Callable[[QueuedCommand], bool],
    ) -> list[QueuedCommand]:
        """Remove commands matching predicate; return the removed list."""
        removed = [c for c in self._queue if predicate(c)]
        if not removed:
            return []
        self._queue[:] = [c for c in self._queue if not predicate(c)]
        self._notify()
        return removed

    def clear(self) -> None:
        """Remove all commands."""
        if not self._queue:
            return
        self._queue.clear()
        self._notify()

    def reset(self) -> None:
        """Clear queue and reset the change event (for test cleanup)."""
        self._queue.clear()
        self._changed.clear()

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def peek(
        self,
        filter_fn: Optional[Callable[[QueuedCommand], bool]] = None,
    ) -> Optional[QueuedCommand]:
        """Return the highest-priority command without removing it."""
        if not self._queue:
            return None
        idx = self._best_index(filter_fn)
        if idx == -1:
            return None
        return self._queue[idx]

    def size(self) -> int:
        """Return the current number of queued commands."""
        return len(self._queue)

    def has_commands(self) -> bool:
        return bool(self._queue)

    def snapshot(self) -> list[QueuedCommand]:
        """Return a shallow copy of the queue (no mutation)."""
        return list(self._queue)

    def get_by_max_priority(self, max_priority: QueuePriority) -> list[QueuedCommand]:
        """
        Return commands at or above max_priority without removing them.
        E.g. max_priority='now' → only 'now' commands.
              max_priority='later' → everything.
        """
        threshold = _priority_rank(max_priority)
        return [c for c in self._queue if _priority_rank(c.priority) <= threshold]

    # ------------------------------------------------------------------
    # Async subscription
    # ------------------------------------------------------------------

    async def wait_for_command(
        self,
        timeout: Optional[float] = None,
    ) -> bool:
        """
        Async-wait until a command arrives (or timeout elapses).

        Returns True if a command is available, False on timeout.
        Raises asyncio.TimeoutError if timeout is exceeded and you prefer
        exceptions — but here we return bool for ergonomics.
        """
        if self._queue:
            return True
        self._changed.clear()
        try:
            await asyncio.wait_for(self._changed.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _best_index(
        self,
        filter_fn: Optional[Callable[[QueuedCommand], bool]],
    ) -> int:
        """Find the index of the best (highest-priority, earliest) candidate."""
        best_idx = -1
        best_rank = (999, 0.0)
        for i, cmd in enumerate(self._queue):
            if filter_fn and not filter_fn(cmd):
                continue
            rank = (_priority_rank(cmd.priority), cmd._enqueued_at)
            if rank < best_rank:
                best_idx = i
                best_rank = rank
        return best_idx

    def _notify(self) -> None:
        """Pulse the change event so async waiters wake up."""
        self._changed.set()
        self._changed.clear()


# ---------------------------------------------------------------------------
# Module-level singleton (mirrors the TS module-level commandQueue array)
# ---------------------------------------------------------------------------

_default_manager: Optional[MessageQueueManager] = None


def get_default_manager() -> MessageQueueManager:
    global _default_manager
    if _default_manager is None:
        _default_manager = MessageQueueManager()
    return _default_manager


# Convenience module-level functions (mirrors TS named exports)

def enqueue(command: QueuedCommand) -> None:
    get_default_manager().enqueue(command)


def dequeue(
    filter_fn: Optional[Callable[[QueuedCommand], bool]] = None,
) -> Optional[QueuedCommand]:
    return get_default_manager().dequeue(filter_fn)


def peek(
    filter_fn: Optional[Callable[[QueuedCommand], bool]] = None,
) -> Optional[QueuedCommand]:
    return get_default_manager().peek(filter_fn)


def queue_size() -> int:
    return get_default_manager().size()


def clear_queue() -> None:
    get_default_manager().clear()


def reset_queue() -> None:
    get_default_manager().reset()


def is_slash_command(cmd: QueuedCommand) -> bool:
    """True if the command value starts with '/' and slash cmds are not skipped."""
    return (
        isinstance(cmd.value, str)
        and cmd.value.strip().startswith("/")
        and not cmd.skip_slash_commands
    )
