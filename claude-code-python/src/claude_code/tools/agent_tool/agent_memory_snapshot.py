"""Agent memory snapshot utilities. Ported from AgentTool/agentMemorySnapshot.ts"""
from __future__ import annotations
import os
from typing import Any, Dict

async def capture_memory_snapshot(agent_id: str, content: str) -> None:
    """Persist agent memory snapshot."""
    snapshot_dir = os.path.join(os.path.expanduser("~"), ".claude", "agent-snapshots")
    os.makedirs(snapshot_dir, exist_ok=True)
    path = os.path.join(snapshot_dir, f"{agent_id}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

async def load_memory_snapshot(agent_id: str) -> str:
    path = os.path.join(os.path.expanduser("~"), ".claude", "agent-snapshots", f"{agent_id}.md")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""
