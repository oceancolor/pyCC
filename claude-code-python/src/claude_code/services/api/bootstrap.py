"""Bootstrap API call. Ported from services/api/bootstrap.ts"""
from __future__ import annotations
from typing import Any, Dict, List, Optional


class BootstrapResponse(dict):
    pass


async def fetch_bootstrap() -> Optional[BootstrapResponse]:
    """Fetch bootstrap data (client config, model options). Stub."""
    return None


_bootstrap_cache: Optional[BootstrapResponse] = None


async def get_bootstrap_response() -> Optional[BootstrapResponse]:
    global _bootstrap_cache
    if _bootstrap_cache is None:
        _bootstrap_cache = await fetch_bootstrap()
    return _bootstrap_cache


async def get_additional_model_options() -> List[Dict[str, str]]:
    return []
