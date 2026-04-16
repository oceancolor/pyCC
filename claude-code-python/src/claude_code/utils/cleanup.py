# 原始 TS: utils/cleanup.ts / utils/cleanupRegistry.ts
"""进程退出时的清理注册表"""
import atexit
import signal
from typing import Callable, List


_handlers: List[Callable[[], None]] = []
_registered = False


def _run_handlers() -> None:
    for h in reversed(_handlers):
        try:
            h()
        except Exception:
            pass


def _setup_signals() -> None:
    global _registered
    if _registered:
        return
    _registered = True
    atexit.register(_run_handlers)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, lambda s, f: (_run_handlers(), exit(0)))
        except (OSError, ValueError):
            pass


def register_cleanup(fn: Callable[[], None]) -> None:
    """注册退出清理函数"""
    _setup_signals()
    _handlers.append(fn)


def unregister_cleanup(fn: Callable[[], None]) -> None:
    try:
        _handlers.remove(fn)
    except ValueError:
        pass
