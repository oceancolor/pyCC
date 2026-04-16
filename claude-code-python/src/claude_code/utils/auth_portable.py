"""Auth portable utilities. Ported from authPortable.ts"""
from __future__ import annotations
import asyncio, subprocess

async def maybe_remove_api_key_from_macos_keychain() -> None:
    import sys
    if sys.platform != 'darwin':
        return
    proc = await asyncio.create_subprocess_exec(
        'security', 'delete-generic-password', '-a', '$USER', '-s', 'claude-code',
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    await proc.wait()

def normalize_api_key_for_config(api_key: str) -> str:
    return api_key[-20:]
