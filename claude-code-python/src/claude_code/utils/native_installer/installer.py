"""
Native Installer Implementation

This module implements the file-based native installer system. It provides:
- Directory structure management with symlinks
- Version installation and activation
- Multi-process safety with locking
- Simple fallback mechanism using modification time
- Support for both JS and native builds
"""
from __future__ import annotations

import asyncio
import logging
import os
import platform as _platform_module
import re
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

VERSION_RETENTION_COUNT = 2

# 7 days in milliseconds - used for mtime-based lock stale timeout.
LOCK_STALE_MS = 7 * 24 * 60 * 60 * 1000


@dataclass
class SetupMessage:
    message: str
    user_action_required: bool
    type: str  # 'path' | 'alias' | 'info' | 'error'


def get_platform() -> str:
    """Get the current platform string including architecture."""
    sys_platform = sys.platform

    if sys_platform == "darwin":
        os_name = "macos"
    elif sys_platform == "win32":
        os_name = "win32"
    else:
        # Linux - check for WSL
        try:
            with open("/proc/version", "r") as f:
                if "microsoft" in f.read().lower():
                    os_name = "linux"  # WSL still uses linux binaries
                else:
                    os_name = "linux"
        except Exception:
            os_name = "linux"

    # Architecture
    machine = _platform_module.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch = "x64"
    elif machine in ("aarch64", "arm64"):
        arch = "arm64"
    else:
        raise Exception(f"Unsupported architecture: {machine}")

    # Check for musl on Linux
    if os_name == "linux":
        if _is_musl_environment():
            return f"linux-{arch}-musl"

    return f"{os_name}-{arch}"


def _is_musl_environment() -> bool:
    """Check if running in a musl libc environment."""
    try:
        result = subprocess.run(
            ["ldd", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = (result.stdout + result.stderr).lower()
        return "musl" in output
    except Exception:
        return False


def get_binary_name(platform: str) -> str:
    """Get the binary name for a given platform."""
    return "claude.exe" if platform.startswith("win32") else "claude"


def _get_xdg_data_home() -> str:
    """Get XDG_DATA_HOME or default."""
    return os.environ.get("XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share"))


def _get_xdg_cache_home() -> str:
    """Get XDG_CACHE_HOME or default."""
    return os.environ.get("XDG_CACHE_HOME", os.path.join(os.path.expanduser("~"), ".cache"))


def _get_xdg_state_home() -> str:
    """Get XDG_STATE_HOME or default."""
    return os.environ.get("XDG_STATE_HOME", os.path.join(os.path.expanduser("~"), ".local", "state"))


def _get_user_bin_dir() -> str:
    """Get the user's bin directory."""
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        return os.path.join(local_app_data, "Programs", "claude-code", "bin")
    return os.path.join(os.path.expanduser("~"), ".local", "bin")


def _get_base_directories() -> dict:
    """Get the base directory paths."""
    platform = get_platform()
    executable_name = get_binary_name(platform)

    return {
        "versions": os.path.join(_get_xdg_data_home(), "claude", "versions"),
        "staging": os.path.join(_get_xdg_cache_home(), "claude", "staging"),
        "locks": os.path.join(_get_xdg_state_home(), "claude", "locks"),
        "executable": os.path.join(_get_user_bin_dir(), executable_name),
    }


async def _is_possible_claude_binary(file_path: str) -> bool:
    """Check if a file could be a Claude binary (exists, is a file, is executable)."""
    try:
        stats = os.stat(file_path)
        if not stat.S_ISREG(stats.st_mode):
            return False
        if stats.st_size == 0:
            return False
        # Check if executable
        if sys.platform != "win32":
            if not (stats.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)):
                return False
        return True
    except (OSError, FileNotFoundError):
        return False


async def _get_version_paths(version: str) -> dict:
    """Get staging and install paths for a version, ensuring directories exist."""
    dirs = _get_base_directories()

    dirs_to_create = [dirs["versions"], dirs["staging"], dirs["locks"]]
    for d in dirs_to_create:
        os.makedirs(d, exist_ok=True)

    # Ensure parent directory of executable exists
    exec_parent = os.path.dirname(dirs["executable"])
    os.makedirs(exec_parent, exist_ok=True)

    install_path = os.path.join(dirs["versions"], version)

    # Create an empty file if it doesn't exist
    try:
        os.stat(install_path)
    except FileNotFoundError:
        with open(install_path, "w", encoding="utf-8"):
            pass

    return {
        "staging_path": os.path.join(dirs["staging"], version),
        "install_path": install_path,
    }


def _get_lock_file_path_from_version_path(dirs: dict, version_path: str) -> str:
    """Get the lock file path corresponding to a version file path."""
    version_name = os.path.basename(version_path)
    return os.path.join(dirs["locks"], f"{version_name}.lock")


async def _try_with_version_lock(
    version_file_path: str,
    callback: Callable,
    retries: int = 0,
) -> bool:
    """
    Execute a callback while holding a lock on a version file.
    Returns False if the file is already locked, True if callback executed.
    """
    from .pid_lock import (
        cleanup_stale_locks,
        is_lock_active,
        is_pid_based_locking_enabled,
        read_lock_content,
        with_lock,
    )

    dirs = _get_base_directories()
    lockfile_path = _get_lock_file_path_from_version_path(dirs, version_file_path)

    # Ensure the locks directory exists
    os.makedirs(dirs["locks"], exist_ok=True)

    if is_pid_based_locking_enabled():
        attempts = 0
        max_attempts = retries + 1
        min_timeout = 1.0 if retries > 0 else 0.1
        max_timeout = 5.0 if retries > 0 else 0.5

        while attempts < max_attempts:
            success = await with_lock(version_file_path, lockfile_path, callback)

            if success:
                return True

            attempts += 1
            if attempts < max_attempts:
                timeout = min(min_timeout * (2 ** (attempts - 1)), max_timeout)
                await asyncio.sleep(timeout)

        _log_lock_acquisition_error(
            version_file_path,
            Exception("Lock held by another process"),
        )
        return False

    # Use simple file-based locking as fallback
    lock_file = lockfile_path
    try:
        # Try to acquire the lock
        try:
            # Create the lock file exclusively
            fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
        except FileExistsError:
            # Check if the lock is stale
            try:
                lock_stat = os.stat(lock_file)
                age_ms = (time.time() - lock_stat.st_mtime) * 1000
                if age_ms < LOCK_STALE_MS:
                    _log_lock_acquisition_error(
                        version_file_path,
                        Exception("Lock already held"),
                    )
                    return False
                # Stale lock - remove and retry
                os.unlink(lock_file)
                fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
            except Exception:
                return False

        try:
            result = callback()
            if asyncio.iscoroutine(result):
                await result
            return True
        except Exception as e:
            logger.error("Error in locked callback: %s", e)
            raise
    finally:
        try:
            os.unlink(lock_file)
        except Exception:
            pass


def _log_lock_acquisition_error(version_path: str, lock_error: Exception) -> None:
    """Log a lock acquisition error."""
    logger.error(
        "NON-FATAL: Lock acquisition failed for %s (expected in multi-process scenarios): %s",
        version_path,
        lock_error,
    )


async def _atomic_move_to_install_path(staged_binary_path: str, install_path: str) -> None:
    """Move a staged binary to the install path atomically."""
    os.makedirs(os.path.dirname(install_path), exist_ok=True)

    temp_install_path = f"{install_path}.tmp.{os.getpid()}.{int(time.time() * 1000)}"

    try:
        shutil.copy2(staged_binary_path, temp_install_path)
        # Make executable
        current_mode = os.stat(temp_install_path).st_mode
        os.chmod(temp_install_path, current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        os.rename(temp_install_path, install_path)
        logger.debug("Atomically installed binary to %s", install_path)
    except Exception as e:
        # Clean up temp file if it exists
        try:
            os.unlink(temp_install_path)
        except Exception:
            pass
        raise


async def _install_version_from_package(staging_path: str, install_path: str) -> None:
    """Install from npm package structure in staging."""
    node_modules_dir = os.path.join(staging_path, "node_modules", "@anthropic-ai")

    try:
        entries = os.listdir(node_modules_dir)
    except FileNotFoundError:
        raise Exception("Could not find platform-specific native package")

    native_package = next(
        (e for e in entries if e.startswith("claude-cli-native-")), None
    )

    if not native_package:
        raise Exception("Could not find platform-specific native package")

    staged_binary_path = os.path.join(node_modules_dir, native_package, "cli")

    try:
        os.stat(staged_binary_path)
    except FileNotFoundError:
        raise Exception("Native binary not found in staged package")

    await _atomic_move_to_install_path(staged_binary_path, install_path)

    # Clean up staging directory
    shutil.rmtree(staging_path, ignore_errors=True)


async def _install_version_from_binary(staging_path: str, install_path: str) -> None:
    """Install from direct binary download."""
    platform = get_platform()
    binary_name = get_binary_name(platform)
    staged_binary_path = os.path.join(staging_path, binary_name)

    try:
        os.stat(staged_binary_path)
    except FileNotFoundError:
        raise Exception("Staged binary not found")

    await _atomic_move_to_install_path(staged_binary_path, install_path)

    # Clean up staging directory
    shutil.rmtree(staging_path, ignore_errors=True)


async def _install_version(
    staging_path: str,
    install_path: str,
    download_type: str,
) -> None:
    """Install a downloaded version."""
    if download_type == "npm":
        await _install_version_from_package(staging_path, install_path)
    else:
        await _install_version_from_binary(staging_path, install_path)


async def _version_is_available(version: str) -> bool:
    """Check if a version is already installed."""
    paths = await _get_version_paths(version)
    return await _is_possible_claude_binary(paths["install_path"])


async def _perform_version_update(version: str, force_reinstall: bool = False) -> bool:
    """
    Performs the core update operation: download (if needed), install, and update symlink.
    Returns whether a new install was performed.
    """
    from .download import download_version

    paths = await _get_version_paths(version)
    staging_path = paths["staging_path"]
    install_path = paths["install_path"]
    dirs = _get_base_directories()
    executable_path = dirs["executable"]

    # Use unique staging path for lockless mode
    enable_lockless = os.environ.get("ENABLE_LOCKLESS_UPDATES", "").lower() in ("true", "1", "yes")
    if enable_lockless:
        staging_path = f"{staging_path}.{os.getpid()}.{int(time.time() * 1000)}"

    needs_install = not (await _version_is_available(version)) or force_reinstall
    if needs_install:
        logger.debug(
            "%s native installer version %s",
            "Force reinstalling" if force_reinstall else "Downloading",
            version,
        )
        download_type = await download_version(version, staging_path)
        await _install_version(staging_path, install_path, download_type)
    else:
        logger.debug("Version %s already installed, updating symlink", version)

    # Create direct symlink from ~/.local/bin/claude to the version binary
    await _remove_directory_if_empty(executable_path)
    await _update_symlink(executable_path, install_path)

    # Verify the executable was actually created/updated
    if not (await _is_possible_claude_binary(executable_path)):
        install_path_exists = os.path.exists(install_path)
        raise Exception(
            f"Failed to create executable at {executable_path}. "
            f"Source file exists: {install_path_exists}. "
            f"Check write permissions to {executable_path}."
        )

    return needs_install


async def _update_latest(
    channel_or_version: str,
    force_reinstall: bool = False,
) -> dict:
    """
    Update to the latest version.
    Returns a dict with success, latestVersion, and optionally lockFailed/lockHolderPid.
    """
    from .download import get_latest_version
    from .pid_lock import (
        is_lock_active,
        is_pid_based_locking_enabled,
        read_lock_content,
    )

    start_time = time.time()
    version = await get_latest_version(channel_or_version)
    dirs = _get_base_directories()
    executable_path = dirs["executable"]

    logger.debug("Checking for native installer update to version %s", version)

    was_new_install = False
    latency_ms: float

    enable_lockless = os.environ.get("ENABLE_LOCKLESS_UPDATES", "").lower() in ("true", "1", "yes")

    if enable_lockless:
        was_new_install = await _perform_version_update(version, force_reinstall)
        latency_ms = (time.time() - start_time) * 1000
    else:
        paths = await _get_version_paths(version)
        install_path = paths["install_path"]

        if force_reinstall:
            await _force_remove_lock(install_path)

        lock_acquired = await _try_with_version_lock(
            install_path,
            lambda: _perform_version_update(version, force_reinstall),
            retries=3,
        )

        latency_ms = (time.time() - start_time) * 1000

        if not lock_acquired:
            lock_holder_pid: Optional[int] = None
            if is_pid_based_locking_enabled():
                lockfile_path = _get_lock_file_path_from_version_path(dirs, install_path)
                if is_lock_active(lockfile_path):
                    content = read_lock_content(lockfile_path)
                    if content:
                        lock_holder_pid = content.pid

            return {
                "success": False,
                "latest_version": version,
                "lock_failed": True,
                "lock_holder_pid": lock_holder_pid,
            }

    logger.debug("Successfully updated to version %s", version)
    return {"success": True, "latest_version": version}


# In-process singleflight guard to prevent duplicate downloads
_in_flight_install: Optional[asyncio.Task] = None


async def install_latest(
    channel_or_version: str,
    force_reinstall: bool = False,
) -> dict:
    """
    Install the latest version. Returns a dict with latestVersion, wasUpdated, etc.
    Uses singleflight pattern to prevent duplicate downloads.
    """
    global _in_flight_install

    if force_reinstall:
        return await _install_latest_impl(channel_or_version, force_reinstall)

    if _in_flight_install is not None and not _in_flight_install.done():
        logger.debug("installLatest: joining in-flight call")
        return await _in_flight_install

    loop = asyncio.get_event_loop()
    task = loop.create_task(_install_latest_impl(channel_or_version, force_reinstall))
    _in_flight_install = task

    try:
        return await task
    finally:
        if _in_flight_install is task:
            _in_flight_install = None


async def _install_latest_impl(
    channel_or_version: str,
    force_reinstall: bool = False,
) -> dict:
    """Core install implementation."""
    update_result = await _update_latest(channel_or_version, force_reinstall)

    if not update_result["success"]:
        return {
            "latest_version": None,
            "was_updated": False,
            "lock_failed": update_result.get("lock_failed"),
            "lock_holder_pid": update_result.get("lock_holder_pid"),
        }

    # Installation succeeded - trigger cleanup
    asyncio.get_event_loop().create_task(_cleanup_old_versions_safe())

    return {
        "latest_version": update_result["latest_version"],
        "was_updated": update_result["success"],
        "lock_failed": False,
    }


async def _cleanup_old_versions_safe() -> None:
    """Wrapper to run cleanup without raising."""
    try:
        await cleanup_old_versions()
    except Exception as e:
        logger.debug("Cleanup failed (non-fatal): %s", e)


async def _get_version_from_symlink(symlink_path: str) -> Optional[str]:
    """Get the version path from a symlink."""
    try:
        target = os.readlink(symlink_path)
        absolute_target = os.path.realpath(
            os.path.join(os.path.dirname(symlink_path), target)
        )
        if await _is_possible_claude_binary(absolute_target):
            return absolute_target
    except Exception:
        pass
    return None


async def remove_directory_if_empty(path: str) -> None:
    """Remove a directory if it's empty (or remove the path if it's not a dir)."""
    try:
        os.rmdir(path)
        logger.debug("Removed empty directory at %s", path)
    except OSError as e:
        import errno
        # Expected cases: not a dir, missing, not empty
        if e.errno not in (errno.ENOTDIR, errno.ENOENT, errno.ENOTEMPTY):
            logger.debug("Could not remove directory at %s: %s", path, e)


# Alias used internally
_remove_directory_if_empty = remove_directory_if_empty


async def _update_symlink(symlink_path: str, target_path: str) -> bool:
    """
    Create or update a symlink from symlink_path to target_path.
    On Windows, copies the file directly.
    Returns True if updated, False if already correct.
    """
    platform = get_platform()
    is_windows = platform.startswith("win32")

    if is_windows:
        return await _update_symlink_windows(symlink_path, target_path)

    return await _update_symlink_unix(symlink_path, target_path)


async def _update_symlink_windows(symlink_path: str, target_path: str) -> bool:
    """Update the executable on Windows by copying."""
    try:
        os.makedirs(os.path.dirname(symlink_path), exist_ok=True)

        # Check if file already exists
        existing_stats = None
        try:
            existing_stats = os.stat(symlink_path)
        except FileNotFoundError:
            pass

        if existing_stats:
            try:
                target_stats = os.stat(target_path)
                if existing_stats.st_size == target_stats.st_size:
                    return False
            except Exception:
                pass

            # Rename strategy for running executables on Windows
            old_file_name = f"{symlink_path}.old.{int(time.time() * 1000)}"
            os.rename(symlink_path, old_file_name)

            try:
                shutil.copy2(target_path, symlink_path)
                try:
                    os.unlink(old_file_name)
                except Exception:
                    pass
            except Exception as copy_error:
                try:
                    os.rename(old_file_name, symlink_path)
                except Exception as restore_error:
                    raise Exception(f"Failed to restore old executable: {restore_error}") from copy_error
                raise
        else:
            if not os.path.exists(target_path):
                raise Exception(f"Source file does not exist: {target_path}")
            shutil.copy2(target_path, symlink_path)

        return True
    except Exception as e:
        logger.error("Failed to copy executable from %s to %s: %s", target_path, symlink_path, e)
        return False


async def _update_symlink_unix(symlink_path: str, target_path: str) -> bool:
    """Create or update a symlink on Unix systems."""
    try:
        os.makedirs(os.path.dirname(symlink_path), exist_ok=True)
    except Exception as e:
        logger.error("Failed to create directory for symlink: %s", e)
        return False

    # Check if symlink already exists and points to the correct target
    try:
        symlink_exists = False
        try:
            os.stat(symlink_path)
            symlink_exists = True
        except FileNotFoundError:
            pass

        if symlink_exists:
            try:
                current_target = os.readlink(symlink_path)
                resolved_current = os.path.realpath(
                    os.path.join(os.path.dirname(symlink_path), current_target)
                )
                resolved_target = os.path.realpath(target_path)

                if resolved_current == resolved_target:
                    return False
            except OSError:
                pass

            os.unlink(symlink_path)
    except Exception as e:
        logger.error("Failed to check/remove existing symlink: %s", e)

    # Use atomic rename to avoid race conditions
    temp_symlink = f"{symlink_path}.tmp.{os.getpid()}.{int(time.time() * 1000)}"
    try:
        os.symlink(target_path, temp_symlink)
        os.rename(temp_symlink, symlink_path)
        logger.debug("Atomically updated symlink %s -> %s", symlink_path, target_path)
        return True
    except Exception as e:
        try:
            os.unlink(temp_symlink)
        except Exception:
            pass
        logger.error("Failed to create symlink from %s to %s: %s", symlink_path, target_path, e)
        return False


async def check_install(force: bool = False) -> list[SetupMessage]:
    """
    Check if the native installation is properly configured.
    Returns a list of setup messages/warnings.
    """
    # Skip if disabled
    if os.environ.get("DISABLE_INSTALLATION_CHECKS", "").lower() in ("true", "1", "yes"):
        return []

    dirs = _get_base_directories()
    messages: list[SetupMessage] = []
    local_bin_dir = os.path.dirname(dirs["executable"])
    platform = get_platform()
    is_windows = platform.startswith("win32")

    # Check if bin directory exists
    if not os.path.exists(local_bin_dir):
        messages.append(SetupMessage(
            message=f"installMethod is native, but directory {local_bin_dir} does not exist",
            user_action_required=True,
            type="error",
        ))

    # Check if claude executable exists and is valid
    if is_windows:
        if not (await _is_possible_claude_binary(dirs["executable"])):
            messages.append(SetupMessage(
                message=f"installMethod is native, but claude command is missing or invalid at {dirs['executable']}",
                user_action_required=True,
                type="error",
            ))
    else:
        try:
            target = os.readlink(dirs["executable"])
            absolute_target = os.path.realpath(
                os.path.join(os.path.dirname(dirs["executable"]), target)
            )
            if not (await _is_possible_claude_binary(absolute_target)):
                messages.append(SetupMessage(
                    message=f"Claude symlink points to missing or invalid binary: {target}",
                    user_action_required=True,
                    type="error",
                ))
        except FileNotFoundError:
            messages.append(SetupMessage(
                message=f"installMethod is native, but claude command not found at {dirs['executable']}",
                user_action_required=True,
                type="error",
            ))
        except OSError:
            # EINVAL - not a symlink
            if not (await _is_possible_claude_binary(dirs["executable"])):
                messages.append(SetupMessage(
                    message=f"{dirs['executable']} exists but is not a valid Claude binary",
                    user_action_required=True,
                    type="error",
                ))

    # Check if bin directory is in PATH
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    is_in_path = any(
        os.path.realpath(entry) == os.path.realpath(local_bin_dir)
        for entry in path_entries
        if entry
    )

    if not is_in_path:
        if is_windows:
            win_bin_path = local_bin_dir.replace("/", "\\")
            messages.append(SetupMessage(
                message=f"Native installation exists but {win_bin_path} is not in your PATH. "
                        "Add it by opening: System Properties → Environment Variables → "
                        "Edit User PATH → New → Add the path above. Then restart your terminal.",
                user_action_required=True,
                type="path",
            ))
        else:
            home = os.path.expanduser("~")
            display_path = local_bin_dir.replace(home, "~")
            messages.append(SetupMessage(
                message=f"Native installation exists but ~/.local/bin is not in your PATH. Run:\n\n"
                        f"echo 'export PATH=\"$HOME/.local/bin:$PATH\"' >> ~/.bashrc && source ~/.bashrc",
                user_action_required=True,
                type="path",
            ))

    return messages


async def lock_current_version() -> None:
    """
    Acquire a lock on the current running version to prevent it from being deleted.
    This lock is held for the entire lifetime of the process.
    """
    from .pid_lock import (
        acquire_process_lifetime_lock,
        is_pid_based_locking_enabled,
    )

    dirs = _get_base_directories()

    # Only lock if we're running from the versions directory
    if dirs["versions"] not in os.path.realpath(sys.executable):
        return

    version_path = os.path.realpath(sys.executable)
    try:
        lockfile_path = _get_lock_file_path_from_version_path(dirs, version_path)
        os.makedirs(dirs["locks"], exist_ok=True)

        if is_pid_based_locking_enabled():
            acquired = await acquire_process_lifetime_lock(version_path, lockfile_path)
            if not acquired:
                _log_lock_acquisition_error(
                    version_path,
                    Exception("Lock already held by another process"),
                )
                return
            logger.debug("Acquired PID lock on running version: %s", version_path)
        else:
            # Simple mtime-based lock for the lifetime of the process
            _simple_lock_for_lifetime(lockfile_path)
    except FileNotFoundError:
        logger.debug("Cannot lock current version - file does not exist: %s", version_path)
    except Exception as e:
        logger.debug("NON-FATAL: Failed to lock current version: %s", e)


def _simple_lock_for_lifetime(lock_file_path: str) -> None:
    """Create a simple lock file that's removed on process exit."""
    import atexit

    try:
        with open(lock_file_path, "w", encoding="utf-8") as f:
            import json
            json.dump({"pid": os.getpid(), "timestamp": time.time()}, f)
    except Exception:
        pass

    def cleanup() -> None:
        try:
            os.unlink(lock_file_path)
        except Exception:
            pass

    atexit.register(cleanup)


async def _force_remove_lock(version_file_path: str) -> None:
    """Force-remove a lock file for a given version path."""
    dirs = _get_base_directories()
    lockfile_path = _get_lock_file_path_from_version_path(dirs, version_file_path)

    try:
        os.unlink(lockfile_path)
        logger.debug("Force-removed lock file at %s", lockfile_path)
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug("Failed to force-remove lock file: %s", e)


async def cleanup_old_versions() -> None:
    """Clean up old versions, keeping only VERSION_RETENTION_COUNT most recent."""
    from .pid_lock import (
        cleanup_stale_locks,
        is_lock_active,
        is_pid_based_locking_enabled,
    )

    await asyncio.sleep(0)  # Yield to ensure we don't block startup

    dirs = _get_base_directories()
    one_hour_ago = time.time() - 3600

    # Clean up old renamed executables on Windows
    if get_platform().startswith("win32"):
        executable_dir = os.path.dirname(dirs["executable"])
        try:
            for fname in os.listdir(executable_dir):
                if not re.match(r"^claude\.exe\.old\.\d+$", fname):
                    continue
                try:
                    os.unlink(os.path.join(executable_dir, fname))
                except Exception:
                    pass
        except Exception:
            pass

    # Clean up orphaned staging directories older than 1 hour
    try:
        for entry in os.listdir(dirs["staging"]):
            staging_path = os.path.join(dirs["staging"], entry)
            try:
                stats = os.stat(staging_path)
                if stats.st_mtime < one_hour_ago:
                    shutil.rmtree(staging_path, ignore_errors=True)
                    logger.debug("Cleaned up old staging directory: %s", entry)
            except Exception:
                pass
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug("Failed to clean up staging directories: %s", e)

    # Clean up stale PID locks
    if is_pid_based_locking_enabled():
        stale_locks_cleaned = cleanup_stale_locks(dirs["locks"])
        if stale_locks_cleaned > 0:
            logger.debug("Cleaned up %d stale version locks", stale_locks_cleaned)

    # Enumerate version files
    try:
        version_entries = os.listdir(dirs["versions"])
    except FileNotFoundError:
        return
    except Exception as e:
        logger.debug("Failed to list versions directory: %s", e)
        return

    version_files = []
    temp_files_cleaned = 0

    for entry in version_entries:
        entry_path = os.path.join(dirs["versions"], entry)

        if re.match(r"\.tmp\.\d+\.\d+$", entry):
            # Orphaned temp install file
            try:
                file_stat = os.stat(entry_path)
                if file_stat.st_mtime < one_hour_ago:
                    os.unlink(entry_path)
                    temp_files_cleaned += 1
            except Exception:
                pass
            continue

        try:
            file_stat = os.stat(entry_path)
            if not stat.S_ISREG(file_stat.st_mode):
                continue
            if sys.platform != "win32" and file_stat.st_size > 0:
                if not (file_stat.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)):
                    continue
            version_files.append({
                "name": entry,
                "path": entry_path,
                "resolved_path": os.path.realpath(entry_path),
                "mtime": file_stat.st_mtime,
            })
        except Exception:
            pass

    if not version_files:
        return

    # Identify protected versions
    current_binary_path = os.path.realpath(sys.executable)
    protected_versions: set[str] = set()

    if dirs["versions"] in current_binary_path:
        protected_versions.add(current_binary_path)

    current_symlink_version = await _get_version_from_symlink(dirs["executable"])
    if current_symlink_version:
        protected_versions.add(current_symlink_version)

    # Protect versions with active locks
    for v in version_files:
        if v["resolved_path"] in protected_versions:
            continue

        lock_file_path = _get_lock_file_path_from_version_path(dirs, v["resolved_path"])
        has_active_lock = False

        if is_pid_based_locking_enabled():
            has_active_lock = is_lock_active(lock_file_path)
        else:
            try:
                if os.path.exists(lock_file_path):
                    lock_stat = os.stat(lock_file_path)
                    age_ms = (time.time() - lock_stat.st_mtime) * 1000
                    has_active_lock = age_ms < LOCK_STALE_MS
            except Exception:
                has_active_lock = False

        if has_active_lock:
            protected_versions.add(v["resolved_path"])
            logger.debug("Protecting locked version from cleanup: %s", v["name"])

    # Eligible versions: not protected, sorted newest first
    eligible_versions = sorted(
        [v for v in version_files if v["resolved_path"] not in protected_versions],
        key=lambda v: v["mtime"],
        reverse=True,
    )

    versions_to_delete = eligible_versions[VERSION_RETENTION_COUNT:]

    if not versions_to_delete:
        return

    deleted_count = 0
    lock_failed_count = 0
    error_count = 0

    async def _delete_version(version: dict) -> None:
        nonlocal deleted_count, lock_failed_count, error_count
        try:
            deleted = await _try_with_version_lock(version["path"], lambda: os.unlink(version["path"]))
            if deleted:
                deleted_count += 1
            else:
                lock_failed_count += 1
                logger.debug("Skipping deletion of %s - locked by another process", version["name"])
        except Exception as e:
            error_count += 1
            logger.error("Failed to delete version %s: %s", version["name"], e)

    await asyncio.gather(*[_delete_version(v) for v in versions_to_delete])

    logger.debug(
        "Version cleanup: total=%d deleted=%d protected=%d lock_failed=%d errors=%d",
        len(version_files),
        deleted_count,
        len(protected_versions),
        lock_failed_count,
        error_count,
    )


async def _is_npm_symlink(executable_path: str) -> bool:
    """Check if a given path is managed by npm."""
    try:
        target_path = executable_path
        file_stat = os.lstat(executable_path)
        if stat.S_ISLNK(file_stat.st_mode):
            target_path = os.path.realpath(executable_path)
        return target_path.endswith(".js") or "node_modules" in target_path
    except Exception:
        return False


async def remove_installed_symlink() -> None:
    """
    Remove the claude symlink from the executable directory.
    Only removes if it's a native binary symlink, not npm-managed JS files.
    """
    dirs = _get_base_directories()

    try:
        if await _is_npm_symlink(dirs["executable"]):
            logger.debug("Skipping removal of %s - appears to be npm-managed", dirs["executable"])
            return

        os.unlink(dirs["executable"])
        logger.debug("Removed claude symlink at %s", dirs["executable"])
    except FileNotFoundError:
        return
    except Exception as e:
        logger.error("Failed to remove claude symlink: %s", e)


async def cleanup_shell_aliases() -> list[SetupMessage]:
    """
    Clean up old claude aliases from shell configuration files.
    Only handles alias removal, not PATH setup.
    """
    messages: list[SetupMessage] = []

    # Get shell config files
    shell_configs = _get_shell_config_paths()

    for shell_type, config_file in shell_configs.items():
        if not config_file or not os.path.exists(config_file):
            continue

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            filtered = [line for line in lines if not _is_claude_alias_line(line)]
            had_alias = len(filtered) < len(lines)

            if had_alias:
                with open(config_file, "w", encoding="utf-8") as f:
                    f.writelines(filtered)
                messages.append(SetupMessage(
                    message=f"Removed claude alias from {config_file}. Run: unalias claude",
                    user_action_required=True,
                    type="alias",
                ))
                logger.debug("Cleaned up claude alias from %s config", shell_type)
        except Exception as e:
            logger.error("Error processing %s: %s", config_file, e)
            messages.append(SetupMessage(
                message=f"Failed to clean up {config_file}: {e}",
                user_action_required=False,
                type="error",
            ))

    return messages


def _is_claude_alias_line(line: str) -> bool:
    """Check if a line is a claude alias definition."""
    stripped = line.strip()
    return bool(re.match(r"^alias\s+claude\s*=", stripped))


def _get_shell_config_paths() -> dict:
    """Get shell configuration file paths."""
    home = os.path.expanduser("~")
    return {
        "bash": os.path.join(home, ".bashrc"),
        "zsh": os.path.join(home, ".zshrc"),
        "fish": os.path.join(home, ".config", "fish", "config.fish"),
    }


async def _attempt_npm_uninstall(package_name: str) -> dict:
    """Attempt to uninstall an npm package globally."""
    proc = await asyncio.create_subprocess_exec(
        "npm", "uninstall", "-g", package_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=60.0)
        code = proc.returncode or 0
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        stdout = stdout_bytes.decode("utf-8", errors="replace")
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return {"success": False, "error": "npm uninstall timed out"}

    if code == 0:
        logger.debug("Removed global npm installation of %s", package_name)
        return {"success": True}
    elif stderr and "npm ERR! code E404" not in stderr:
        if "npm error code ENOTEMPTY" in stderr:
            logger.debug("ENOTEMPTY error, attempting manual removal")
            manual_result = await _manual_remove_npm_package(package_name)
            if manual_result["success"]:
                return {"success": True, "warning": manual_result.get("warning")}
            elif manual_result.get("error"):
                return {
                    "success": False,
                    "error": f"Failed to remove {package_name}: {stderr}. "
                             f"Manual removal also failed: {manual_result['error']}",
                }
        return {
            "success": False,
            "error": f"Failed to remove global npm installation of {package_name}: {stderr}",
        }

    return {"success": False}


async def _manual_remove_npm_package(package_name: str) -> dict:
    """Manually remove npm package files."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "npm", "config", "get", "prefix",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        if not stdout_bytes:
            return {"success": False, "error": "Failed to get npm global prefix"}

        global_prefix = stdout_bytes.decode().strip()
        manually_removed = False

        platform = get_platform()
        if platform.startswith("win32"):
            for fname in ("claude.cmd", "claude.ps1", "claude"):
                try:
                    os.unlink(os.path.join(global_prefix, fname))
                    manually_removed = True
                except Exception:
                    pass
        else:
            bin_symlink = os.path.join(global_prefix, "bin", "claude")
            try:
                os.unlink(bin_symlink)
                manually_removed = True
            except Exception:
                pass

        if manually_removed:
            node_modules_path = (
                os.path.join(global_prefix, "node_modules", package_name)
                if platform.startswith("win32")
                else os.path.join(global_prefix, "lib", "node_modules", package_name)
            )
            return {
                "success": True,
                "warning": f"{package_name} executables removed, but node_modules directory was "
                           f"left intact for safety. You may manually delete it later at: {node_modules_path}",
            }
        return {"success": False}
    except Exception as e:
        return {"success": False, "error": f"Manual removal failed: {e}"}


async def cleanup_npm_installations() -> dict:
    """
    Clean up npm global installations of Claude.
    Returns a dict with removed count, errors, and warnings.
    """
    errors: list[str] = []
    warnings: list[str] = []
    removed = 0

    # Always attempt to remove @anthropic-ai/claude-code
    code_package_result = await _attempt_npm_uninstall("@anthropic-ai/claude-code")
    if code_package_result["success"]:
        removed += 1
        if code_package_result.get("warning"):
            warnings.append(code_package_result["warning"])
    elif code_package_result.get("error"):
        errors.append(code_package_result["error"])

    # Check for local installation at ~/.claude/local
    local_install_dir = os.path.join(os.path.expanduser("~"), ".claude", "local")
    try:
        shutil.rmtree(local_install_dir)
        removed += 1
        logger.debug("Removed local installation at %s", local_install_dir)
    except FileNotFoundError:
        pass
    except Exception as e:
        errors.append(f"Failed to remove {local_install_dir}: {e}")

    return {"removed": removed, "errors": errors, "warnings": warnings}
