"""Settings sync types."""
from typing import TypedDict
class SyncStatus(TypedDict):
    synced: bool
    last_sync: float
