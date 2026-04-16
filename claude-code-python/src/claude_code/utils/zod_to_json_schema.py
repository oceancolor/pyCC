"""
zod_to_json_schema.py

Python equivalent of zodToJsonSchema.ts.

Converts Pydantic v2 model classes (or marshmallow schemas) to JSON Schema
dict format.  Results are cached by object identity (WeakKeyDictionary) so
the conversion is done at most once per session per unique schema object.

Public API
----------
zod_to_json_schema(schema) -> dict
    Convert a Pydantic BaseModel *class* (or a pre-built dict) to a
    JSON Schema dict.  Also accepts objects that expose a
    ``model_json_schema()`` class-method (Pydantic v2) or a
    ``schema()`` class-method (Pydantic v1).

with_resolvers() -> WithResolvers
    Python port of withResolvers.ts — a Future together with its
    resolve/reject callbacks (analogous to Promise.withResolvers).
"""

from __future__ import annotations

import asyncio
import weakref
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, Optional, Type, TypeVar

# ---------------------------------------------------------------------------
# JSON Schema conversion
# ---------------------------------------------------------------------------

JsonSchema = Dict[str, Any]

# Cache by schema object identity (WeakKeyDictionary → no retention)
_schema_cache: weakref.WeakKeyDictionary[Any, JsonSchema] = weakref.WeakKeyDictionary()


def zod_to_json_schema(schema: Any) -> JsonSchema:
    """Convert *schema* to a JSON Schema dict.

    Supports:
      - dict (returned as-is)
      - Pydantic v2 BaseModel subclass (``model_json_schema()``)
      - Pydantic v1 BaseModel subclass (``schema()``)
      - Any object with a ``to_json_schema()`` method

    Results are cached by object identity.

    Args:
        schema: A schema descriptor.

    Returns:
        JSON Schema dict.

    Raises:
        TypeError: If the schema type is unsupported.
    """
    # Fast path: plain dict
    if isinstance(schema, dict):
        return schema

    # Cache lookup
    try:
        cached = _schema_cache.get(schema)
        if cached is not None:
            return cached
    except TypeError:
        # Unhashable / un-weakref-able — skip cache
        pass

    result = _convert(schema)

    try:
        _schema_cache[schema] = result
    except TypeError:
        pass

    return result


def _convert(schema: Any) -> JsonSchema:
    # Pydantic v2
    if hasattr(schema, "model_json_schema"):
        return schema.model_json_schema()  # type: ignore[no-any-return]

    # Pydantic v1
    if hasattr(schema, "schema") and callable(schema.schema):
        return schema.schema()  # type: ignore[no-any-return]

    # Generic fallback
    if hasattr(schema, "to_json_schema") and callable(schema.to_json_schema):
        return schema.to_json_schema()  # type: ignore[no-any-return]

    raise TypeError(
        f"Cannot convert {type(schema).__name__!r} to JSON Schema. "
        "Pass a Pydantic BaseModel class, a dict, or an object with "
        "model_json_schema() / schema() / to_json_schema()."
    )


# ---------------------------------------------------------------------------
# with_resolvers  (polyfill for Promise.withResolvers / ES2024)
# ---------------------------------------------------------------------------

T = TypeVar("T")


@dataclass
class WithResolvers(Generic[T]):
    """A Future together with its resolve and reject callbacks.

    Attributes:
        future: The underlying asyncio Future.
        resolve: Call to fulfill the future with a value.
        reject:  Call to cancel/fail the future with an exception.
    """

    future: asyncio.Future  # type: ignore[type-arg]
    resolve: Callable[[T], None]
    reject: Callable[[BaseException], None]


def with_resolvers(
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> WithResolvers[Any]:
    """Create an asyncio Future with explicit resolve/reject callbacks.

    Mirrors the ES2024 ``Promise.withResolvers()`` polyfill from
    ``withResolvers.ts``.

    Args:
        loop: Event loop to attach the future to.  Uses the running loop
              (or a new one) when not specified.

    Returns:
        WithResolvers containing the future and its callbacks.
    """
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()

    fut: asyncio.Future[Any] = loop.create_future()

    def resolve(value: Any) -> None:
        if not fut.done():
            fut.get_loop().call_soon_threadsafe(fut.set_result, value)

    def reject(exc: BaseException) -> None:
        if not fut.done():
            fut.get_loop().call_soon_threadsafe(fut.set_exception, exc)

    return WithResolvers(future=fut, resolve=resolve, reject=reject)
