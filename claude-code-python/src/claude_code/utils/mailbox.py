"""Mailbox — in-process message queue with async receive.

Ported from mailbox.ts.
"""

import asyncio
from typing import Any, Callable, Literal, Optional
from dataclasses import dataclass, field


MessageSource = Literal['user', 'teammate', 'system', 'tick', 'task']


@dataclass
class Message:
    id: str
    source: MessageSource
    content: str
    from_: Optional[str] = field(default=None, metadata={'alias': 'from'})
    color: Optional[str] = None
    timestamp: str = ''


def _default_filter(_: Message) -> bool:
    return True


class Mailbox:
    """Thread-safe in-process message queue with async receive."""

    def __init__(self) -> None:
        self._queue: list[Message] = []
        self._waiters: list[tuple[Callable[[Message], bool],
                                  asyncio.Future[Message]]] = []
        self._revision = 0
        self._subscribers: list[Callable[[], None]] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def length(self) -> int:
        return len(self._queue)

    @property
    def revision(self) -> int:
        return self._revision

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send(self, msg: Message) -> None:
        """Deliver *msg* to a waiting receiver or enqueue it."""
        self._revision += 1
        for i, (fn, fut) in enumerate(self._waiters):
            if fn(msg) and not fut.done():
                fut.set_result(msg)
                self._waiters.pop(i)
                self._notify()
                return
        self._queue.append(msg)
        self._notify()

    def poll(
        self,
        fn: Callable[[Message], bool] = _default_filter,
    ) -> Optional[Message]:
        """Return and remove the first matching message, or None."""
        for i, msg in enumerate(self._queue):
            if fn(msg):
                return self._queue.pop(i)
        return None

    async def receive(
        self,
        fn: Callable[[Message], bool] = _default_filter,
    ) -> Message:
        """Await the next message matching *fn*, removing it from the queue."""
        for i, msg in enumerate(self._queue):
            if fn(msg):
                self._queue.pop(i)
                self._notify()
                return msg

        loop = asyncio.get_event_loop()
        fut: asyncio.Future[Message] = loop.create_future()
        self._waiters.append((fn, fut))
        return await fut

    def subscribe(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Subscribe to change notifications; returns an unsubscribe callable."""
        self._subscribers.append(callback)

        def unsubscribe() -> None:
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass

        return unsubscribe

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _notify(self) -> None:
        for cb in list(self._subscribers):
            cb()
