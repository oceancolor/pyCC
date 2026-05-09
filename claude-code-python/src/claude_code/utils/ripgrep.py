# 原始 TS: utils/ripgrep.ts
"""Ripgrep (rg) subprocess wrapper for fast code/text search.

Ported from utils/ripgrep.ts — full implementation including:
- System/builtin/embedded ripgrep detection and config
- Async/streaming ripgrep execution with timeout handling
- EAGAIN retry with single-threaded mode
- RipgrepTimeoutError for distinguishing no-matches vs timeout
- countFilesRoundedRg with privacy rounding
- ripGrepStream for streaming results
- codesign helper for macOS
- getRipgrepStatus / testRipgrepOnFirstUse
"""

from __future__ import annotations

import asyncio
import functools
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class RipgrepConfig:
    """Describes how to invoke ripgrep on this system."""
    mode: str  # "system" | "builtin" | "embedded"
    command: str
    args: List[str] = field(default_factory=list)
    argv0: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal helpers from other modules
# ---------------------------------------------------------------------------

def _is_env_defined_falsy(val: Optional[str]) -> bool:
    """Return True when the env var is defined AND falsy (0, false, no, empty)."""
    if val is None:
        return False
    return val.strip().lower() in ("0", "false", "no", "")


def _log_error(err: Exception) -> None:
    try:
        from claude_code.utils.log import log_error  # type: ignore
        log_error(err)
    except (ImportError, Exception):
        pass


def _log_for_debugging(msg: str) -> None:
    try:
        from claude_code.utils.debug import log_for_debugging  # type: ignore
        log_for_debugging(msg)
    except (ImportError, Exception):
        pass


def _log_event(name: str, data: dict) -> None:
    try:
        from claude_code.services.analytics import log_event  # type: ignore
        log_event(name, data)
    except (ImportError, Exception):
        pass


def _get_platform() -> str:
    """Return canonical platform string ('wsl', 'mac', 'linux', 'windows')."""
    try:
        from claude_code.utils.platform import get_platform  # type: ignore
        return get_platform()
    except (ImportError, Exception):
        if sys.platform == "win32":
            return "windows"
        if sys.platform == "darwin":
            return "mac"
        # Simple WSL detection
        if os.path.exists("/proc/version"):
            try:
                content = open("/proc/version").read().lower()
                if "microsoft" in content or "wsl" in content:
                    return "wsl"
            except OSError:
                pass
        return "linux"


def _is_in_bundled_mode() -> bool:
    try:
        from claude_code.utils.bundled_mode import is_in_bundled_mode  # type: ignore
        return is_in_bundled_mode()
    except (ImportError, Exception):
        return False


def _exec_file_no_throw(
    command: str,
    args: List[str],
    timeout: Optional[float] = None,
) -> Tuple[int, str, str]:
    """Run *command* with *args*; return (returncode, stdout, stderr) — never raises."""
    try:
        result = subprocess.run(
            [command] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except Exception:
        return -1, "", ""


def _find_executable(name: str) -> Optional[str]:
    return shutil.which(name)


# ---------------------------------------------------------------------------
# Executable discovery
# ---------------------------------------------------------------------------

def _find_embedded_rg() -> Optional[str]:
    """Return path to a bundled rg binary, or None."""
    here = os.path.dirname(os.path.abspath(__file__))
    machine = platform.machine().lower()
    plat = sys.platform
    # Typical vendored layout: vendor/ripgrep/<arch>-<platform>/rg
    candidates = [
        os.path.join(here, "..", "..", "vendor", "ripgrep", f"{machine}-{plat}", "rg"),
        os.path.join(here, "..", "..", "vendor", "rg"),
        os.path.join(here, "..", "..", "bin", "rg"),
    ]
    for path in candidates:
        norm = os.path.normpath(path)
        if os.path.isfile(norm) and os.access(norm, os.X_OK):
            return norm
    return None


_rg_config_cache: Optional[RipgrepConfig] = None


def get_ripgrep_config() -> RipgrepConfig:
    """Locate the ripgrep executable and return its config (memoized)."""
    global _rg_config_cache
    if _rg_config_cache is not None:
        return _rg_config_cache

    user_wants_system = _is_env_defined_falsy(os.environ.get("USE_BUILTIN_RIPGREP"))

    if user_wants_system:
        system_path = _find_executable("rg")
        if system_path:
            # SECURITY: Use plain 'rg' name to prevent PATH hijacking
            _rg_config_cache = RipgrepConfig(mode="system", command="rg", args=[])
            return _rg_config_cache

    if _is_in_bundled_mode():
        _rg_config_cache = RipgrepConfig(
            mode="embedded",
            command=sys.executable,
            args=["--no-config"],
            argv0="rg",
        )
        return _rg_config_cache

    # Fall back to embedded/vendored binary
    embedded = _find_embedded_rg()
    if embedded:
        _rg_config_cache = RipgrepConfig(mode="builtin", command=embedded, args=[])
        return _rg_config_cache

    # Last resort: trust system rg
    _rg_config_cache = RipgrepConfig(mode="system", command="rg", args=[])
    return _rg_config_cache


def ripgrep_command() -> Tuple[str, List[str], Optional[str]]:
    """Return (rg_path, rg_args, argv0)."""
    cfg = get_ripgrep_config()
    return cfg.command, cfg.args, cfg.argv0


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------

class RipgrepTimeoutError(Exception):
    """Raised when ripgrep times out before finishing."""

    def __init__(self, message: str, partial_results: List[str]) -> None:
        super().__init__(message)
        self.name = "RipgrepTimeoutError"
        self.partial_results = partial_results


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_BUFFER_SIZE = 20_000_000  # 20 MB


def _is_eagain_error(stderr: str) -> bool:
    return "os error 11" in stderr or "Resource temporarily unavailable" in stderr


def _get_default_timeout_ms() -> float:
    env_seconds = os.environ.get("CLAUDE_CODE_GLOB_TIMEOUT_SECONDS", "")
    try:
        parsed = int(env_seconds)
        if parsed > 0:
            return parsed * 1000.0
    except (ValueError, TypeError):
        pass
    return 60_000.0 if _get_platform() == "wsl" else 20_000.0


# ---------------------------------------------------------------------------
# macOS codesign helper
# ---------------------------------------------------------------------------

_already_done_sign_check = False


async def _codesign_ripgrep_if_necessary() -> None:
    global _already_done_sign_check
    if sys.platform != "darwin" or _already_done_sign_check:
        return
    _already_done_sign_check = True

    cfg = get_ripgrep_config()
    if cfg.mode != "builtin":
        return

    builtin_path = cfg.command
    code, stdout, _ = _exec_file_no_throw("codesign", ["-vv", "-d", builtin_path])
    lines = stdout.splitlines()
    needs_signed = any("linker-signed" in line for line in lines)
    if not needs_signed:
        return

    try:
        sign_code, sign_stdout, sign_stderr = _exec_file_no_throw(
            "codesign",
            ["--sign", "-", "--force", "--preserve-metadata=entitlements,requirements,flags,runtime", builtin_path],
        )
        if sign_code != 0:
            _log_error(Exception(f"Failed to sign ripgrep: {sign_stdout} {sign_stderr}"))

        q_code, q_stdout, q_stderr = _exec_file_no_throw(
            "xattr", ["-d", "com.apple.quarantine", builtin_path]
        )
        if q_code != 0:
            _log_error(Exception(f"Failed to remove quarantine: {q_stdout} {q_stderr}"))
    except Exception as exc:
        _log_error(exc)


# ---------------------------------------------------------------------------
# Core subprocess runner
# ---------------------------------------------------------------------------

async def _rip_grep_raw(
    args: List[str],
    target: str,
    abort_event: Optional[asyncio.Event] = None,
    single_thread: bool = False,
) -> Tuple[Optional[int], str, str]:
    """Run ripgrep and return (returncode, stdout, stderr).

    Returns (None, partial_stdout, stderr) on timeout/abort.
    """
    rg_path, rg_args, argv0 = ripgrep_command()
    thread_args = ["-j", "1"] if single_thread else []
    full_args = rg_args + thread_args + args + [target]
    timeout_ms = _get_default_timeout_ms()

    cmd = [rg_path] + full_args

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **({"argv0": argv0} if argv0 else {})},
        )
    except Exception as exc:
        return -1, "", str(exc)

    stdout_chunks: List[bytes] = []
    stderr_chunks: List[bytes] = []
    stdout_size = 0
    stderr_size = 0
    stdout_truncated = False
    stderr_truncated = False

    async def _read_stream(stream: asyncio.StreamReader, chunks: List[bytes], size_ref: List[int], truncated_ref: List[bool]) -> None:
        while True:
            chunk = await stream.read(65536)
            if not chunk:
                break
            if not truncated_ref[0]:
                chunks.append(chunk)
                size_ref[0] += len(chunk)
                if size_ref[0] > MAX_BUFFER_SIZE:
                    truncated_ref[0] = True

    stdout_size_ref = [0]
    stderr_size_ref = [0]
    stdout_truncated_ref = [False]
    stderr_truncated_ref = [False]

    async def _wait_with_timeout() -> Optional[int]:
        try:
            return await asyncio.wait_for(proc.wait(), timeout=timeout_ms / 1000.0)
        except asyncio.TimeoutError:
            try:
                proc.terminate()
                await asyncio.sleep(5)
                proc.kill()
            except ProcessLookupError:
                pass
            return None

    if proc.stdout and proc.stderr:
        _, _, rc = await asyncio.gather(
            _read_stream(proc.stdout, stdout_chunks, stdout_size_ref, stdout_truncated_ref),
            _read_stream(proc.stderr, stderr_chunks, stderr_size_ref, stderr_truncated_ref),
            _wait_with_timeout(),
        )
    else:
        rc = await _wait_with_timeout()

    stdout_bytes = b"".join(stdout_chunks)
    stderr_bytes = b"".join(stderr_chunks)
    stdout_str = stdout_bytes.decode(errors="replace")
    stderr_str = stderr_bytes.decode(errors="replace")

    return rc, stdout_str, stderr_str


# ---------------------------------------------------------------------------
# ripGrep — main public API (matches TS ripGrep)
# ---------------------------------------------------------------------------

async def rip_grep(
    args: List[str],
    target: str,
    abort_event: Optional[asyncio.Event] = None,
) -> List[str]:
    """Run ripgrep and return list of matching lines.

    Mirrors the TypeScript ripGrep() function including:
    - EAGAIN retry with single-threaded mode
    - RipgrepTimeoutError on timeout with no results
    - Partial results on timeout/buffer overflow
    """
    await _codesign_ripgrep_if_necessary()

    # Fire and forget test on first use
    asyncio.ensure_future(_test_ripgrep_on_first_use())

    async def _handle_result(
        rc: Optional[int],
        stdout: str,
        stderr: str,
        is_retry: bool,
    ) -> List[str]:
        # Success
        if rc == 0:
            return [
                line.rstrip("\r")
                for line in stdout.strip().split("\n")
                if line.strip()
            ]

        # Exit code 1 = no matches (success in ripgrep convention)
        if rc == 1:
            return []

        # Critical errors
        # On POSIX, ENOENT/EACCES/EPERM manifest as specific messages, not rc
        # but we handle rc-based critical codes here too
        if rc in (-2, -13):  # rough EACCES / EPERM equivalents
            raise RuntimeError(f"ripgrep critical error (rc={rc}): {stderr}")

        # EAGAIN retry
        if not is_retry and _is_eagain_error(stderr):
            _log_for_debugging("rg EAGAIN error detected, retrying with single-threaded mode (-j 1)")
            _log_event("tengu_ripgrep_eagain_retry", {})
            rc2, stdout2, stderr2 = await _rip_grep_raw(args, target, abort_event, single_thread=True)
            return await _handle_result(rc2, stdout2, stderr2, True)

        # Partial results on timeout/buffer overflow
        has_output = bool(stdout and stdout.strip())
        is_timeout = rc is None  # None means we killed it
        is_buffer_overflow = stdout_size_exceeded = (
            has_output and len(stdout) >= MAX_BUFFER_SIZE
        )

        lines: List[str] = []
        if has_output:
            lines = [
                line.rstrip("\r")
                for line in stdout.strip().split("\n")
                if line.strip()
            ]
            if lines and (is_timeout or is_buffer_overflow):
                lines = lines[:-1]

        _log_for_debugging(
            f"rg error (rc={rc}, stderr: {stderr}), {len(lines)} results"
        )

        if rc not in (2, None) and rc != "ABORT_ERR":
            try:
                _log_error(Exception(f"ripgrep exited with rc={rc}: {stderr}"))
            except Exception:
                pass

        if is_timeout and not lines:
            timeout_secs = 60 if _get_platform() == "wsl" else 20
            raise RipgrepTimeoutError(
                f"Ripgrep search timed out after {timeout_secs} seconds. "
                "The search may have matched files but did not complete in time. "
                "Try searching a more specific path or pattern.",
                lines,
            )

        return lines

    rc, stdout, stderr = await _rip_grep_raw(args, target, abort_event)
    return await _handle_result(rc, stdout, stderr, False)


# ---------------------------------------------------------------------------
# ripGrepStream — streaming variant
# ---------------------------------------------------------------------------

async def rip_grep_stream(
    args: List[str],
    target: str,
    abort_event: Optional[asyncio.Event],
    on_lines: Callable[[List[str]], None],
) -> None:
    """Stream ripgrep results as they arrive, calling on_lines per chunk."""
    await _codesign_ripgrep_if_necessary()
    rg_path, rg_args, argv0 = ripgrep_command()
    full_args = rg_args + args + [target]

    proc = await asyncio.create_subprocess_exec(
        rg_path, *full_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        stdin=asyncio.subprocess.DEVNULL,
    )

    def _strip_cr(line: str) -> str:
        return line[:-1] if line.endswith("\r") else line

    remainder = ""
    assert proc.stdout is not None
    try:
        while True:
            chunk = await proc.stdout.read(65536)
            if not chunk:
                break
            data = remainder + chunk.decode(errors="replace")
            lines = data.split("\n")
            remainder = lines.pop()
            if lines:
                on_lines([_strip_cr(l) for l in lines])
    except Exception:
        pass

    rc = await proc.wait()
    if abort_event and abort_event.is_set():
        return

    if rc == 0 or rc == 1:
        if remainder:
            on_lines([_strip_cr(remainder)])
    else:
        raise RuntimeError(f"ripgrep exited with code {rc}")


# ---------------------------------------------------------------------------
# ripGrepFileCount — streaming line count
# ---------------------------------------------------------------------------

async def _rip_grep_file_count(
    args: List[str],
    target: str,
    abort_event: Optional[asyncio.Event] = None,
) -> int:
    """Count newlines from rg --files without buffering the full output."""
    await _codesign_ripgrep_if_necessary()
    rg_path, rg_args, argv0 = ripgrep_command()
    full_args = rg_args + args + [target]

    proc = await asyncio.create_subprocess_exec(
        rg_path, *full_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        stdin=asyncio.subprocess.DEVNULL,
    )

    lines = 0
    assert proc.stdout is not None
    while True:
        chunk = await proc.stdout.read(65536)
        if not chunk:
            break
        lines += chunk.count(b"\n")

    rc = await proc.wait()
    if rc == 0 or rc == 1:
        return lines
    raise RuntimeError(f"rg --files exited {rc}")


# ---------------------------------------------------------------------------
# countFilesRoundedRg — privacy-rounded file count
# ---------------------------------------------------------------------------

import math

_file_count_cache: Dict[str, Optional[int]] = {}


async def count_files_rounded_rg(
    dir_path: str,
    abort_event: Optional[asyncio.Event] = None,
    ignore_patterns: Optional[List[str]] = None,
) -> Optional[int]:
    """Count files in *dir_path* rounded to the nearest power of 10."""
    if ignore_patterns is None:
        ignore_patterns = []

    # Skip home directory to avoid permission dialogs
    if os.path.realpath(dir_path) == os.path.realpath(os.path.expanduser("~")):
        return None

    cache_key = f"{dir_path}|{','.join(ignore_patterns)}"
    if cache_key in _file_count_cache:
        return _file_count_cache[cache_key]

    try:
        rg_args = ["--files", "--hidden"]
        for pattern in ignore_patterns:
            rg_args += ["--glob", f"!{pattern}"]

        count = await _rip_grep_file_count(rg_args, dir_path, abort_event)

        if count == 0:
            result: Optional[int] = 0
        else:
            magnitude = math.floor(math.log10(count))
            power = 10 ** magnitude
            result = round(count / power) * power

        _file_count_cache[cache_key] = result
        return result
    except Exception as exc:
        if getattr(exc, "name", None) != "AbortError":
            _log_error(exc)
        return None


# ---------------------------------------------------------------------------
# getRipgrepStatus
# ---------------------------------------------------------------------------

_ripgrep_status: Optional[Dict[str, Any]] = None


def get_ripgrep_status() -> Dict[str, Any]:
    """Return current ripgrep mode/path/working status."""
    cfg = get_ripgrep_config()
    return {
        "mode": cfg.mode,
        "path": cfg.command,
        "working": _ripgrep_status["working"] if _ripgrep_status else None,
    }


# ---------------------------------------------------------------------------
# testRipgrepOnFirstUse (memoized)
# ---------------------------------------------------------------------------

_test_ripgrep_done = False


async def _test_ripgrep_on_first_use() -> None:
    global _ripgrep_status, _test_ripgrep_done
    if _test_ripgrep_done or _ripgrep_status is not None:
        return
    _test_ripgrep_done = True

    cfg = get_ripgrep_config()
    try:
        rc, stdout, _ = _exec_file_no_throw(
            cfg.command, cfg.args + ["--version"], timeout=5.0
        )
        working = rc == 0 and bool(stdout) and stdout.startswith("ripgrep ")
        _ripgrep_status = {
            "working": working,
            "last_tested": time.time(),
            "config": cfg,
        }
        _log_for_debugging(
            f"Ripgrep first use test: {'PASSED' if working else 'FAILED'} "
            f"(mode={cfg.mode}, path={cfg.command})"
        )
        _log_event("tengu_ripgrep_availability", {
            "working": 1 if working else 0,
            "using_system": 1 if cfg.mode == "system" else 0,
        })
    except Exception as exc:
        _ripgrep_status = {"working": False, "last_tested": time.time(), "config": cfg}
        _log_error(exc)


# ---------------------------------------------------------------------------
# Public search helpers (high-level API, compatible with existing Python code)
# ---------------------------------------------------------------------------

@dataclass
class RipgrepMatch:
    """A single line match from ripgrep output."""
    file: str
    line_number: int
    line: str


async def rg_search(
    pattern: str,
    paths: List[str],
    *,
    case_sensitive: bool = False,
    whole_word: bool = False,
    fixed_strings: bool = False,
    include_glob: Optional[str] = None,
    exclude_glob: Optional[str] = None,
    max_count: Optional[int] = None,
    context_lines: int = 0,
    extra_args: Optional[List[str]] = None,
) -> List[RipgrepMatch]:
    """Run ripgrep and return a list of RipgrepMatch objects.

    Args:
        pattern: The search pattern (regex or literal).
        paths: Directories or files to search.
        case_sensitive: Enable case-sensitive matching.
        whole_word: Match whole words only.
        fixed_strings: Treat pattern as a literal string.
        include_glob: Only search files matching this glob.
        exclude_glob: Exclude files matching this glob.
        max_count: Stop after this many matches.
        context_lines: Number of context lines around each match.
        extra_args: Additional raw rg arguments.
    """
    rg_args: List[str] = []

    if not case_sensitive:
        rg_args.append("--ignore-case")
    if whole_word:
        rg_args.append("--word-regexp")
    if fixed_strings:
        rg_args.append("--fixed-strings")
    if include_glob:
        rg_args += ["--glob", include_glob]
    if exclude_glob:
        rg_args += ["--glob", f"!{exclude_glob}"]
    if max_count is not None:
        rg_args += ["--max-count", str(max_count)]
    if context_lines > 0:
        rg_args += ["--context", str(context_lines)]
    if extra_args:
        rg_args += extra_args

    rg_args += ["--line-number", "--with-filename", "--color", "never"]
    rg_args += ["--", pattern]

    # Combine all paths into a single target dir or use multiple by running per-path
    if not paths:
        return []

    all_matches: List[RipgrepMatch] = []
    for target in paths:
        raw_lines = await rip_grep(rg_args, target)
        for raw_line in raw_lines:
            parsed = _parse_rg_line(raw_line)
            if parsed:
                all_matches.append(parsed)

    return all_matches


def rg_search_sync(
    pattern: str,
    paths: List[str],
    **kwargs: Any,
) -> List[RipgrepMatch]:
    """Synchronous wrapper around :func:`rg_search`."""
    return asyncio.run(rg_search(pattern, paths, **kwargs))


def _parse_rg_line(line: str) -> Optional[RipgrepMatch]:
    """Parse a ``file:lineno:content`` line from ripgrep output."""
    parts = line.split(":", 2)
    if len(parts) < 3:
        return None
    try:
        return RipgrepMatch(
            file=parts[0],
            line_number=int(parts[1]),
            line=parts[2],
        )
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Count characters in a string
# ---------------------------------------------------------------------------

def count_char_in_string(s: str, char: str) -> int:
    """Count occurrences of *char* in *s*."""
    return s.count(char)
