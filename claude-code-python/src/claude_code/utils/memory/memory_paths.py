"""Memory paths. Ported from utils/memory/."""
from __future__ import annotations
import os
from pathlib import Path

def get_memory_dir() -> str:
    return str(Path.home() / ".claude" / "memory")
