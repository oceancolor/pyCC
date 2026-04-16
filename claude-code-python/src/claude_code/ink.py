"""
Ink (React terminal UI) integration stub.
Ported from ink.ts (85 lines) — React Ink is Node/JS-only, Python renders via rich/click.
"""
from __future__ import annotations
from typing import Any, Callable, Optional


def render(component: Any, options: Optional[dict] = None) -> Any:
    """Stub: render a terminal UI component. Use rich/blessed for Python UI."""
    return None


def static_render(component: Any) -> str:
    """Stub: statically render a component to string."""
    return ""


def use_input(handler: Callable, options: Optional[dict] = None) -> None:
    """Stub: register keyboard input handler."""
    pass


def use_app() -> dict:
    """Stub: return app context."""
    return {"exit": lambda code=0: None}
