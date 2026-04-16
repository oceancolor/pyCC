"""Policy limit types."""
from typing import TypedDict, Optional


class PolicyLimit(TypedDict, total=False):
    feature: str
    limit: Optional[int]
    current: int
    enabled: bool
