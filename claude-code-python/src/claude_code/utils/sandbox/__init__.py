"""Sandbox utilities sub-package. Ported from utils/sandbox/.

Provides sandbox adapter and configuration helpers for running code in
isolated environments.
"""
from __future__ import annotations

from claude_code.utils.sandbox.sandbox_adapter import (
    SandboxConfig,
    SandboxManager,
    SandboxResult,
)

__all__ = [
    "SandboxConfig",
    "SandboxResult",
    "SandboxManager",
]
