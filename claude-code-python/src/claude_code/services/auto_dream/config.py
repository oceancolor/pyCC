"""Auto dream config. Ported from services/autoDream/config.ts"""
import os

def is_auto_dream_enabled() -> bool:
    return os.environ.get("CLAUDE_CODE_AUTO_DREAM", "").lower() in ("1", "true")
