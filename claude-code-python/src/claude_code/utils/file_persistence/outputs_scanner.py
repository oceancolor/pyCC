"""Outputs directory scanner. Ported from utils/filePersistence/outputsScanner.ts"""
from __future__ import annotations
import os
import time
from typing import List, Optional

def log_debug(msg: str) -> None:
    pass

def get_environment_kind() -> Optional[str]:
    kind = os.environ.get("CLAUDE_CODE_ENVIRONMENT_KIND")
    return kind if kind in ("byoc", "anthropic_cloud") else None

def capture_turn_start_time() -> float:
    return time.time()

async def find_modified_files(dir_path: str, since_ts: float) -> List[str]:
    results = []
    try:
        for root, _, files in os.walk(dir_path):
            for f in files:
                fpath = os.path.join(root, f)
                if os.path.getmtime(fpath) >= since_ts:
                    results.append(fpath)
    except Exception:
        pass
    return results
