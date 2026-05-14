"""Secure storage fallback. Ported from utils/secureStorage/fallbackStorage.ts"""

from __future__ import annotations

from typing import Optional, Dict, Any

SecureStorageData = Dict[str, Any]


def create_fallback_storage(primary: "SecureStorage", secondary: "SecureStorage") -> "SecureStorage":
    """Create a storage that tries primary first, falls back to secondary.

    Args:
        primary: The preferred storage backend.
        secondary: The fallback storage backend.

    Returns:
        A new :class:`SecureStorage` that delegates to primary, then secondary.
    """
    from .index import SecureStorage

    class _FallbackStorage:
        name = f"{primary.name}-with-{secondary.name}-fallback"

        def read(self) -> Optional[SecureStorageData]:
            result = primary.read()
            if result is not None:
                return result
            return secondary.read() or {}

        async def read_async(self) -> Optional[SecureStorageData]:
            result = await primary.read_async()
            if result is not None:
                return result
            return (await secondary.read_async()) or {}

        def update(self, data: SecureStorageData) -> dict:
            # Capture state before update for migration logic
            primary_data_before = primary.read()

            result = primary.update(data)
            if result.get("success"):
                # Delete secondary when migrating to primary for the first time.
                # Preserves credentials when sharing .claude between host and containers.
                if primary_data_before is None:
                    secondary.delete()
                return result

            fallback_result = secondary.update(data)
            if fallback_result.get("success"):
                # Primary write failed but may hold a stale entry — delete it to
                # prevent it from shadowing the fresh data in secondary (#30337).
                if primary_data_before is not None:
                    primary.delete()
                return {
                    "success": True,
                    "warning": fallback_result.get("warning"),
                }

            return {"success": False}

        def delete(self) -> bool:
            primary_ok = primary.delete()
            secondary_ok = secondary.delete()
            return primary_ok or secondary_ok

    return _FallbackStorage()  # type: ignore[return-value]
