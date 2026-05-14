"""Secure storage abstraction and factory. Ported from utils/secureStorage/index.ts"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

SecureStorageData = Dict[str, Any]


class SecureStorage(ABC):
    """Abstract base class for secure credential storage backends."""

    name: str = "unknown"

    @abstractmethod
    def read(self) -> Optional[SecureStorageData]:
        """Read credentials synchronously. Returns None if not found."""

    @abstractmethod
    async def read_async(self) -> Optional[SecureStorageData]:
        """Read credentials asynchronously. Returns None if not found."""

    @abstractmethod
    def update(self, data: SecureStorageData) -> dict:
        """Write credentials. Returns ``{"success": bool, "warning": str|None}``."""

    @abstractmethod
    def delete(self) -> bool:
        """Delete credentials. Returns True on success (including ENOENT)."""


def get_secure_storage() -> SecureStorage:
    """Return the appropriate secure storage implementation for the current platform.

    - macOS: Keychain → plaintext fallback
    - Other: plaintext
    """
    from .fallback_storage import create_fallback_storage

    if sys.platform == "darwin":
        from .mac_os_keychain_storage import mac_os_keychain_storage
        from .plain_text_storage import plain_text_storage
        return create_fallback_storage(mac_os_keychain_storage, plain_text_storage)  # type: ignore[arg-type]

    # TODO: add libsecret support for Linux
    from .plain_text_storage import plain_text_storage
    return plain_text_storage  # type: ignore[return-value]
