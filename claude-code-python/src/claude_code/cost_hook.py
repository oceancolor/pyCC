"""Cost hook utilities. Ported from costHook.ts"""
from __future__ import annotations
import atexit
from typing import Callable, Optional


def use_cost_summary(get_fps_metrics: Optional[Callable] = None) -> None:
    """Register exit handler that prints cost summary."""
    def _on_exit():
        try:
            from claude_code.cost_tracker import format_total_cost, save_current_session_costs
            fps_metrics = get_fps_metrics() if get_fps_metrics else None
            print("\n" + format_total_cost())
            save_current_session_costs(fps_metrics)
        except Exception:
            pass
    atexit.register(_on_exit)
