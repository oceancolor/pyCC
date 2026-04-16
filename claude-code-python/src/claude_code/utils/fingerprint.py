# 原始 TS: utils/fingerprint.ts
"""系统指纹（机器唯一标识，用于匿名分析）"""
from __future__ import annotations
import hashlib
import os
import platform
import uuid
from pathlib import Path
from typing import Optional

_FP_FILE = Path.home() / ".claude" / ".fingerprint"


def _generate_fingerprint() -> str:
    parts = [
        platform.node(),
        platform.machine(),
        platform.system(),
        str(uuid.getnode()),  # MAC address based
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def get_fingerprint() -> str:
    if _FP_FILE.exists():
        fp = _FP_FILE.read_text().strip()
        if fp:
            return fp
    fp = _generate_fingerprint()
    _FP_FILE.parent.mkdir(parents=True, exist_ok=True)
    _FP_FILE.write_text(fp)
    return fp
