"""Footer pill label generator. Ported from tasks/pillLabel.ts"""
from __future__ import annotations
from typing import List

DIAMOND_FILLED = "◆"
DIAMOND_OPEN = "◇"


def get_pill_label(tasks: List[dict]) -> str:
    n = len(tasks)
    if n == 0:
        return ""

    all_same = len({t.get("type") for t in tasks}) == 1
    first = tasks[0]

    if all_same:
        t_type = first.get("type")
        if t_type == "local_bash":
            monitors = sum(1 for t in tasks if t.get("kind") == "monitor")
            shells = n - monitors
            parts = []
            if shells > 0:
                parts.append("1 shell" if shells == 1 else f"{shells} shells")
            if monitors > 0:
                parts.append("1 monitor" if monitors == 1 else f"{monitors} monitors")
            return ", ".join(parts)
        elif t_type == "in_process_teammate":
            team_count = len({t.get("identity", {}).get("team_name") for t in tasks})
            return "1 team" if team_count == 1 else f"{team_count} teams"
        elif t_type == "local_agent":
            return "1 local agent" if n == 1 else f"{n} local agents"
        elif t_type == "remote_agent":
            if n == 1 and first.get("is_ultraplan"):
                phase = first.get("ultraplan_phase")
                if phase == "plan_ready":
                    return f"{DIAMOND_FILLED} ultraplan ready"
                elif phase == "needs_input":
                    return f"{DIAMOND_OPEN} ultraplan needs your input"
                return f"{DIAMOND_OPEN} ultraplan"
            return (f"{DIAMOND_OPEN} 1 cloud session" if n == 1
                    else f"{DIAMOND_OPEN} {n} cloud sessions")
        elif t_type == "local_workflow":
            return "1 background workflow" if n == 1 else f"{n} background workflows"
        elif t_type == "monitor_mcp":
            return "1 monitor" if n == 1 else f"{n} monitors"
        elif t_type == "dream":
            return "dreaming"

    return f"{n} background {'task' if n == 1 else 'tasks'}"


def pill_needs_cta(tasks: List[dict]) -> bool:
    if len(tasks) != 1:
        return False
    t = tasks[0]
    return (
        t.get("type") == "remote_agent"
        and t.get("is_ultraplan") is True
        and t.get("ultraplan_phase") is not None
    )
