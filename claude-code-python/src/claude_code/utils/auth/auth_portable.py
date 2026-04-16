# 原始 TS: utils/authPortable.ts
"""Portable auth helpers: macOS Keychain removal, API key normalization."""

from __future__ import annotations

import subprocess
import sys


async def maybe_remove_api_key_from_macos_keychain() -> None:
    """Remove the stored API key from the macOS Keychain (best-effort).

    No-op on non-Darwin platforms or if the entry doesn't exist.
    """
    if sys.platform != "darwin":
        return

    service_name = _get_macos_keychain_service_name()
    result = subprocess.run(
        [
            "security",
            "delete-generic-password",
            "-a", _get_current_user(),
            "-s", service_name,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Failed to delete keychain entry")


def normalize_api_key_for_config(api_key: str) -> str:
    """Return a normalized (partially redacted) API key suitable for config storage.

    Stores only the last 20 characters — enough to identify the key without
    exposing it in plaintext config files.
    """
    return api_key[-20:]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_macos_keychain_service_name() -> str:
    """Return the macOS Keychain service name used to store the API key."""
    # TODO: keep in sync with secureStorage/macOsKeychainHelpers.ts
    return "claude-code"


def _get_current_user() -> str:
    """Return the current OS username."""
    import getpass
    return getpass.getuser()
