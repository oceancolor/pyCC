"""
Queue Processor

Processes commands from a queue with configurable batching behaviour.

Slash commands (starting with '/') and bash-mode commands are processed
one at a time so each goes through the execute_input path individually.
Other non-slash commands are batched: all items with the same mode as
the highest-priority item are drained at once and passed as a single list.

The caller is responsible for ensuring no query is currently running
and for calling process_queue_if_ready() again after each command
completes until the queue is empty.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, List, Optional, TypeVar

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Generic QueueProcessor (simple FIFO)
# ---------------------------------------------------------------------------


class QueueProcessor(Generic[T]):
    """A simple generic FIFO queue processor.

    Usage::

        q: QueueProcessor[int] = QueueProcessor()
        q.enqueue(1)
        q.enqueue(2)
        results = q.process_all(lambda item: item * 2)  # [2, 4]
    """

    def __init__(self) -> None:
        self._queue: deque[T] = deque()

    def enqueue(self, item: T) -> None:
        """Add *item* to the back of the queue."""
        self._queue.append(item)

    def dequeue(self) -> Optional[T]:
        """Remove and return the front item, or None if empty."""
        return self._queue.popleft() if self._queue else None

    def peek(self) -> Optional[T]:
        """Return the front item without removing it, or None if empty."""
        return self._queue[0] if self._queue else None

    def is_empty(self) -> bool:
        """Return True if the queue contains no items."""
        return len(self._queue) == 0

    def process_all(self, handler: Callable[[T], Any]) -> list:
        """Drain the queue and call *handler* for each item.

        Args:
            handler: Called with each item in FIFO order.

        Returns:
            List of return values from *handler*.
        """
        results = []
        while not self.is_empty():
            item = self.dequeue()
            if item is not None:
                results.append(handler(item))
        return results

    def __len__(self) -> int:
        return len(self._queue)


# ---------------------------------------------------------------------------
# Command-queue types  (mirrors TS QueuedCommand / processQueueIfReady)
# ---------------------------------------------------------------------------


@dataclass
class QueuedCommand:
    """A command waiting in the input queue."""

    # str for plain prompts; list[dict] for ContentBlockParam arrays
    value: Any
    mode: str = "prompt"
    # None → main-thread command; set → sub-agent command
    agent_id: Optional[str] = None


@dataclass
class ProcessQueueResult:
    processed: bool


def _is_slash_command(cmd: QueuedCommand) -> bool:
    """Return True if *cmd* is a slash command (value starts with '/')."""
    if isinstance(cmd.value, str):
        return cmd.value.strip().startswith("/")
    if isinstance(cmd.value, list):
        for block in cmd.value:
            if isinstance(block, dict) and block.get("type") == "text":
                return block.get("text", "").strip().startswith("/")
    return False


# Module-level command queue
_command_queue: deque[QueuedCommand] = deque()


def enqueue_command(cmd: QueuedCommand) -> None:
    """Add a command to the module-level queue."""
    _command_queue.append(cmd)


def has_queued_commands() -> bool:
    """Return True if there are pending commands in the module-level queue."""
    return len(_command_queue) > 0


def _peek_main_thread(queue: deque[QueuedCommand]) -> Optional[QueuedCommand]:
    for item in queue:
        if item.agent_id is None:
            return item
    return None


def _dequeue_main_thread(queue: deque[QueuedCommand]) -> Optional[QueuedCommand]:
    for i, item in enumerate(queue):
        if item.agent_id is None:
            del queue[i]  # type: ignore[misc]
            # deque doesn't support index deletion; rebuild
            lst = list(queue)
            queue.clear()
            queue.extend(lst[: i] + lst[i:])
            return item
    return None


def _dequeue_one_main_thread() -> Optional[QueuedCommand]:
    """Dequeue the first main-thread command."""
    for i, item in enumerate(list(_command_queue)):
        if item.agent_id is None:
            lst = list(_command_queue)
            _command_queue.clear()
            _command_queue.extend(lst[:i] + lst[i + 1 :])
            return item
    return None


def _dequeue_all_matching(
    predicate: Callable[[QueuedCommand], bool],
) -> List[QueuedCommand]:
    """Remove and return all commands matching *predicate* (preserving order)."""
    matched: List[QueuedCommand] = []
    remaining: List[QueuedCommand] = []
    for item in _command_queue:
        (matched if predicate(item) else remaining).append(item)
    _command_queue.clear()
    _command_queue.extend(remaining)
    return matched


def process_queue_if_ready(
    execute_input: Callable[[List[QueuedCommand]], None],
) -> ProcessQueueResult:
    """Process the next batch of commands from the module-level queue.

    Args:
        execute_input: Called with a list of QueuedCommand to execute.

    Returns:
        ProcessQueueResult indicating whether anything was processed.
    """
    next_cmd = _peek_main_thread(_command_queue)
    if next_cmd is None:
        return ProcessQueueResult(processed=False)

    # Slash and bash commands are processed individually
    if _is_slash_command(next_cmd) or next_cmd.mode == "bash":
        cmd = _dequeue_one_main_thread()
        if cmd:
            execute_input([cmd])
            return ProcessQueueResult(processed=True)
        return ProcessQueueResult(processed=False)

    # Batch all non-slash commands with the same mode
    target_mode = next_cmd.mode
    commands = _dequeue_all_matching(
        lambda c: c.agent_id is None
        and not _is_slash_command(c)
        and c.mode == target_mode
    )
    if not commands:
        return ProcessQueueResult(processed=False)

    execute_input(commands)
    return ProcessQueueResult(processed=True)
