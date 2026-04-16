# Source: utils/pdf.ts
"""
PDF file handling utilities.

Provides:
- read_pdf(path)        → base64-encoded PDF (for API upload)
- pdf_to_base64(path)   → alias for the base64 encoding step
- extract_pdf_pages()   → render pages as JPEG via pdftoppm
- get_pdf_page_count()  → page count via pdfinfo
- is_pdf_file(path)     → quick magic-bytes check
"""
from __future__ import annotations

import asyncio
import base64
import os
import re
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Union

# ---------------------------------------------------------------------------
# Size limits (mirrors apiLimits.ts)
# ---------------------------------------------------------------------------

PDF_TARGET_RAW_SIZE: int = 20 * 1024 * 1024   # 20 MB
PDF_MAX_EXTRACT_SIZE: int = 100 * 1024 * 1024  # 100 MB


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class PDFError:
    reason: Literal["empty", "too_large", "password_protected", "corrupted", "unknown", "unavailable"]
    message: str


@dataclass
class PDFFileData:
    file_path: str
    base64: str
    original_size: int


@dataclass
class PDFReadSuccess:
    type: Literal["pdf"] = "pdf"
    file: Optional[PDFFileData] = None


@dataclass
class PDFPartsData:
    file_path: str
    original_size: int
    output_dir: str
    count: int


@dataclass
class PDFPartsSuccess:
    type: Literal["parts"] = "parts"
    file: Optional[PDFPartsData] = None


# Union result types
PDFReadResult = Union[Dict[str, Any], None]  # {"success": bool, "data"/"error": ...}


def _make_ok(data: Any) -> Dict[str, Any]:
    return {"success": True, "data": data}


def _make_err(error: PDFError) -> Dict[str, Any]:
    return {"success": False, "error": {"reason": error.reason, "message": error.message}}


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def is_pdf_file(path: str) -> bool:
    """
    Returns True if the file exists and starts with the %PDF- magic bytes.
    Fast check — does not parse the full document.
    """
    try:
        with open(path, "rb") as f:
            header = f.read(5)
        return header == b"%PDF-"
    except OSError:
        return False


def _format_file_size(size: int) -> str:
    """Human-readable file size string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size //= 1024
    return f"{size:.1f} TB"


# ---------------------------------------------------------------------------
# PDF reading (base64 for API upload)
# ---------------------------------------------------------------------------


async def read_pdf(path: str) -> Dict[str, Any]:
    """
    Read a PDF file and return it as base64-encoded data suitable for API upload.
    Returns a result dict: {success, data} or {success, error}.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _read_pdf_sync, path)


def _read_pdf_sync(path: str) -> Dict[str, Any]:
    try:
        stat = os.stat(path)
        original_size = stat.st_size

        if original_size == 0:
            return _make_err(PDFError("empty", f"PDF file is empty: {path}"))

        if original_size > PDF_TARGET_RAW_SIZE:
            return _make_err(PDFError(
                "too_large",
                f"PDF file exceeds maximum allowed size of {_format_file_size(PDF_TARGET_RAW_SIZE)}.",
            ))

        with open(path, "rb") as f:
            file_bytes = f.read()

        # Validate magic bytes
        if not file_bytes[:5] == b"%PDF-":
            return _make_err(PDFError(
                "corrupted",
                f"File is not a valid PDF (missing %PDF- header): {path}",
            ))

        b64 = base64.b64encode(file_bytes).decode("ascii")
        return _make_ok({
            "type": "pdf",
            "file": {"file_path": path, "base64": b64, "original_size": original_size},
        })

    except PermissionError as e:
        return _make_err(PDFError("unknown", str(e)))
    except OSError as e:
        return _make_err(PDFError("unknown", str(e)))
    except Exception as e:
        return _make_err(PDFError("unknown", str(e)))


async def pdf_to_base64(path: str) -> Optional[str]:
    """
    Return the base64 encoding of a PDF file, or None on failure.
    Convenience wrapper around read_pdf().
    """
    result = await read_pdf(path)
    if result["success"]:
        return result["data"]["file"]["base64"]
    return None


# ---------------------------------------------------------------------------
# Page count via pdfinfo
# ---------------------------------------------------------------------------


async def get_pdf_page_count(path: str) -> Optional[int]:
    """
    Get the number of pages in a PDF using pdfinfo (poppler-utils).
    Returns None if pdfinfo is unavailable or fails.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_page_count_sync, path)


def _get_page_count_sync(path: str) -> Optional[int]:
    try:
        result = subprocess.run(
            ["pdfinfo", path],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        match = re.search(r"^Pages:\s+(\d+)", result.stdout, re.MULTILINE)
        if not match:
            return None
        count = int(match.group(1))
        return count if count > 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return None


# ---------------------------------------------------------------------------
# pdftoppm availability (cached)
# ---------------------------------------------------------------------------

_pdftoppm_available: Optional[bool] = None


def reset_pdftoppm_cache() -> None:
    """Reset the pdftoppm availability cache (for tests)."""
    global _pdftoppm_available
    _pdftoppm_available = None


async def is_pdftoppm_available() -> bool:
    """Check whether pdftoppm binary is available (result cached)."""
    global _pdftoppm_available
    if _pdftoppm_available is not None:
        return _pdftoppm_available
    loop = asyncio.get_event_loop()
    _pdftoppm_available = await loop.run_in_executor(None, _check_pdftoppm)
    return _pdftoppm_available


def _check_pdftoppm() -> bool:
    try:
        result = subprocess.run(
            ["pdftoppm", "-v"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0 or len(result.stderr) > 0
    except FileNotFoundError:
        return False
    except subprocess.TimeoutExpired:
        return False


# ---------------------------------------------------------------------------
# Extract PDF pages as JPEG images
# ---------------------------------------------------------------------------


async def extract_pdf_pages(
    path: str,
    first_page: Optional[int] = None,
    last_page: Optional[int] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract PDF pages as JPEG images using pdftoppm.
    Returns result dict with type='parts' and output directory info.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _extract_pages_sync, path, first_page, last_page, output_dir
    )


def _extract_pages_sync(
    path: str,
    first_page: Optional[int],
    last_page: Optional[int],
    output_dir: Optional[str],
) -> Dict[str, Any]:
    try:
        stat = os.stat(path)
        original_size = stat.st_size

        if original_size == 0:
            return _make_err(PDFError("empty", f"PDF file is empty: {path}"))

        if original_size > PDF_MAX_EXTRACT_SIZE:
            return _make_err(PDFError(
                "too_large",
                f"PDF exceeds max size for extraction ({_format_file_size(PDF_MAX_EXTRACT_SIZE)}).",
            ))

        # Check pdftoppm availability synchronously
        try:
            probe = subprocess.run(["pdftoppm", "-v"], capture_output=True, timeout=5)
            available = probe.returncode == 0 or len(probe.stderr) > 0
        except FileNotFoundError:
            available = False

        if not available:
            return _make_err(PDFError(
                "unavailable",
                "pdftoppm is not installed. Install poppler-utils to enable PDF page rendering.",
            ))

        # Prepare output directory
        if output_dir is None:
            uid = str(uuid.uuid4())
            output_dir = os.path.join(tempfile.gettempdir(), f"pdf-{uid}")
        os.makedirs(output_dir, exist_ok=True)

        prefix = os.path.join(output_dir, "page")
        args = ["pdftoppm", "-jpeg", "-r", "100"]
        if first_page:
            args += ["-f", str(first_page)]
        if last_page and last_page != float("inf"):
            args += ["-l", str(last_page)]
        args += [path, prefix]

        result = subprocess.run(args, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            stderr = result.stderr
            if re.search(r"password", stderr, re.IGNORECASE):
                return _make_err(PDFError("password_protected", "PDF is password-protected."))
            if re.search(r"damaged|corrupt|invalid", stderr, re.IGNORECASE):
                return _make_err(PDFError("corrupted", "PDF file is corrupted or invalid."))
            return _make_err(PDFError("unknown", f"pdftoppm failed: {stderr}"))

        image_files = sorted(f for f in os.listdir(output_dir) if f.endswith(".jpg"))
        if not image_files:
            return _make_err(PDFError("corrupted", "pdftoppm produced no output pages."))

        return _make_ok({
            "type": "parts",
            "file": {
                "file_path": path,
                "original_size": original_size,
                "output_dir": output_dir,
                "count": len(image_files),
            },
        })

    except Exception as e:
        return _make_err(PDFError("unknown", str(e)))


# ---------------------------------------------------------------------------
# pypdf text extraction (optional dependency)
# ---------------------------------------------------------------------------

try:
    from pypdf import PdfReader as _PdfReader
    _PYPDF_AVAILABLE = True
except ImportError:
    _PYPDF_AVAILABLE = False


async def read_pdf_text(path: str) -> Optional[str]:
    """
    Extract plain text from a PDF using pypdf.
    Returns None if pypdf is unavailable or extraction fails.
    """
    if not _PYPDF_AVAILABLE:
        return None
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _read_pdf_text_sync, path)


def _read_pdf_text_sync(path: str) -> Optional[str]:
    if not _PYPDF_AVAILABLE:
        return None
    try:
        reader = _PdfReader(path)  # type: ignore[name-defined]
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    except Exception:
        return None
