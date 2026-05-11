"""Portable auth helpers. Ported from utils/authPortable.ts"""
from __future__ import annotations
import os
import subprocess


async def maybe_remove_api_key_from_macos_keychain_throws() -> None:
    """Remove the Claude Code API key from the macOS Keychain.

    Raises ``RuntimeError`` if the deletion fails (non-zero exit code from
    the ``security`` CLI).  No-op on non-macOS platforms.

    Ported from utils/authPortable.ts: maybeRemoveApiKeyFromMacOSKeychainThrows.
    """
    if os.sys.platform != "darwin":
        return

    service_name = _get_macos_keychain_service_name()
    cmd = f'security delete-generic-password -a $USER -s "{service_name}"'
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError("Failed to delete keychain entry")
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to delete keychain entry: {exc}") from exc


def normalize_api_key_for_config(api_key: str) -> str:
    """Return the last 20 characters of *api_key* for safe storage in config.

    Ported from utils/authPortable.ts: normalizeApiKeyForConfig.
    """
    return api_key[-20:]


def _get_macos_keychain_service_name() -> str:
    """Return the Keychain service name used by Claude Code."""
    try:
        from claude_code.utils.secure_storage.mac_os_keychain_helpers import (  # type: ignore[import]
            get_mac_os_keychain_storage_service_name,
        )
        return get_mac_os_keychain_storage_service_name()
    except ImportError:
        return "claude-code"
