"""Remote managed settings types. Ported from services/remoteManagedSettings/types.ts"""
from __future__ import annotations
from typing import Any, Optional
try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict


class RemoteSettings(TypedDict, total=False):
    """Shape of settings returned from the remote managed settings API."""
    version: int
    settings: Any
    updated_at: Optional[float]


class RemoteManagedSettingsResponse(TypedDict, total=False):
    """API response wrapper for remote managed settings."""
    settings: RemoteSettings
    etag: Optional[str]
    status: str
