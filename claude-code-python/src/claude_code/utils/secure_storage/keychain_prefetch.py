"""Keychain prefetch for startup optimization. Ported from utils/secureStorage/keychainPrefetch.ts"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from typing import Optional


async def prefetch_keychain_credentials() -> Optional[str]:
    """Asynchronously prefetch credentials from the macOS Keychain.

    Called during startup to warm the keychain cache before it is needed
    synchronously. Returns the raw JSON stdout, or None on failure.

    On non-macOS platforms this is a no-op and returns None.
    """
    if sys.platform != "darwin":
        return None

    from .mac_os_keychain_helpers import (
        CREDENTIALS_SERVICE_SUFFIX,
        get_mac_os_keychain_storage_service_name,
        get_username,
        prime_keychain_cache_from_prefetch,
    )

    service_name = get_mac_os_keychain_storage_service_name(CREDENTIALS_SERVICE_SUFFIX)
    username = get_username()

    try:
        proc = await asyncio.create_subprocess_exec(
            "security",
            "find-generic-password",
            "-a", username,
            "-w",
            "-s", service_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        raw: Optional[str] = stdout.decode().strip() if proc.returncode == 0 else None
    except Exception:
        raw = None

    prime_keychain_cache_from_prefetch(raw)
    return raw


def start_keychain_prefetch() -> "asyncio.Task[Optional[str]]":
    """Start the keychain prefetch as a background asyncio task.

    Returns the task so callers can optionally await it. On non-macOS platforms
    the task resolves immediately to None.
    """
    loop = asyncio.get_event_loop()
    return loop.create_task(prefetch_keychain_credentials())
