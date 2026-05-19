"""Sandbox utilities.

Provides the sandbox adapter and configuration helpers used to run code
in isolated environments (Docker, macOS sandbox-exec, etc.) when the
user enables sandbox mode.

Ported from: src/utils/sandbox/ (TypeScript)

Usage::

    from claude_code.utils.sandbox import SandboxConfig, SandboxManager, SandboxResult
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
