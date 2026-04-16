"""Fullscreen/tmux utilities. Ported from utils/fullscreen.ts"""
from __future__ import annotations
import os
import subprocess
import sys
from typing import Optional

_tmux_control_mode: Optional[bool] = None


def is_tmux_control_mode() -> bool:
    global _tmux_control_mode
    if _tmux_control_mode is None:
        tmux = os.environ.get("TMUX")
        if not tmux:
            _tmux_control_mode = False
            return False
        try:
            result = subprocess.run(
                ["tmux", "display-message", "-p", "#{client_control_mode}"],
                capture_output=True, text=True, timeout=1)
            _tmux_control_mode = result.stdout.strip() == "1"
        except Exception:
            _tmux_control_mode = False
    return _tmux_control_mode


def is_fullscreen_supported() -> bool:
    """Check if fullscreen mode is available."""
    if sys.platform == "darwin":
        return True
    return bool(os.environ.get("TERM") and not is_tmux_control_mode())
