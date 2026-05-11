"""
Download functionality for native installer.

Handles downloading Claude binaries from various sources:
- NPM packages
- GCS bucket
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
import stat
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

GCS_BUCKET_URL = (
    "https://storage.googleapis.com/"
    "claude-code-dist-86c565f3-f756-42ad-8dfa-d59b1c096819/claude-code-releases"
)
ARTIFACTORY_REGISTRY_URL = (
    "https://artifactory.infra.ant.dev/artifactory/api/npm/npm-all/"
)

# Stall timeout: abort if no bytes received for this duration
DEFAULT_STALL_TIMEOUT_MS = 60000  # 60 seconds
MAX_DOWNLOAD_RETRIES = 3
STALL_TIMEOUT_MS = DEFAULT_STALL_TIMEOUT_MS


def _get_stall_timeout_ms() -> int:
    return int(
        os.environ.get("CLAUDE_CODE_STALL_TIMEOUT_MS_FOR_TESTING", DEFAULT_STALL_TIMEOUT_MS)
    )


class StallTimeoutError(Exception):
    def __init__(self) -> None:
        super().__init__("Download stalled: no data received for 60 seconds")
        self.name = "StallTimeoutError"


async def _run_subprocess(*args: str, timeout: float = 30.0, cwd: Optional[str] = None) -> tuple[int, str, str]:
    """Run a subprocess and return (returncode, stdout, stderr)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return (
            proc.returncode or 0,
            stdout_bytes.decode("utf-8", errors="replace"),
            stderr_bytes.decode("utf-8", errors="replace"),
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return (-1, "", "timeout")


async def get_latest_version_from_artifactory(tag: str = "latest") -> str:
    """Get the latest version from Artifactory NPM registry."""
    import sys
    native_package_url = os.environ.get("NATIVE_PACKAGE_URL", "@anthropic-ai/claude-code")

    start_time = time.time()
    code, stdout, stderr = await _run_subprocess(
        "npm", "view", f"{native_package_url}@{tag}", "version",
        "--prefer-online", "--registry", ARTIFACTORY_REGISTRY_URL,
        timeout=30.0,
    )
    latency_ms = (time.time() - start_time) * 1000

    if code != 0:
        error = Exception(f"npm view failed with code {code}: {stderr}")
        logger.error("npm view failed: %s", stderr)
        raise error

    logger.debug("npm view %s@%s version: %s", native_package_url, tag, stdout)
    return stdout.strip()


async def get_latest_version_from_binary_repo(
    channel: str = "latest",
    base_url: str = GCS_BUCKET_URL,
    auth: Optional[dict] = None,
) -> str:
    """Get the latest version from a binary repository."""
    try:
        import aiohttp
    except ImportError:
        # Fall back to urllib
        import urllib.request
        import urllib.error

        url = f"{base_url}/{channel}"
        start_time = time.time()
        try:
            req = urllib.request.Request(url)
            if auth and "headers" in auth:
                for k, v in auth["headers"].items():
                    req.add_header(k, v)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8").strip()
        except Exception as e:
            raise Exception(f"Failed to fetch version from {url}: {e}") from e

    url = f"{base_url}/{channel}"
    start_time = time.time()
    try:
        async with aiohttp.ClientSession() as session:
            headers = {}
            if auth and "headers" in auth:
                headers.update(auth["headers"])
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30), headers=headers) as resp:
                resp.raise_for_status()
                text = await resp.text()
                return text.strip()
    except Exception as e:
        raise Exception(f"Failed to fetch version from {url}: {e}") from e


async def get_latest_version(channel_or_version: str) -> str:
    """
    Get the latest version for a given channel or direct version string.
    """
    import re

    # Direct version
    if re.match(r"^v?\d+\.\d+\.\d+(-\S+)?$", channel_or_version):
        normalized = channel_or_version.lstrip("v")
        # 99.99.x is reserved for CI smoke-test fixtures
        if re.match(r"^99\.99\.", normalized):
            raise Exception(
                f"Version {normalized} is not available for installation. "
                "Use 'stable' or 'latest'."
            )
        return normalized

    # ReleaseChannel validation
    channel = channel_or_version
    if channel not in ("stable", "latest"):
        raise Exception(
            f"Invalid channel: {channel_or_version}. Use 'stable' or 'latest'"
        )

    if os.environ.get("USER_TYPE") == "ant":
        npm_tag = "stable" if channel == "stable" else "latest"
        return await get_latest_version_from_artifactory(npm_tag)

    return await get_latest_version_from_binary_repo(channel, GCS_BUCKET_URL)


async def _download_and_verify_binary(
    binary_url: str,
    expected_checksum: str,
    binary_path: str,
    request_config: Optional[dict] = None,
) -> None:
    """
    Common logic for downloading and verifying a binary.
    Includes stall detection and retry logic.
    """
    request_config = request_config or {}
    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_DOWNLOAD_RETRIES + 1):
        try:
            await _download_with_stall_detection(
                binary_url,
                expected_checksum,
                binary_path,
                request_config,
            )
            return  # Success
        except StallTimeoutError as e:
            last_error = e
            if attempt < MAX_DOWNLOAD_RETRIES:
                logger.debug(
                    "Download stalled on attempt %d/%d, retrying...",
                    attempt,
                    MAX_DOWNLOAD_RETRIES,
                )
                await asyncio.sleep(1.0)
                continue
            raise last_error
        except Exception as e:
            # Don't retry non-stall errors
            raise


async def _download_with_stall_detection(
    url: str,
    expected_checksum: str,
    dest_path: str,
    request_config: dict,
) -> None:
    """Download a binary with stall detection and checksum verification."""
    stall_timeout_s = _get_stall_timeout_ms() / 1000.0
    total_timeout_s = 5 * 60.0  # 5 minutes

    headers = {}
    if "headers" in request_config:
        headers.update(request_config["headers"])
    if "auth" in request_config:
        import base64
        u = request_config["auth"].get("username", "")
        p = request_config["auth"].get("password", "")
        token = base64.b64encode(f"{u}:{p}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"

    try:
        import aiohttp
        _USE_AIOHTTP = True
    except ImportError:
        _USE_AIOHTTP = False

    if _USE_AIOHTTP:
        await _download_aiohttp(url, expected_checksum, dest_path, headers, stall_timeout_s, total_timeout_s)
    else:
        await _download_urllib(url, expected_checksum, dest_path, headers, total_timeout_s)


async def _download_aiohttp(
    url: str,
    expected_checksum: str,
    dest_path: str,
    headers: dict,
    stall_timeout_s: float,
    total_timeout_s: float,
) -> None:
    """Download using aiohttp with stall detection."""
    import aiohttp

    sha256 = hashlib.sha256()
    data_chunks: list[bytes] = []

    async with aiohttp.ClientSession() as session:
        async with session.get(
            url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=total_timeout_s),
        ) as resp:
            resp.raise_for_status()

            last_data_time = time.time()
            async for chunk in resp.content.iter_chunked(65536):
                if not chunk:
                    continue
                elapsed = time.time() - last_data_time
                if elapsed > stall_timeout_s:
                    raise StallTimeoutError()
                last_data_time = time.time()
                sha256.update(chunk)
                data_chunks.append(chunk)

    # Verify checksum
    actual_checksum = sha256.hexdigest()
    if actual_checksum != expected_checksum:
        raise Exception(
            f"Checksum mismatch: expected {expected_checksum}, got {actual_checksum}"
        )

    # Write binary to disk
    with open(dest_path, "wb") as f:
        for chunk in data_chunks:
            f.write(chunk)

    # Make executable
    current_mode = os.stat(dest_path).st_mode
    os.chmod(dest_path, current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


async def _download_urllib(
    url: str,
    expected_checksum: str,
    dest_path: str,
    headers: dict,
    total_timeout_s: float,
) -> None:
    """Download using urllib as fallback."""
    import urllib.request

    def _do_download() -> bytes:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=total_timeout_s) as resp:
            return resp.read()

    loop = asyncio.get_event_loop()
    data = await asyncio.wait_for(
        loop.run_in_executor(None, _do_download),
        timeout=total_timeout_s + 10,
    )

    # Verify checksum
    actual_checksum = hashlib.sha256(data).hexdigest()
    if actual_checksum != expected_checksum:
        raise Exception(
            f"Checksum mismatch: expected {expected_checksum}, got {actual_checksum}"
        )

    with open(dest_path, "wb") as f:
        f.write(data)

    current_mode = os.stat(dest_path).st_mode
    os.chmod(dest_path, current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


async def download_version_from_artifactory(version: str, staging_path: str) -> None:
    """Download a version from Artifactory NPM registry."""
    from .installer import get_platform

    # Remove any partial download
    if os.path.exists(staging_path):
        shutil.rmtree(staging_path, ignore_errors=True)

    platform = get_platform()
    native_package_url = os.environ.get("NATIVE_PACKAGE_URL", "@anthropic-ai/claude-code")
    platform_package_name = f"{native_package_url}-{platform}"

    logger.debug("Fetching integrity hash for %s@%s", platform_package_name, version)

    code, integrity_output, stderr = await _run_subprocess(
        "npm", "view", f"{platform_package_name}@{version}", "dist.integrity",
        "--registry", ARTIFACTORY_REGISTRY_URL,
        timeout=30.0,
    )

    if code != 0:
        raise Exception(f"npm view integrity failed with code {code}: {stderr}")

    integrity = integrity_output.strip()
    if not integrity:
        raise Exception(
            f"Failed to fetch integrity hash for {platform_package_name}@{version}"
        )

    logger.debug("Got integrity hash for %s: %s", platform, integrity)

    # Create isolated npm project in staging
    os.makedirs(staging_path, exist_ok=True)

    package_json = {
        "name": "claude-native-installer",
        "version": "0.0.1",
        "dependencies": {native_package_url: version},
    }

    package_lock = {
        "name": "claude-native-installer",
        "version": "0.0.1",
        "lockfileVersion": 3,
        "requires": True,
        "packages": {
            "": {
                "name": "claude-native-installer",
                "version": "0.0.1",
                "dependencies": {native_package_url: version},
            },
            f"node_modules/{native_package_url}": {
                "version": version,
                "optionalDependencies": {platform_package_name: version},
            },
            f"node_modules/{platform_package_name}": {
                "version": version,
                "integrity": integrity,
            },
        },
    }

    with open(os.path.join(staging_path, "package.json"), "w", encoding="utf-8") as f:
        json.dump(package_json, f, indent=2)

    with open(os.path.join(staging_path, "package-lock.json"), "w", encoding="utf-8") as f:
        json.dump(package_lock, f, indent=2)

    code, _, stderr = await _run_subprocess(
        "npm", "ci", "--prefer-online", "--registry", ARTIFACTORY_REGISTRY_URL,
        timeout=60.0,
        cwd=staging_path,
    )

    if code != 0:
        raise Exception(f"npm ci failed with code {code}: {stderr}")

    logger.debug("Successfully downloaded and verified %s@%s", native_package_url, version)


async def download_version_from_binary_repo(
    version: str,
    staging_path: str,
    base_url: str,
    auth_config: Optional[dict] = None,
) -> None:
    """Download a version from a binary repository (GCS or generic bucket)."""
    from .installer import get_binary_name, get_platform

    # Remove any partial download
    if os.path.exists(staging_path):
        shutil.rmtree(staging_path, ignore_errors=True)

    platform = get_platform()
    start_time = time.time()

    logger.debug("Attempting binary download for version %s", version)

    # Fetch manifest to get checksum
    manifest_url = f"{base_url}/{version}/manifest.json"
    try:
        manifest = await _fetch_json(manifest_url, auth_config)
    except Exception as e:
        logger.error("Failed to fetch manifest from %s: %s", manifest_url, e)
        raise

    platform_info = manifest.get("platforms", {}).get(platform)
    if not platform_info:
        raise Exception(f"Platform {platform} not found in manifest for version {version}")

    expected_checksum = platform_info["checksum"]

    binary_name = get_binary_name(platform)
    binary_url = f"{base_url}/{version}/{platform}/{binary_name}"

    os.makedirs(staging_path, exist_ok=True)
    binary_path = os.path.join(staging_path, binary_name)

    try:
        await _download_and_verify_binary(
            binary_url,
            expected_checksum,
            binary_path,
            auth_config or {},
        )
        latency_ms = (time.time() - start_time) * 1000
        logger.debug("Binary download succeeded in %.0fms", latency_ms)
    except Exception as e:
        logger.error("Failed to download binary from %s: %s", binary_url, e)
        raise


async def _fetch_json(url: str, auth_config: Optional[dict] = None) -> dict:
    """Fetch JSON from a URL."""
    headers = {}
    if auth_config:
        if "headers" in auth_config:
            headers.update(auth_config["headers"])
        if "auth" in auth_config:
            import base64
            u = auth_config["auth"].get("username", "")
            p = auth_config["auth"].get("password", "")
            token = base64.b64encode(f"{u}:{p}".encode()).decode()
            headers["Authorization"] = f"Basic {token}"

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                resp.raise_for_status()
                return await resp.json()
    except ImportError:
        pass

    import urllib.request
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def download_version(version: str, staging_path: str) -> str:
    """
    Download a specific version.
    Returns 'npm' or 'binary' indicating the download type.
    """
    if os.environ.get("USER_TYPE") == "ant":
        await download_version_from_artifactory(version, staging_path)
        return "npm"

    await download_version_from_binary_repo(version, staging_path, GCS_BUCKET_URL)
    return "binary"


# Exported for testing
_download_and_verify_binary_for_testing = _download_and_verify_binary
