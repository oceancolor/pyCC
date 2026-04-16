# 原始 TS: utils/agentSwarmsEnabled.ts / utils/agenticSessionSearch.ts
"""Agent swarm 配置与 agentic session 搜索"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional
import json


def is_agent_swarms_enabled() -> bool:
    """检查是否启用了 agent swarm 模式"""
    return os.environ.get("CLAUDE_CODE_AGENT_SWARMS", "").lower() in ("1", "true", "yes")


def get_max_concurrent_agents() -> int:
    try:
        return int(os.environ.get("CLAUDE_CODE_MAX_AGENTS", "5"))
    except ValueError:
        return 5


def search_agentic_sessions(query: str, sessions_dir: Optional[Path] = None) -> List[dict]:
    """在已保存的 session 中搜索关键词"""
    if sessions_dir is None:
        sessions_dir = Path.home() / ".claude" / "sessions"
    if not sessions_dir.exists():
        return []

    results = []
    for f in sessions_dir.glob("*.jsonl"):
        try:
            lines = f.read_text().splitlines()
            for line in lines:
                data = json.loads(line)
                content = str(data.get("content", ""))
                if query.lower() in content.lower():
                    header = json.loads(lines[0]) if lines else {}
                    results.append({
                        "session_id": header.get("session_id", f.stem),
                        "file": str(f),
                        "match": content[:200],
                    })
                    break
        except (json.JSONDecodeError, OSError):
            continue
    return results
