"""Secure storage utilities sub-package. Ported from utils/secureStorage/.

Provides platform-appropriate secure credential storage (macOS Keychain,
plain-text fallback) for API keys and other sensitive values.
"""
from __future__ import annotations

from claude_code.utils.secure_storage.index import (
    SecureStorage,
    get_secure_storage,
)
from claude_code.utils.secure_storage.fallback_storage import (
    create_fallback_storage,
)

__all__ = [
    "SecureStorage",
    "get_secure_storage",
    "create_fallback_storage",
]
