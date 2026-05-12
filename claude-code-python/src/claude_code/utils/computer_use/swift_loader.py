"""
swift_loader.py - Loader for @ant/computer-use-swift native module.

Port of TypeScript swiftLoader.ts.
"""

import sys
from typing import Any, Optional

_cached: Optional[Any] = None


def require_computer_use_swift() -> Any:
    """
    Load and return the computer use Swift API.

    Returns:
        ComputerUseAPI instance.

    Raises:
        RuntimeError: If not on macOS or module not available.
    """
    global _cached

    if sys.platform != 'darwin':
        raise RuntimeError('@ant/computer-use-swift is macOS-only')

    if _cached is not None:
        return _cached

    try:
        import computer_use_swift  # type: ignore
        _cached = computer_use_swift
        return _cached
    except ImportError:
        raise RuntimeError('@ant/computer-use-swift is not available (native module not installed)')
