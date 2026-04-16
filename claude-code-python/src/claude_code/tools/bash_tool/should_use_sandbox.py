"""Sandbox usage determination. Ported from BashTool/shouldUseSandbox.ts"""
from __future__ import annotations
import os
from typing import Optional


def _is_sandboxing_enabled() -> bool:
    """Stub: check if sandboxing is available on this platform."""
    return False  # Sandbox not implemented


def should_use_sandbox(command: Optional[str] = None,
                       dangerously_disable_sandbox: bool = False) -> bool:
    if not _is_sandboxing_enabled():
        return False
    if dangerously_disable_sandbox:
        return False
    if not command:
        return False
    return True
