"""
Workload context via contextvars (AsyncLocalStorage equivalent).
Ported from workloadContext.ts
"""
from __future__ import annotations
from contextvars import ContextVar
from typing import Callable, Optional, TypeVar

WORKLOAD_CRON = "cron"

_workload_var: ContextVar[Optional[str]] = ContextVar("workload", default=None)

T = TypeVar("T")


def get_workload() -> Optional[str]:
    return _workload_var.get()


def run_with_workload(workload: Optional[str], fn: Callable[[], T]) -> T:
    token = _workload_var.set(workload)
    try:
        return fn()
    finally:
        _workload_var.reset(token)
