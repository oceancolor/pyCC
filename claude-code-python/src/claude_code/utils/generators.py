"""
Python port of: src/utils/generators.ts
Async generator utilities: last_value, return_value, all_generators,
to_array, from_array.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, AsyncIterator, List, Optional, TypeVar

T = TypeVar("T")
R = TypeVar("R")


async def last_value(generator: AsyncIterator[T]) -> Optional[T]:
    """
    Consume an async generator and return its last yielded value.
    Returns None if the generator yields nothing.
    """
    last: Optional[T] = None
    async for item in generator:
        last = item
    return last


async def return_value(generator: AsyncGenerator[Any, None]) -> Any:
    """
    Consume an async generator until it is exhausted and return the
    value carried by StopAsyncIteration (i.e. the generator's return value).

    In TypeScript, generators can 'return' a value distinct from what they
    yield.  In Python, an async generator's return value is surfaced via the
    StopAsyncIteration exception's .value attribute when the generator uses
    'return <expr>' after the last yield.

    If the generator never returns a meaningful value (e.g. plain 'return')
    this function returns None.
    """
    gen = generator.__aiter__()
    while True:
        try:
            await gen.__anext__()
        except StopAsyncIteration as exc:
            return exc.value


async def all_generators(
    generators: List[AsyncIterator[T]],
    concurrency_cap: Optional[int] = None,
) -> AsyncGenerator[T, None]:
    """
    Run multiple async generators concurrently, yielding values as they
    arrive.  An optional concurrency_cap limits how many generators run
    simultaneously.

    Implementation note: we use asyncio.Queue to collect results from
    concurrent tasks and re-yield them in arrival order.
    """
    if not generators:
        return

    queue: asyncio.Queue = asyncio.Queue()
    sentinel = object()  # unique object marks "one generator finished"

    async def _drain(gen: AsyncIterator[T]) -> None:
        async for value in gen:
            await queue.put(value)
        await queue.put(sentinel)

    if concurrency_cap is None or concurrency_cap <= 0:
        # All generators run concurrently
        tasks = [asyncio.create_task(_drain(g)) for g in generators]
    else:
        # Semaphore-limited concurrency
        sem = asyncio.Semaphore(concurrency_cap)

        async def _drain_limited(gen: AsyncIterator[T]) -> None:
            async with sem:
                await _drain(gen)

        tasks = [asyncio.create_task(_drain_limited(g)) for g in generators]

    remaining = len(generators)
    while remaining > 0:
        item = await queue.get()
        if item is sentinel:
            remaining -= 1
        else:
            yield item  # type: ignore[misc]

    # Ensure all tasks are properly awaited (they should already be done)
    await asyncio.gather(*tasks, return_exceptions=True)


# Make all_generators an async generator function by using 'yield' — the
# function body already contains 'yield item', so Python treats it correctly.
# However, because the function has a conditional early 'return', we need to
# mark it explicitly. The implementation above is correct as-is.


async def to_array(generator: AsyncIterator[T]) -> List[T]:
    """Consume an async generator and collect all yielded values into a list."""
    return [item async for item in generator]


async def from_array(values: List[T]) -> AsyncGenerator[T, None]:
    """Create an async generator that yields all items from a list."""
    for item in values:
        yield item
