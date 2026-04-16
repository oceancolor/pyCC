"""Message utilities. Ported from utils/messages/."""
from __future__ import annotations
from typing import Any, List, Optional

def extract_text_content(blocks: Any) -> str:
    if isinstance(blocks, str):
        return blocks
    if isinstance(blocks, list):
        return "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
    return ""
