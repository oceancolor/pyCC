"""OAuth client stub. Ported from services/oauth/client.ts"""
from __future__ import annotations
from typing import Optional

async def get_oauth_token() -> Optional[str]:
    import os
    return os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")

async def refresh_oauth_token(refresh_token: str) -> Optional[str]:
    return None
