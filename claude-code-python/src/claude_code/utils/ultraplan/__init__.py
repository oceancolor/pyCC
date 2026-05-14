"""UltraPlan utilities sub-package. Ported from utils/ultraplan/.

Provides keyword detection and CCR (Continuous Context Refresh) session
helpers for the UltraPlan extended planning feature.
"""
from __future__ import annotations

from claude_code.utils.ultraplan.keyword import (
    find_ultraplan_trigger_positions,
    find_ultrareview_trigger_positions,
)
from claude_code.utils.ultraplan.ccr_session import (
    ScanResult,
    UltraplanPollError,
)

__all__ = [
    "find_ultraplan_trigger_positions",
    "find_ultrareview_trigger_positions",
    "ScanResult",
    "UltraplanPollError",
]
