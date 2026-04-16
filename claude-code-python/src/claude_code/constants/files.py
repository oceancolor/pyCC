"""
File extension & binary detection utilities
原始 TS: src/constants/files.ts
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Binary file extensions to skip for text-based operations
# ---------------------------------------------------------------------------

BINARY_EXTENSIONS: frozenset[str] = frozenset({
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico",
    ".webp", ".tiff", ".tif",
    # Videos
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".wmv",
    ".flv", ".m4v", ".mpeg", ".mpg",
    # Audio
    ".mp3", ".wav", ".ogg", ".flac", ".aac",
    ".m4a", ".wma", ".aiff", ".opus",
    # Archives
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".xz", ".z", ".tgz", ".iso",
    # Executables/binaries
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".o", ".a", ".obj", ".lib", ".app",
    ".msi", ".deb", ".rpm",
    # Documents (PDF is here; FileReadTool excludes it at the call site)
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".odt", ".ods", ".odp",
    # Fonts
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    # Bytecode / VM artifacts
    ".pyc", ".pyo", ".class", ".jar", ".war", ".ear",
    ".node", ".wasm", ".rlib",
    # Database files
    ".sqlite", ".sqlite3", ".db", ".mdb", ".idx",
    # Design / 3D
    ".psd", ".ai", ".eps", ".sketch", ".fig",
    ".xd", ".blend", ".3ds", ".max",
    # Flash
    ".swf", ".fla",
    # Lock/profiling data
    ".lockb", ".dat", ".data",
})

_BINARY_CHECK_SIZE = 8192


def has_binary_extension(file_path: str) -> bool:
    """Check if a file path has a binary extension."""
    ext = Path(file_path).suffix.lower()
    return ext in BINARY_EXTENSIONS


def is_binary_content(data: bytes) -> bool:
    """
    Check if a buffer contains binary content by looking for null bytes
    or a high proportion of non-printable characters.
    """
    check_size = min(len(data), _BINARY_CHECK_SIZE)
    if check_size == 0:
        return False

    non_printable = 0
    for i in range(check_size):
        byte = data[i]
        # Null byte is a strong indicator of binary
        if byte == 0:
            return True
        # Count non-printable, non-whitespace bytes
        # Printable ASCII: 32-126, plus common whitespace (9=tab, 10=LF, 13=CR)
        if byte < 32 and byte not in (9, 10, 13):
            non_printable += 1

    return (non_printable / check_size) > 0.1
