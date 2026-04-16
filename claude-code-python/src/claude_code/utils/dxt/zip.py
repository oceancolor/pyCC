"""DXT zip extraction with validation. Ported from utils/dxt/zip.ts"""
from __future__ import annotations
import zipfile
import os
from pathlib import Path

MAX_FILE_SIZE = 512 * 1024 * 1024
MAX_TOTAL_SIZE = 1024 * 1024 * 1024
MAX_FILE_COUNT = 100_000

async def extract_zip(zip_path: str, dest_dir: str) -> None:
    total_size = 0
    with zipfile.ZipFile(zip_path, 'r') as zf:
        names = zf.namelist()
        if len(names) > MAX_FILE_COUNT:
            raise ValueError(f"Too many files in zip: {len(names)}")
        for name in names:
            info = zf.getinfo(name)
            if info.file_size > MAX_FILE_SIZE:
                raise ValueError(f"File too large: {name}")
            total_size += info.file_size
            if total_size > MAX_TOTAL_SIZE:
                raise ValueError("Total uncompressed size exceeds limit")
            # Path traversal check
            dest = Path(dest_dir) / name
            if not str(dest.resolve()).startswith(str(Path(dest_dir).resolve())):
                raise ValueError(f"Path traversal detected: {name}")
        zf.extractall(dest_dir)
