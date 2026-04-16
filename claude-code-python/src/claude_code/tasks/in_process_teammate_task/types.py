"""InProcessTeammateTask types. Ported from tasks/InProcessTeammateTask/types.ts (121L)."""
from __future__ import annotations
from typing import TypedDict, Optional


class TeammateIdentity(TypedDict):
    team_name: str
    agent_name: str
    description: Optional[str]


class InProcessTeammateTaskState(TypedDict, total=False):
    id: str
    type: str  # "in_process_teammate"
    status: str
    description: str
    identity: TeammateIdentity
    start_time: float
    end_time: Optional[float]
    output_file: str
    output_offset: int
    notified: bool
    is_backgrounded: bool
