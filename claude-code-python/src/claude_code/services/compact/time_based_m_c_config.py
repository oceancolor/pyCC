"""Time-based MicroCompact config. Ported from services/compact/timeBasedMCConfig.ts"""
import os

def get_time_based_mc_interval_ms() -> int:
    val = os.environ.get("CLAUDE_CODE_MC_INTERVAL_MS")
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return 30 * 60 * 1000  # 30 minutes default
