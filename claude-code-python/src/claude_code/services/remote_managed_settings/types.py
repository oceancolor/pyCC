"""Remote managed settings types."""
from typing import TypedDict, Any, Optional
class RemoteSettings(TypedDict, total=False):
    version: int
    settings: Any
    updated_at: Optional[float]
