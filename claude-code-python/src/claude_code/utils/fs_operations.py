"""
fs_operations.py - Python port of fsOperations.ts
Source: claude-code-analysis/claude-code-source/utils/fsOperations.ts

Core functionality:
- File system operations wrapper (read/write, existence checks, directory ops,
  permission handling, symlink resolution, etc.)
- Provides FsOperations protocol and a default NodeFsOperations-equivalent
  (PythonFsOperations) using the standard os / pathlib / io modules.
"""

import asyncio
import io
import os
import shutil
import stat
from pathlib import Path
from typing import (
    AsyncGenerator,
    Callable,
    Dict,
    List,
    NamedTuple,
    Optional,
    Protocol,
    Tuple,
    Union,
)


# ---------------------------------------------------------------------------
# Simple stat-like result dataclass
# ---------------------------------------------------------------------------

class StatResult(NamedTuple):
    """A thin wrapper around os.stat_result to mirror the Node.js fs.Stats interface."""
    st_mode: int
    st_ino: int
    st_dev: int
    st_nlink: int
    st_uid: int
    st_gid: int
    st_size: int
    st_atime: float
    st_mtime: float
    st_ctime: float
    is_lstat: bool = False  # True when obtained via lstat (not stat)

    def is_file(self) -> bool:
        return stat.S_ISREG(self.st_mode)

    def is_dir(self) -> bool:
        return stat.S_ISDIR(self.st_mode)

    def is_symbolic_link(self) -> bool:
        return self.is_lstat and stat.S_ISLNK(self.st_mode)

    def is_fifo(self) -> bool:
        return stat.S_ISFIFO(self.st_mode)

    def is_socket(self) -> bool:
        return stat.S_ISSOCK(self.st_mode)

    def is_block_device(self) -> bool:
        return stat.S_ISBLK(self.st_mode)

    def is_character_device(self) -> bool:
        return stat.S_ISCHR(self.st_mode)

    @classmethod
    def from_os_stat(cls, s: os.stat_result, is_symlink: bool = False) -> "StatResult":
        return cls(
            st_mode=s.st_mode,
            st_ino=s.st_ino,
            st_dev=s.st_dev,
            st_nlink=s.st_nlink,
            st_uid=s.st_uid,
            st_gid=s.st_gid,
            st_size=s.st_size,
            st_atime=s.st_atime,
            st_mtime=s.st_mtime,
            st_ctime=s.st_ctime,
            is_lstat=is_symlink,
        )


class DirEntry(NamedTuple):
    """Mirrors Node.js fs.Dirent."""
    name: str
    path: str  # full path
    d_type: int = 0  # os.DT_* constant or stat mode

    def is_file(self) -> bool:
        return os.path.isfile(self.path)

    def is_dir(self) -> bool:
        return os.path.isdir(self.path)

    def is_symlink(self) -> bool:
        return os.path.islink(self.path)


class ReadRangeResult(NamedTuple):
    buffer: bytes
    bytes_read: int


class ReadFileRangeResult(NamedTuple):
    content: str
    bytes_read: int
    bytes_total: int


# ---------------------------------------------------------------------------
# FsOperations Protocol
# ---------------------------------------------------------------------------

class FsOperations(Protocol):
    """
    Simplified filesystem operations interface, mirroring the TypeScript FsOperations type.
    Provides a subset of commonly used sync/async operations with type safety.
    """

    def cwd(self) -> str: ...
    def exists_sync(self, path: str) -> bool: ...
    def stat_sync(self, path: str) -> StatResult: ...
    def lstat_sync(self, path: str) -> StatResult: ...
    def readdir_sync(self, path: str) -> List[DirEntry]: ...
    def readdir_string_sync(self, path: str) -> List[str]: ...
    def is_dir_empty_sync(self, path: str) -> bool: ...
    def read_file_sync(self, path: str, encoding: str = "utf-8") -> str: ...
    def read_file_bytes_sync(self, path: str) -> bytes: ...
    def read_sync(self, path: str, length: int) -> ReadRangeResult: ...
    def append_file_sync(self, path: str, data: str, mode: Optional[int] = None) -> None: ...
    def copy_file_sync(self, src: str, dest: str) -> None: ...
    def unlink_sync(self, path: str) -> None: ...
    def rename_sync(self, old_path: str, new_path: str) -> None: ...
    def link_sync(self, target: str, path: str) -> None: ...
    def symlink_sync(self, target: str, path: str) -> None: ...
    def readlink_sync(self, path: str) -> str: ...
    def realpath_sync(self, path: str) -> str: ...
    def mkdir_sync(self, path: str, mode: Optional[int] = None) -> None: ...
    def rmdir_sync(self, path: str) -> None: ...
    def rm_sync(self, path: str, recursive: bool = False, force: bool = False) -> None: ...

    # Async variants
    async def stat(self, path: str) -> StatResult: ...
    async def readdir(self, path: str) -> List[DirEntry]: ...
    async def unlink(self, path: str) -> None: ...
    async def rmdir(self, path: str) -> None: ...
    async def rm(self, path: str, recursive: bool = False, force: bool = False) -> None: ...
    async def mkdir(self, path: str, mode: Optional[int] = None) -> None: ...
    async def read_file(self, path: str, encoding: str = "utf-8") -> str: ...
    async def rename(self, old_path: str, new_path: str) -> None: ...
    async def read_file_bytes(self, path: str, max_bytes: Optional[int] = None) -> bytes: ...


# ---------------------------------------------------------------------------
# Default Python implementation (mirrors NodeFsOperations)
# ---------------------------------------------------------------------------

class PythonFsOperations:
    """
    Default filesystem implementation using Python's os / pathlib / io modules.
    Mirrors the NodeFsOperations object from the TypeScript source.
    """

    # ---- Sync helpers ----

    def cwd(self) -> str:
        return os.getcwd()

    def exists_sync(self, path: str) -> bool:
        return os.path.exists(path)

    def stat_sync(self, path: str) -> StatResult:
        return StatResult.from_os_stat(os.stat(path))

    def lstat_sync(self, path: str) -> StatResult:
        s = os.lstat(path)
        is_sym = stat.S_ISLNK(s.st_mode)
        return StatResult.from_os_stat(s, is_symlink=is_sym)

    def readdir_sync(self, path: str) -> List[DirEntry]:
        entries = []
        with os.scandir(path) as it:
            for entry in it:
                entries.append(DirEntry(name=entry.name, path=entry.path, _d_type=0))
        return entries

    def readdir_string_sync(self, path: str) -> List[str]:
        return os.listdir(path)

    def is_dir_empty_sync(self, path: str) -> bool:
        return len(os.listdir(path)) == 0

    def read_file_sync(self, path: str, encoding: str = "utf-8") -> str:
        with open(path, "r", encoding=encoding) as f:
            return f.read()

    def read_file_bytes_sync(self, path: str) -> bytes:
        with open(path, "rb") as f:
            return f.read()

    def read_sync(self, path: str, length: int) -> ReadRangeResult:
        with open(path, "rb") as f:
            data = f.read(length)
        return ReadRangeResult(buffer=data, bytes_read=len(data))

    def append_file_sync(
        self, path: str, data: str, mode: Optional[int] = None
    ) -> None:
        if mode is not None:
            # Atomic create-with-mode for new files; fall back to normal append if exists
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
                try:
                    os.write(fd, data.encode("utf-8"))
                finally:
                    os.close(fd)
                return
            except FileExistsError:
                pass
        with open(path, "a", encoding="utf-8") as f:
            f.write(data)

    def copy_file_sync(self, src: str, dest: str) -> None:
        shutil.copy2(src, dest)

    def unlink_sync(self, path: str) -> None:
        os.unlink(path)

    def rename_sync(self, old_path: str, new_path: str) -> None:
        os.rename(old_path, new_path)

    def link_sync(self, target: str, path: str) -> None:
        os.link(target, path)

    def symlink_sync(self, target: str, path: str) -> None:
        os.symlink(target, path)

    def readlink_sync(self, path: str) -> str:
        return os.readlink(path)

    def realpath_sync(self, path: str) -> str:
        return os.path.realpath(path)

    def mkdir_sync(self, path: str, mode: Optional[int] = None) -> None:
        kwargs: Dict = {"exist_ok": True}
        if mode is not None:
            kwargs["mode"] = mode
        os.makedirs(path, **kwargs)

    def rmdir_sync(self, path: str) -> None:
        os.rmdir(path)

    def rm_sync(
        self, path: str, recursive: bool = False, force: bool = False
    ) -> None:
        try:
            if recursive:
                shutil.rmtree(path)
            else:
                os.remove(path)
        except FileNotFoundError:
            if not force:
                raise

    # ---- Async variants (run sync ops in thread pool) ----

    async def stat(self, path: str) -> StatResult:
        return await asyncio.get_event_loop().run_in_executor(
            None, self.stat_sync, path
        )

    async def readdir(self, path: str) -> List[DirEntry]:
        return await asyncio.get_event_loop().run_in_executor(
            None, self.readdir_sync, path
        )

    async def unlink(self, path: str) -> None:
        await asyncio.get_event_loop().run_in_executor(None, self.unlink_sync, path)

    async def rmdir(self, path: str) -> None:
        await asyncio.get_event_loop().run_in_executor(None, self.rmdir_sync, path)

    async def rm(
        self, path: str, recursive: bool = False, force: bool = False
    ) -> None:
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: self.rm_sync(path, recursive=recursive, force=force)
        )

    async def mkdir(self, path: str, mode: Optional[int] = None) -> None:
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: self.mkdir_sync(path, mode=mode)
        )

    async def read_file(self, path: str, encoding: str = "utf-8") -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self.read_file_sync(path, encoding=encoding)
        )

    async def rename(self, old_path: str, new_path: str) -> None:
        await asyncio.get_event_loop().run_in_executor(
            None, self.rename_sync, old_path, new_path
        )

    async def read_file_bytes(
        self, path: str, max_bytes: Optional[int] = None
    ) -> bytes:
        loop = asyncio.get_event_loop()
        if max_bytes is None:
            return await loop.run_in_executor(None, self.read_file_bytes_sync, path)

        def _read_partial() -> bytes:
            with open(path, "rb") as f:
                return f.read(max_bytes)

        return await loop.run_in_executor(None, _read_partial)


# Singleton default implementation
_default_fs: PythonFsOperations = PythonFsOperations()


def get_fs_implementation() -> PythonFsOperations:
    """Get the currently active filesystem implementation."""
    return _default_fs


def set_fs_implementation(implementation: PythonFsOperations) -> None:
    """Override the filesystem implementation."""
    global _default_fs
    _default_fs = implementation


def set_original_fs_implementation() -> None:
    """Reset the filesystem implementation to the default Python implementation."""
    global _default_fs
    _default_fs = PythonFsOperations()


# ---------------------------------------------------------------------------
# safe_resolve_path
# ---------------------------------------------------------------------------

def safe_resolve_path(
    fs: PythonFsOperations,
    file_path: str,
) -> Tuple[str, bool, bool]:
    """
    Safely resolves a file path, handling symlinks and errors gracefully.

    Returns (resolved_path, is_symlink, is_canonical).

    Error handling:
    - If the file doesn't exist, returns the original path
    - If symlink resolution fails (broken symlink, permission denied, circular),
      returns the original path and marks it as not a symlink
    """
    # Block UNC paths
    if file_path.startswith("//") or file_path.startswith("\\\\"):
        return file_path, False, False

    try:
        st = fs.lstat_sync(file_path)
        if st.is_fifo() or st.is_socket() or st.is_character_device() or st.is_block_device():
            return file_path, False, False

        resolved = fs.realpath_sync(file_path)
        return resolved, resolved != file_path, True
    except Exception:
        return file_path, False, False


# ---------------------------------------------------------------------------
# is_duplicate_path
# ---------------------------------------------------------------------------

def is_duplicate_path(
    fs: PythonFsOperations,
    file_path: str,
    loaded_paths: set,
) -> bool:
    """
    Check if a file path is a duplicate and should be skipped.
    Resolves symlinks to detect duplicates pointing to the same file.
    If not a duplicate, adds the resolved path to loaded_paths.

    Returns True if the file should be skipped (is duplicate).
    """
    resolved_path, _, _ = safe_resolve_path(fs, file_path)
    if resolved_path in loaded_paths:
        return True
    loaded_paths.add(resolved_path)
    return False


# ---------------------------------------------------------------------------
# resolve_deepest_existing_ancestor_sync
# ---------------------------------------------------------------------------

def resolve_deepest_existing_ancestor_sync(
    fs: PythonFsOperations,
    absolute_path: str,
) -> Optional[str]:
    """
    Resolve the deepest existing ancestor of a path via realpath, walking
    up until it succeeds. Detects dangling symlinks via lstat.

    Returns the resolved absolute path with non-existent tail segments
    rejoined, or None if no symlink was found in any existing ancestor.
    """
    dir_path = absolute_path
    segments: List[str] = []

    while True:
        parent = os.path.dirname(dir_path)
        if parent == dir_path:
            break

        try:
            st = fs.lstat_sync(dir_path)
        except Exception:
            segments.insert(0, os.path.basename(dir_path))
            dir_path = parent
            continue

        if st.is_symbolic_link():
            # Found a symlink (live or dangling)
            try:
                resolved = fs.realpath_sync(dir_path)
                if segments:
                    return os.path.join(resolved, *segments)
                return resolved
            except Exception:
                # Dangling: realpath failed but lstat saw the link entry
                target = fs.readlink_sync(dir_path)
                abs_target = (
                    target
                    if os.path.isabs(target)
                    else os.path.normpath(os.path.join(os.path.dirname(dir_path), target))
                )
                if segments:
                    return os.path.join(abs_target, *segments)
                return abs_target

        # Existing non-symlink component
        try:
            resolved = fs.realpath_sync(dir_path)
            if resolved != dir_path:
                if segments:
                    return os.path.join(resolved, *segments)
                return resolved
        except Exception:
            pass
        return None

    return None


# ---------------------------------------------------------------------------
# get_paths_for_permission_check
# ---------------------------------------------------------------------------

def get_paths_for_permission_check(input_path: str) -> List[str]:
    """
    Gets all paths that should be checked for permissions.
    Includes the original path, all intermediate symlink targets in the chain,
    and the final resolved path.
    """
    path = input_path

    # Expand tilde notation
    if path == "~":
        path = os.path.expanduser("~")
    elif path.startswith("~/"):
        path = os.path.expanduser(path)

    path_set: List[str] = [path]
    path_seen: set = {path}

    fs_impl = get_fs_implementation()

    # Block UNC paths
    if path.startswith("//") or path.startswith("\\\\"):
        return path_set

    try:
        current_path = path
        visited: set = set()
        max_depth = 40  # SYMLOOP_MAX

        for _ in range(max_depth):
            if current_path in visited:
                break
            visited.add(current_path)

            if not fs_impl.exists_sync(current_path):
                # Path doesn't exist or is a dangling symlink
                if current_path == path:
                    resolved = resolve_deepest_existing_ancestor_sync(fs_impl, path)
                    if resolved is not None and resolved not in path_seen:
                        path_set.append(resolved)
                        path_seen.add(resolved)
                break

            try:
                st = fs_impl.lstat_sync(current_path)
            except Exception:
                break

            if st.is_fifo() or st.is_socket() or st.is_character_device() or st.is_block_device():
                break

            if not st.is_symbolic_link():
                break

            # Get the immediate symlink target
            target = fs_impl.readlink_sync(current_path)
            abs_target = (
                target
                if os.path.isabs(target)
                else os.path.normpath(os.path.join(os.path.dirname(current_path), target))
            )

            if abs_target not in path_seen:
                path_set.append(abs_target)
                path_seen.add(abs_target)
            current_path = abs_target

    except Exception:
        pass

    # Also add the final resolved path for completeness
    resolved_path, is_symlink, _ = safe_resolve_path(fs_impl, path)
    if is_symlink and resolved_path != path and resolved_path not in path_seen:
        path_set.append(resolved_path)
        path_seen.add(resolved_path)

    return path_set


# ---------------------------------------------------------------------------
# Ranged file reading helpers
# ---------------------------------------------------------------------------

async def read_file_range(
    path: str,
    offset: int,
    max_bytes: int,
) -> Optional[ReadFileRangeResult]:
    """
    Read up to `max_bytes` from a file starting at `offset`.
    Returns None if the file is smaller than the offset.
    """
    loop = asyncio.get_event_loop()

    def _read() -> Optional[ReadFileRangeResult]:
        size = os.path.getsize(path)
        if size <= offset:
            return None
        bytes_to_read = min(size - offset, max_bytes)
        with open(path, "rb") as f:
            f.seek(offset)
            data = f.read(bytes_to_read)
        return ReadFileRangeResult(
            content=data.decode("utf-8", errors="replace"),
            bytes_read=len(data),
            bytes_total=size,
        )

    return await loop.run_in_executor(None, _read)


async def tail_file(path: str, max_bytes: int) -> ReadFileRangeResult:
    """
    Read the last `max_bytes` of a file.
    Returns the whole file if it's smaller than max_bytes.
    """
    loop = asyncio.get_event_loop()

    def _tail() -> ReadFileRangeResult:
        size = os.path.getsize(path)
        if size == 0:
            return ReadFileRangeResult(content="", bytes_read=0, bytes_total=0)
        offset = max(0, size - max_bytes)
        bytes_to_read = size - offset
        with open(path, "rb") as f:
            f.seek(offset)
            data = f.read(bytes_to_read)
        return ReadFileRangeResult(
            content=data.decode("utf-8", errors="replace"),
            bytes_read=len(data),
            bytes_total=size,
        )

    return await loop.run_in_executor(None, _tail)


async def read_lines_reverse(
    path: str,
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields lines from a file in reverse order.
    Reads the file backwards in chunks to avoid loading entire file into memory.
    """
    CHUNK_SIZE = 1024 * 4

    loop = asyncio.get_event_loop()
    size = await loop.run_in_executor(None, os.path.getsize, path)

    def _read_chunk(f: io.RawIOBase, pos: int, chunk_size: int) -> bytes:
        f.seek(pos)
        return f.read(chunk_size)

    with open(path, "rb") as fh:
        position = size
        remainder = b""

        while position > 0:
            current_chunk_size = min(CHUNK_SIZE, position)
            position -= current_chunk_size
            chunk = await loop.run_in_executor(None, _read_chunk, fh, position, current_chunk_size)
            combined = chunk + remainder

            first_newline = combined.find(b"\n")
            if first_newline == -1:
                remainder = combined
                continue

            remainder = combined[:first_newline]
            lines = combined[first_newline + 1:].decode("utf-8", errors="replace").split("\n")

            for line in reversed(lines):
                if line:
                    yield line

        if remainder:
            yield remainder.decode("utf-8", errors="replace")
