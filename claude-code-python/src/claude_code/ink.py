"""
Ink (React terminal UI) integration module.
Ported from ink.ts — React Ink is Node/JS-only; Python uses rich/click for terminal UI.

This module provides stub/adapter implementations for Ink's core API surface
so that Python code can import from it without errors. Actual terminal rendering
should use `rich`, `blessed`, or similar Python libraries.
"""
from __future__ import annotations
from typing import Any, Callable, Optional


# ---------------------------------------------------------------------------
# Core render functions (stubs)
# ---------------------------------------------------------------------------

async def render(component: Any, options: Optional[Any] = None) -> Any:
    """Stub: render a terminal UI component. Use rich/blessed for Python UI."""
    return None


async def create_root(options: Optional[Any] = None) -> Any:
    """Stub: create a root render context."""
    return _RootStub()


def static_render(component: Any) -> str:
    """Stub: statically render a component to string."""
    return ""


# ---------------------------------------------------------------------------
# Hook stubs (mirrors Ink's React hooks)
# ---------------------------------------------------------------------------

def use_input(handler: Callable, options: Optional[dict] = None) -> None:
    """Stub: register keyboard input handler."""
    pass


def use_app() -> dict:
    """Stub: return app context (exit fn)."""
    return {"exit": lambda code=0: None}


def use_stdin() -> dict:
    """Stub: return stdin context."""
    return {"stdin": None, "is_raw_mode_supported": False, "set_raw_mode": lambda _: None}


def use_animation_frame(callback: Callable) -> None:
    """Stub: animation frame hook."""
    pass


def use_interval(callback: Callable, delay: int) -> None:
    """Stub: interval hook."""
    pass


# ---------------------------------------------------------------------------
# UI component stubs (mimick the Ink component names)
# ---------------------------------------------------------------------------

class Box:
    """Stub for Ink's <Box> component."""
    def __init__(self, **props: Any) -> None:
        self.props = props


class Text:
    """Stub for Ink's <Text> component."""
    def __init__(self, children: Any = None, **props: Any) -> None:
        self.children = children
        self.props = props


class Newline:
    """Stub for Ink's <Newline> component."""
    pass


class Spacer:
    """Stub for Ink's <Spacer> component."""
    pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class _RootStub:
    """Stub root returned by create_root()."""

    def render(self, component: Any) -> None:
        pass

    def unmount(self) -> None:
        pass

    def clear(self) -> None:
        pass

    async def wait_until_exit(self) -> None:
        pass
