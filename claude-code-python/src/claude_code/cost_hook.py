"""
Cost summary hook / atexit handler.
Ported from costHook.ts

The TypeScript version uses React's useEffect to register a process exit
handler.  Python uses atexit for the equivalent behaviour.
"""
from __future__ import annotations

import atexit
from typing import Any, Callable, Optional


def _register_cost_summary(get_fps_metrics: Optional[Callable[[], Any]] = None) -> None:
    """Register an atexit handler that prints cost summary and saves session costs."""

    def _on_exit() -> None:
        try:
            from claude_code.cost_tracker import format_total_cost, save_current_session_costs  # type: ignore
        except ImportError:
            return

        try:
            from claude_code.utils.billing import has_console_billing_access  # type: ignore

            if has_console_billing_access():
                import sys
                sys.stdout.write("\n" + format_total_cost() + "\n")
        except ImportError:
            pass

        fps_metrics = get_fps_metrics() if get_fps_metrics else None
        try:
            save_current_session_costs(fps_metrics)
        except Exception:
            pass

    atexit.register(_on_exit)


def use_cost_summary(get_fps_metrics: Optional[Callable[[], Any]] = None) -> None:
    """Python equivalent of useCostSummary().

    Call once at session startup to register the atexit cost-summary handler.
    Unlike the React hook, registration is idempotent in practice since the
    function is typically called once from the main entry point.
    """
    _register_cost_summary(get_fps_metrics)
