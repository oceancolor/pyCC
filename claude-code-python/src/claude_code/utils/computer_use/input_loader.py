"""
input_loader.py - Loader for @ant/computer-use-input native module.

Port of TypeScript inputLoader.ts.
"""

import sys
from typing import Any, Optional

_cached: Optional[Any] = None


def require_computer_use_input() -> Any:
    """
    Load and return the computer use input API.

    On macOS, attempts to load the native input module.
    On other platforms, raises an error.

    Returns:
        ComputerUseInputAPI instance.

    Raises:
        RuntimeError: If not on macOS or module not available.
    """
    global _cached

    if _cached is not None:
        return _cached

    if sys.platform != 'darwin':
        raise RuntimeError('@ant/computer-use-input is macOS-only')

    # Try to load the native module
    try:
        import computer_use_input  # type: ignore
        if not getattr(computer_use_input, 'isSupported', False):
            raise RuntimeError('@ant/computer-use-input is not supported on this platform')
        _cached = computer_use_input
        return _cached
    except ImportError:
        raise RuntimeError('@ant/computer-use-input is not available (native module not installed)')
