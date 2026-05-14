"""GitHub-style activity heatmap for the terminal. Ported from utils/heatmap.ts"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

# ANSI grey/green intensity levels
_INTENSITY_COLORS = [
    "\x1b[38;5;238m",  # 0 – empty (dark grey)
    "\x1b[38;5;22m",   # 1 – low (very dark green)
    "\x1b[38;5;28m",   # 2 – medium-low
    "\x1b[38;5;34m",   # 3 – medium
    "\x1b[38;5;40m",   # 4 – high (bright green)
]
_RESET = "\x1b[0m"
_BLOCK = "■"


@dataclass
class DailyActivity:
    """Activity record for a single day."""

    date: str  # ISO format 'YYYY-MM-DD'
    message_count: int = 0
    cost: float = 0.0


@dataclass
class HeatmapOptions:
    terminal_width: int = 80
    show_month_labels: bool = True


def _calculate_percentiles(daily_activity: List[DailyActivity]) -> Optional[dict]:
    """Pre-calculate p25/p50/p75 percentiles for intensity bucketing."""
    counts = sorted(a.message_count for a in daily_activity if a.message_count > 0)
    if not counts:
        return None
    n = len(counts)
    return {
        "p25": counts[int(n * 0.25)],
        "p50": counts[int(n * 0.50)],
        "p75": counts[int(n * 0.75)],
    }


def _get_intensity(count: int, percentiles: Optional[dict]) -> int:
    """Map a raw message count to an intensity bucket 0–4."""
    if count <= 0 or percentiles is None:
        return 0
    if count <= percentiles["p25"]:
        return 1
    if count <= percentiles["p50"]:
        return 2
    if count <= percentiles["p75"]:
        return 3
    return 4


_MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def generate_heatmap(
    daily_activity: List[DailyActivity],
    options: Optional[HeatmapOptions] = None,
) -> str:
    """Generate a GitHub-style activity heatmap for the terminal.

    Args:
        daily_activity: List of :class:`DailyActivity` objects.
        options: Optional :class:`HeatmapOptions` for display control.

    Returns:
        A multi-line string ready to print in a terminal.
    """
    opts = options or HeatmapOptions()
    day_label_width = 4
    available_width = opts.terminal_width - day_label_width
    num_weeks = max(10, min(52, available_width))

    activity_map: Dict[str, int] = {a.date: a.message_count for a in daily_activity}
    percentiles = _calculate_percentiles(daily_activity)

    today = date.today()
    # Find the Sunday of the current week
    current_week_start = today - timedelta(days=today.weekday() + 1) if today.weekday() != 6 else today
    # For Python: date.weekday() returns Mon=0..Sun=6; we want Sun=0
    # date.isoweekday() returns Mon=1..Sun=7
    days_since_sunday = today.isoweekday() % 7  # Sun=0, Mon=1, ..., Sat=6
    current_week_start = today - timedelta(days=days_since_sunday)
    start_date = current_week_start - timedelta(weeks=num_weeks - 1)

    # grid[day_of_week][week] = intensity 0–4
    grid: List[List[int]] = [[0] * num_weeks for _ in range(7)]
    month_starts: List[Tuple[int, int]] = []  # (month_index, week_col)
    last_month = -1

    for week_col in range(num_weeks):
        for day_row in range(7):
            current = start_date + timedelta(weeks=week_col, days=day_row)
            date_str = current.isoformat()
            count = activity_map.get(date_str, 0)
            grid[day_row][week_col] = _get_intensity(count, percentiles)

            if week_col == 0 or (day_row == 0 and current.month != last_month):
                if current.month != last_month:
                    month_starts.append((current.month - 1, week_col))
                    last_month = current.month

    lines: List[str] = []

    # Month label row
    if opts.show_month_labels:
        month_line = " " * day_label_width
        prev_end = 0
        for month_idx, week_col in month_starts:
            if week_col > prev_end:
                month_line += " " * (week_col - prev_end)
            abbr = _MONTH_ABBR[month_idx]
            month_line += abbr
            prev_end = week_col + len(abbr)
        lines.append(month_line)

    # Day rows
    for day_row in range(7):
        if day_row % 2 == 0:
            label = f"{_DAY_LABELS[day_row]:3s} "
        else:
            label = "    "
        row_cells = ""
        for week_col in range(num_weeks):
            intensity = grid[day_row][week_col]
            color = _INTENSITY_COLORS[intensity]
            row_cells += f"{color}{_BLOCK}{_RESET}"
        lines.append(label + row_cells)

    return "\n".join(lines)
