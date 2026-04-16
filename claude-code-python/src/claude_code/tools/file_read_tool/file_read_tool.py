"""
FileReadTool — reads text, images, notebooks, PDFs.
Ported from FileReadTool/FileReadTool.ts (1183 lines → core logic).

New in this version (vs the 133-line partial implementation):
  * PDF file support via pdfminer.six (graceful fallback if not installed)
  * Image file support with base64 encoding + MIME detection
  * Jupyter notebook support (.ipynb)
  * Large-file segmented reading (offset + limit)
  * cat-n style line-number formatting
  * Binary file detection (extension + content sniff)
  * File-type routing (text / image / notebook / pdf)
  * macOS screenshot path alternate-space resolution
  * Blocked device path protection
  * Token-count guard (size-based estimate, no API call needed)
"""
from __future__ import annotations

import base64
import json
import os
import re
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from claude_code.tools.file_read_tool.limits import get_default_file_reading_limits
from claude_code.tools.file_read_tool.prompt import (
    FILE_READ_TOOL_NAME,
    MAX_LINES_TO_READ,
    FILE_UNCHANGED_STUB,
)

# ---------------------------------------------------------------------------
# Constants (mirroring FileReadTool.ts)
# ---------------------------------------------------------------------------

BLOCKED_DEVICE_PATHS = {
    "/dev/zero", "/dev/random", "/dev/urandom", "/dev/full",
    "/dev/stdin", "/dev/tty", "/dev/console",
    "/dev/stdout", "/dev/stderr",
    "/dev/fd/0", "/dev/fd/1", "/dev/fd/2",
}

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

PDF_EXTENSIONS = {"pdf"}

# Narrow no-break space used by some macOS screenshot filenames
_THIN_SPACE = "\u202F"

# Max size we'll attempt to read in one call (mirrors TS default)
_DEFAULT_MAX_SIZE_BYTES = 256 * 1024  # 256 KB

# Rough token-count estimate: 4 chars ≈ 1 token
_CHARS_PER_TOKEN = 4

# Binary-sniff window
_BINARY_SNIFF_BYTES = 8192

# PDF constants (mirrors TS constants/apiLimits.ts)
PDF_MAX_PAGES_PER_READ = 20
PDF_AT_MENTION_INLINE_THRESHOLD = 50  # pages


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class MaxFileReadTokenExceededError(Exception):
    """Raised when file content exceeds the token budget."""

    def __init__(self, token_count: int, max_tokens: int):
        super().__init__(
            f"File content ({token_count} tokens) exceeds maximum allowed tokens "
            f"({max_tokens}). Use offset and limit parameters to read specific "
            "portions of the file, or search for specific content instead of "
            "reading the whole file."
        )
        self.token_count = token_count
        self.max_tokens = max_tokens


# ---------------------------------------------------------------------------
# Path / device helpers
# ---------------------------------------------------------------------------

def is_blocked_device_path(path: str) -> bool:
    """True for device files that would hang on read (infinite output / stdin)."""
    if path in BLOCKED_DEVICE_PATHS:
        return True
    # /proc/self/fd/0-2 and /proc/<pid>/fd/0-2 are Linux aliases for stdio
    if re.match(r"^/proc/.+/fd/[012]$", path):
        return True
    return False


def _get_alternate_screenshot_path(file_path: str) -> Optional[str]:
    """
    macOS screenshots may have a thin-space (U+202F) or regular space before
    AM/PM depending on the OS version.  Return the alternate path to try, or
    None if this doesn't look like a screenshot filename.
    """
    filename = os.path.basename(file_path)
    m = re.match(r"^(.+)([ \u202F])(AM|PM)(\.png)$", filename)
    if not m:
        return None
    current_space = m.group(2)
    alt_space = " " if current_space == _THIN_SPACE else _THIN_SPACE
    alt_filename = filename.replace(
        f"{current_space}{m.group(3)}{m.group(4)}",
        f"{alt_space}{m.group(3)}{m.group(4)}",
    )
    return os.path.join(os.path.dirname(file_path), alt_filename)


# ---------------------------------------------------------------------------
# Binary detection
# ---------------------------------------------------------------------------

_BINARY_EXTENSIONS: frozenset[str] = frozenset({
    # executables / compiled
    "exe", "dll", "so", "dylib", "bin", "o", "a", "obj", "lib", "app",
    "msi", "deb", "rpm", "wasm", "class", "jar", "war", "ear", "pyc", "pyo",
    # archives
    "zip", "tar", "gz", "bz2", "7z", "rar", "xz", "z", "tgz", "iso",
    # audio/video
    "mp4", "mov", "avi", "mkv", "webm", "wmv", "flv", "m4v", "mpeg", "mpg",
    "mp3", "wav", "ogg", "flac", "aac", "m4a", "wma", "aiff", "opus",
    # images that we don't handle natively
    "bmp", "ico", "tiff", "tif",
    # documents (PDF is excluded from this set — handled natively)
    "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp",
    # fonts
    "ttf", "otf", "woff", "woff2", "eot",
    # db / lock
    "sqlite", "sqlite3", "db", "mdb", "idx", "lockb",
    # design
    "psd", "ai", "eps", "sketch", "fig", "blend", "3ds", "max",
    # flash
    "swf", "fla",
})


def has_binary_extension(file_path: str) -> bool:
    """True if the path has an extension known to be binary (excludes PDF/images)."""
    ext = Path(file_path).suffix.lstrip(".").lower()
    return ext in _BINARY_EXTENSIONS


def is_binary_content(data: bytes) -> bool:
    """Sniff a byte buffer: True if it contains a NUL byte (binary heuristic)."""
    return b"\x00" in data[:_BINARY_SNIFF_BYTES]


# ---------------------------------------------------------------------------
# MIME type helpers
# ---------------------------------------------------------------------------

_MIME_MAP: Dict[str, str] = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}


def _mime_for_image(ext: str) -> str:
    return _MIME_MAP.get(ext.lower(), "image/png")


def _detect_image_mime_from_bytes(data: bytes) -> str:
    """Detect image MIME type from magic bytes (best-effort)."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


# ---------------------------------------------------------------------------
# PDF page-range parsing (mirrors pdfUtils.ts parsePDFPageRange)
# ---------------------------------------------------------------------------

def parse_pdf_page_range(pages: str) -> Optional[Dict[str, Any]]:
    """
    Parse a PDF page-range string.  Formats: "3", "1-5", "10-20".
    Returns {'first_page': int, 'last_page': int | float('inf')} or None.
    """
    pages = pages.strip()
    if re.fullmatch(r"\d+", pages):
        p = int(pages)
        return {"first_page": p, "last_page": p}
    m = re.fullmatch(r"(\d+)-(\d+)", pages)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a > b:
            return None
        return {"first_page": a, "last_page": b}
    return None


# ---------------------------------------------------------------------------
# Token estimation (rough — avoids API calls)
# ---------------------------------------------------------------------------

def _estimate_tokens(content: str, ext: str = "") -> int:
    """Rough token estimate: len / 4 chars per token (conservative)."""
    return max(1, len(content) // _CHARS_PER_TOKEN)


def _check_token_limit(content: str, ext: str, max_tokens: int) -> None:
    """Raise MaxFileReadTokenExceededError if content exceeds budget."""
    estimate = _estimate_tokens(content, ext)
    if estimate > max_tokens:
        raise MaxFileReadTokenExceededError(estimate, max_tokens)


# ---------------------------------------------------------------------------
# Text reading (with offset / limit + cat -n line numbers)
# ---------------------------------------------------------------------------

def _read_text_ranged(
    path: str,
    offset: Optional[int],
    limit: Optional[int],
    max_tokens: int,
    ext: str,
) -> dict:
    """
    Read a text file with optional line-range selection.

    offset: 1-based first line to read (default 1)
    limit:  max number of lines to read (default MAX_LINES_TO_READ)

    Returns same shape as the TS 'text' output type.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        all_lines = fh.readlines()

    total_lines = len(all_lines)
    start_idx = max(0, (offset or 1) - 1)  # 0-based
    end_idx = min(total_lines, start_idx + (limit or MAX_LINES_TO_READ))
    selected = all_lines[start_idx:end_idx]

    # cat -n style: "   1\t<line>"
    content = "".join(
        f"{start_idx + i + 1}\t{line}" for i, line in enumerate(selected)
    )

    _check_token_limit(content, ext, max_tokens)

    return {
        "type": "text",
        "file": {
            "file_path": path,
            "content": content,
            "num_lines": len(selected),
            "start_line": start_idx + 1,
            "total_lines": total_lines,
        },
        # Flat accessors kept for test & backward compatibility
        "text": content,
        "file_path": path,
        "num_lines": len(selected),
        "start_line": start_idx + 1,
        "total_lines": total_lines,
    }


# ---------------------------------------------------------------------------
# Image reading
# ---------------------------------------------------------------------------

def _read_image(path: str) -> dict:
    """Read an image file and return base64-encoded data with MIME type."""
    ext = Path(path).suffix.lstrip(".").lower()
    with open(path, "rb") as fh:
        raw = fh.read()
    if len(raw) == 0:
        raise ValueError(f"Image file is empty: {path}")
    mime = _detect_image_mime_from_bytes(raw) if ext not in _MIME_MAP else _mime_for_image(ext)
    encoded = base64.b64encode(raw).decode("ascii")
    return {
        "type": "image",
        "file": {
            "base64": encoded,
            "type": mime,
            "original_size": len(raw),
        },
        # Flat accessors
        "text": f"[Image: {path}]",
        "base64": encoded,
        "mime_type": mime,
        "original_size": len(raw),
        "file_path": path,
    }


# ---------------------------------------------------------------------------
# Jupyter notebook reading
# ---------------------------------------------------------------------------

def _read_notebook(path: str) -> dict:
    """
    Parse a Jupyter notebook (.ipynb) and return cells as structured data.
    Mirrors readNotebook / mapNotebookCellsToToolResult from the TS port.
    """
    with open(path, "r", encoding="utf-8") as fh:
        nb = json.load(fh)

    cells_raw = nb.get("cells", [])
    cells: List[Dict[str, Any]] = []
    for cell in cells_raw:
        cell_type = cell.get("cell_type", "code")
        source_lines = cell.get("source", [])
        source = "".join(source_lines) if isinstance(source_lines, list) else str(source_lines)
        outputs = cell.get("outputs", [])
        # Summarise outputs as plain text where possible
        output_texts: List[str] = []
        for out in outputs:
            if out.get("output_type") == "stream":
                out_text = "".join(out.get("text", []))
                output_texts.append(out_text)
            elif out.get("output_type") in ("execute_result", "display_data"):
                data = out.get("data", {})
                if "text/plain" in data:
                    output_texts.append("".join(data["text/plain"]))
        cells.append({
            "cell_type": cell_type,
            "source": source,
            "outputs": output_texts,
        })

    # Human-readable text representation
    parts: List[str] = []
    for c in cells:
        header = f"[{c['cell_type']}]"
        parts.append(header)
        if c["source"].strip():
            parts.append(c["source"])
        for o in c["outputs"]:
            if o.strip():
                parts.append(f"# Output:\n{o}")
        parts.append("")
    text = "\n".join(parts)

    return {
        "type": "notebook",
        "file": {
            "file_path": path,
            "cells": cells,
        },
        # Flat accessors
        "text": text,
        "file_path": path,
        "cells": cells,
    }


# ---------------------------------------------------------------------------
# PDF reading
# ---------------------------------------------------------------------------

def _read_pdf_with_pdfminer(path: str, pages: Optional[str] = None) -> str:
    """Extract text from a PDF using pdfminer.six (optional dependency)."""
    from pdfminer.high_level import extract_text  # type: ignore[import]
    from pdfminer.pdfpage import PDFPage  # type: ignore[import]

    if pages:
        parsed = parse_pdf_page_range(pages)
        if parsed:
            # pdfminer page_numbers is 0-based
            first = parsed["first_page"] - 1
            last = parsed["last_page"]
            page_numbers = list(range(first, last)) if last != float("inf") else None
            return extract_text(path, page_numbers=page_numbers)
    return extract_text(path)


def _read_pdf_base64(path: str) -> Tuple[str, int]:
    """Return (base64_content, original_size) for a PDF file."""
    with open(path, "rb") as fh:
        raw = fh.read()
    return base64.b64encode(raw).decode("ascii"), len(raw)


def _read_pdf(path: str, pages: Optional[str] = None, max_tokens: int = 25_000) -> dict:
    """
    Read a PDF file.

    Strategy (mirrors TS fallback chain):
      1. Try pdfminer.six for text extraction
      2. Fall back to base64 encoding of the raw bytes
    """
    file_size = os.path.getsize(path)
    text_content: Optional[str] = None

    # Try text extraction first
    try:
        text_content = _read_pdf_with_pdfminer(path, pages)
    except ImportError:
        pass  # pdfminer not available
    except Exception:
        pass  # corrupted PDF or other error — fall back to base64

    if text_content is not None and text_content.strip():
        _check_token_limit(text_content, "pdf", max_tokens)
        # Return as a text result so the model can read it
        lines = text_content.splitlines(keepends=True)
        content_with_nums = "".join(
            f"{i + 1}\t{line}" for i, line in enumerate(lines)
        )
        return {
            "type": "pdf",
            "file": {
                "file_path": path,
                "content": content_with_nums,
                "original_size": file_size,
            },
            "text": content_with_nums,
            "file_path": path,
            "original_size": file_size,
        }

    # Fallback: return base64 for the model to process as a document block
    b64, orig_size = _read_pdf_base64(path)
    return {
        "type": "pdf",
        "file": {
            "file_path": path,
            "base64": b64,
            "original_size": orig_size,
        },
        "text": f"[PDF: {path} ({orig_size:,} bytes) — text extraction unavailable, raw bytes returned]",
        "base64": b64,
        "file_path": path,
        "original_size": orig_size,
    }


# ---------------------------------------------------------------------------
# FileReadTool
# ---------------------------------------------------------------------------

class FileReadTool:
    """
    Read a file from the local filesystem.

    Supports:
      - Plain text with optional offset/limit and line numbers
      - Images (PNG, JPG, JPEG, GIF, WEBP) → base64
      - Jupyter notebooks (.ipynb) → structured cells
      - PDF files → text extraction (pdfminer) or base64 fallback
    """

    name = FILE_READ_TOOL_NAME
    description = "Read a file from the local filesystem."
    is_read_only = True

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The absolute path to the file to read",
                },
                "offset": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "The line number to start reading from. "
                        "Only provide if the file is too large to read at once."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "The number of lines to read. "
                        "Only provide if the file is too large to read at once."
                    ),
                },
                "pages": {
                    "type": "string",
                    "description": (
                        f'Page range for PDF files (e.g., "1-5", "3", "10-20"). '
                        f"Only applicable to PDF files. "
                        f"Maximum {PDF_MAX_PAGES_PER_READ} pages per request."
                    ),
                },
            },
            "required": ["file_path"],
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_input(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pre-call validation (mirrors TS validateInput).
        Returns {'valid': bool, 'error': str|None, 'error_code': int}.
        """
        file_path: str = input_data.get("file_path", "")
        pages: Optional[str] = input_data.get("pages")

        # 1. Validate pages parameter (pure string parsing, no I/O)
        if pages is not None:
            parsed = parse_pdf_page_range(pages)
            if parsed is None:
                return {
                    "valid": False,
                    "error": (
                        f'Invalid pages parameter: "{pages}". '
                        'Use formats like "1-5", "3", or "10-20". Pages are 1-indexed.'
                    ),
                    "error_code": 7,
                }
            last = parsed["last_page"]
            range_size = (
                PDF_MAX_PAGES_PER_READ + 1
                if last == float("inf")
                else last - parsed["first_page"] + 1
            )
            if range_size > PDF_MAX_PAGES_PER_READ:
                return {
                    "valid": False,
                    "error": (
                        f'Page range "{pages}" exceeds maximum of '
                        f"{PDF_MAX_PAGES_PER_READ} pages per request. "
                        "Please use a smaller range."
                    ),
                    "error_code": 8,
                }

        # 2. Expand path
        full_path = os.path.abspath(os.path.expanduser(file_path))

        # 3. Binary extension check (excludes PDF and images — handled natively)
        ext = Path(full_path).suffix.lstrip(".").lower()
        if (
            has_binary_extension(full_path)
            and ext not in PDF_EXTENSIONS
            and ext not in IMAGE_EXTENSIONS
        ):
            return {
                "valid": False,
                "error": (
                    f"This tool cannot read binary files. "
                    f"The file appears to be a binary {ext!r} file. "
                    "Please use appropriate tools for binary file analysis."
                ),
                "error_code": 4,
            }

        # 4. Blocked device paths
        if is_blocked_device_path(full_path):
            return {
                "valid": False,
                "error": (
                    f"Cannot read '{file_path}': this device file would block "
                    "or produce infinite output."
                ),
                "error_code": 9,
            }

        return {"valid": True, "error": None, "error_code": 0}

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def call(self, input_data: Dict[str, Any], context: Any = None) -> dict:
        file_path: str = input_data.get("file_path", "")
        offset: Optional[int] = input_data.get("offset")
        limit: Optional[int] = input_data.get("limit")
        pages: Optional[str] = input_data.get("pages")
        return await self._read(file_path, offset, limit, pages)

    async def _read(
        self,
        file_path: str,
        offset: Optional[int],
        limit: Optional[int],
        pages: Optional[str] = None,
    ) -> dict:
        """Core read dispatcher — mirrors callInner in the TS implementation."""
        path = os.path.abspath(os.path.expanduser(file_path))

        # --- Blocked device ---
        if is_blocked_device_path(path):
            return {
                "text": (
                    f"Error: Reading '{file_path}' is not allowed "
                    "(blocked device file)."
                )
            }

        # --- Existence check (try alternate macOS screenshot path) ---
        if not os.path.exists(path):
            alt = _get_alternate_screenshot_path(path)
            if alt and os.path.exists(alt):
                path = alt
            else:
                return {"text": f"Error: File not found: {file_path}"}

        if os.path.isdir(path):
            return {"text": f"Error: '{file_path}' is a directory."}

        limits = get_default_file_reading_limits()
        max_size = limits["max_size_bytes"]
        max_tokens = limits["max_tokens"]

        file_size = os.path.getsize(path)
        ext = Path(path).suffix.lstrip(".").lower()

        # --- Image ---
        if ext in IMAGE_EXTENSIONS:
            try:
                return _read_image(path)
            except Exception as exc:
                return {"text": f"Error reading image '{file_path}': {exc}"}

        # --- Jupyter notebook ---
        if ext == "ipynb":
            try:
                return _read_notebook(path)
            except Exception as exc:
                return {"text": f"Error reading notebook '{file_path}': {exc}"}

        # --- PDF ---
        if ext in PDF_EXTENSIONS:
            # Validate pages param if provided
            if pages is not None:
                parsed = parse_pdf_page_range(pages)
                if parsed is None:
                    return {
                        "text": (
                            f"Error: Invalid pages parameter '{pages}'. "
                            'Use formats like "1-5", "3", or "10-20".'
                        )
                    }
            try:
                return _read_pdf(path, pages=pages, max_tokens=max_tokens)
            except MaxFileReadTokenExceededError as exc:
                return {"text": f"Error: {exc}"}
            except Exception as exc:
                return {"text": f"Error reading PDF '{file_path}': {exc}"}

        # --- Binary content sniff (for files without recognised binary extension) ---
        try:
            with open(path, "rb") as fh:
                probe = fh.read(_BINARY_SNIFF_BYTES)
            if is_binary_content(probe):
                return {
                    "text": (
                        f"Error: '{file_path}' appears to be a binary file "
                        f"(detected NUL bytes). Use appropriate tools for binary analysis."
                    )
                }
        except OSError as exc:
            return {"text": f"Error reading file '{file_path}': {exc}"}

        # --- Size guard (before full read) ---
        if file_size > max_size and offset is None and limit is None:
            return {
                "text": (
                    f"Error: File is too large ({file_size:,} bytes, "
                    f"max {max_size:,} bytes). "
                    "Use offset and limit to read specific portions."
                )
            }

        # --- Plain text ---
        try:
            return _read_text_ranged(path, offset, limit, max_tokens, ext)
        except MaxFileReadTokenExceededError as exc:
            return {"text": f"Error: {exc}"}
        except UnicodeDecodeError:
            return {
                "text": (
                    f"Error: '{file_path}' could not be decoded as UTF-8. "
                    "The file may be binary or use an unsupported encoding."
                )
            }
        except OSError as exc:
            return {"text": f"Error reading file '{file_path}': {exc}"}

    # ------------------------------------------------------------------
    # Convenience wrappers (sync-style, used by tests / callers that
    # don't have an async event loop)
    # ------------------------------------------------------------------

    def _read_text(
        self,
        path: str,
        offset: Optional[int],
        limit: Optional[int],
    ) -> dict:
        """Synchronous text-read helper (kept for backward compatibility)."""
        limits = get_default_file_reading_limits()
        ext = Path(path).suffix.lstrip(".").lower()
        return _read_text_ranged(path, offset, limit, limits["max_tokens"], ext)

    async def _read_image(self, path: str) -> dict:  # type: ignore[override]
        """Async image-read helper (kept for backward compatibility)."""
        return _read_image(path)

    def _read_notebook(self, path: str) -> dict:
        """Sync notebook-read helper (kept for backward compatibility)."""
        return _read_notebook(path)
