"""Git bundle creation and upload for CCR seed-bundle seeding. Ported from utils/teleport/gitBundle.ts"""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


async def create_git_bundle(
    cwd: str,
    ref: str = "HEAD",
    output_path: Optional[str] = None,
) -> str:
    """Create a git bundle for the given repository.

    Args:
        cwd: The repository root directory.
        ref: The git ref to include in the bundle (default: HEAD).
        output_path: Where to write the bundle. If None a temp file is created.

    Returns:
        The path to the created bundle file.

    Raises:
        RuntimeError: If git is not available or bundle creation fails.
    """
    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".bundle")
        os.close(fd)

    proc = await asyncio.create_subprocess_exec(
        "git", "-C", cwd, "bundle", "create", output_path, ref,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        msg = stderr.decode().strip() if stderr else "unknown error"
        raise RuntimeError(f"git bundle failed: {msg}")

    return output_path


async def upload_git_bundle(
    bundle_path: str,
    upload_url: str,
    auth_token: str,
    timeout: float = 120.0,
) -> dict:
    """Upload a git bundle to the Teleport seed-bundle endpoint.

    Args:
        bundle_path: Local path to the ``.bundle`` file.
        upload_url: Pre-signed URL or API endpoint.
        auth_token: Bearer token for authentication.
        timeout: Upload timeout in seconds.

    Returns:
        Parsed JSON response dict from the server.

    Raises:
        RuntimeError: If aiohttp is unavailable or the upload fails.
    """
    try:
        import aiohttp  # type: ignore[import]
    except ImportError:
        raise RuntimeError("aiohttp is required for bundle uploads")

    bundle_bytes = Path(bundle_path).read_bytes()

    async with aiohttp.ClientSession() as session:
        async with session.put(
            upload_url,
            data=bundle_bytes,
            headers={
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/octet-stream",
            },
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            resp.raise_for_status()
            try:
                return await resp.json()
            except Exception:
                return {"status": resp.status}


async def create_and_upload_git_bundle(
    cwd: str,
    upload_url: str,
    auth_token: str,
    ref: str = "HEAD",
    timeout: float = 120.0,
) -> dict:
    """Convenience wrapper: create a git bundle and upload it in one call.

    Cleans up the temp bundle file after the upload (success or failure).

    Args:
        cwd: The repository root directory.
        upload_url: Pre-signed upload URL.
        auth_token: Bearer token for authentication.
        ref: The git ref to bundle (default: HEAD).
        timeout: Upload timeout in seconds.

    Returns:
        Parsed server response dict.
    """
    bundle_path = await create_git_bundle(cwd, ref=ref)
    try:
        return await upload_git_bundle(bundle_path, upload_url, auth_token, timeout)
    finally:
        try:
            os.unlink(bundle_path)
        except Exception:
            pass


def verify_git_bundle(bundle_path: str) -> bool:
    """Verify the integrity of a git bundle file.

    Returns True if ``git bundle verify`` succeeds, False otherwise.
    """
    try:
        result = subprocess.run(
            ["git", "bundle", "verify", bundle_path],
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False
