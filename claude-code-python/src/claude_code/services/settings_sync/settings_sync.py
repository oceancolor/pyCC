"""Settings sync service stub. Ported from services/settingsSync."""
from __future__ import annotations
from typing import Any, Dict

async def sync_settings() -> None:
    pass

async def get_remote_settings() -> Dict[str, Any]:
    return {}
