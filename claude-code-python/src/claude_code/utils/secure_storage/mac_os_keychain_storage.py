"""macOS Keychain storage backend. Ported from utils/secureStorage/macOsKeychainStorage.ts"""

from __future__ import annotations

import asyncio
import json
import subprocess
import time
from typing import Optional, Dict, Any

SecureStorageData = Dict[str, Any]

_SECURITY_STDIN_LINE_LIMIT = 4096 - 64  # guard against `security -i` truncation


def _run_security_find(service_name: str, username: str) -> Optional[str]:
    """Synchronously find a generic password in the macOS Keychain."""
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", username, "-w", "-s", service_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


async def _run_security_find_async(service_name: str, username: str) -> Optional[str]:
    """Asynchronously find a generic password in the macOS Keychain."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "security", "find-generic-password", "-a", username, "-w", "-s", service_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0:
            return stdout.decode().strip() or None
    except Exception:
        pass
    return None


class _MacOsKeychainStorage:
    """Stores credentials in the macOS Keychain via the ``security`` CLI."""

    name = "keychain"

    def read(self) -> Optional[SecureStorageData]:
        from .mac_os_keychain_helpers import (
            CREDENTIALS_SERVICE_SUFFIX,
            KEYCHAIN_CACHE_TTL_MS,
            get_mac_os_keychain_storage_service_name,
            get_username,
            keychain_cache_state,
        )

        prev = keychain_cache_state.cache
        now_ms = int(time.time() * 1000)
        if now_ms - prev["cached_at"] < KEYCHAIN_CACHE_TTL_MS:
            return prev["data"]

        service_name = get_mac_os_keychain_storage_service_name(CREDENTIALS_SERVICE_SUFFIX)
        username = get_username()
        raw = _run_security_find(service_name, username)

        if raw:
            try:
                data = json.loads(raw)
                keychain_cache_state.cache = {"data": data, "cached_at": now_ms}
                return data
            except Exception:
                pass

        # Stale-while-error: keep serving the previous value if available
        if prev["data"] is not None:
            keychain_cache_state.cache = {"data": prev["data"], "cached_at": now_ms}
            return prev["data"]

        keychain_cache_state.cache = {"data": None, "cached_at": now_ms}
        return None

    async def read_async(self) -> Optional[SecureStorageData]:
        from .mac_os_keychain_helpers import (
            CREDENTIALS_SERVICE_SUFFIX,
            KEYCHAIN_CACHE_TTL_MS,
            get_mac_os_keychain_storage_service_name,
            get_username,
            keychain_cache_state,
        )

        prev = keychain_cache_state.cache
        now_ms = int(time.time() * 1000)
        if now_ms - prev["cached_at"] < KEYCHAIN_CACHE_TTL_MS:
            return prev["data"]

        # Deduplicate concurrent reads
        if keychain_cache_state.read_in_flight is not None:
            return await keychain_cache_state.read_in_flight  # type: ignore[misc]

        gen = keychain_cache_state.generation

        async def _do_read() -> Optional[SecureStorageData]:
            service_name = get_mac_os_keychain_storage_service_name(CREDENTIALS_SERVICE_SUFFIX)
            username = get_username()
            raw = await _run_security_find_async(service_name, username)
            if raw:
                try:
                    return json.loads(raw)
                except Exception:
                    pass
            return None

        async def _read_and_cache() -> Optional[SecureStorageData]:
            try:
                data = await _do_read()
                if gen == keychain_cache_state.generation:
                    keychain_cache_state.cache = {
                        "data": data,
                        "cached_at": int(time.time() * 1000),
                    }
                    keychain_cache_state.read_in_flight = None
                return data
            except Exception:
                keychain_cache_state.read_in_flight = None
                return None

        task = asyncio.ensure_future(_read_and_cache())
        keychain_cache_state.read_in_flight = task
        return await task

    def update(self, data: SecureStorageData) -> dict:
        from .mac_os_keychain_helpers import (
            CREDENTIALS_SERVICE_SUFFIX,
            clear_keychain_cache,
            get_mac_os_keychain_storage_service_name,
            get_username,
        )

        service_name = get_mac_os_keychain_storage_service_name(CREDENTIALS_SERVICE_SUFFIX)
        username = get_username()
        value = json.dumps(data)

        if len(value.encode()) > _SECURITY_STDIN_LINE_LIMIT:
            return {"success": False}

        try:
            # Try to update an existing entry first
            result = subprocess.run(
                [
                    "security", "add-generic-password",
                    "-a", username,
                    "-s", service_name,
                    "-w", value,
                    "-U",  # update if exists
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                clear_keychain_cache()
                return {"success": True}
        except Exception:
            pass

        return {"success": False}

    def delete(self) -> bool:
        from .mac_os_keychain_helpers import (
            CREDENTIALS_SERVICE_SUFFIX,
            clear_keychain_cache,
            get_mac_os_keychain_storage_service_name,
            get_username,
        )

        service_name = get_mac_os_keychain_storage_service_name(CREDENTIALS_SERVICE_SUFFIX)
        username = get_username()
        try:
            result = subprocess.run(
                [
                    "security", "delete-generic-password",
                    "-a", username,
                    "-s", service_name,
                ],
                capture_output=True,
                timeout=10,
            )
            clear_keychain_cache()
            return result.returncode == 0
        except Exception:
            return False


mac_os_keychain_storage = _MacOsKeychainStorage()
