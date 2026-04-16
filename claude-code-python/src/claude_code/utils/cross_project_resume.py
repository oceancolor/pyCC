# 原始 TS: utils/crossProjectResume.ts
"""跨项目 session 恢复"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Dict, List, Optional


_INDEX_FILE = Path.home() / ".claude" / "session_index.json"


def _load_index() -> Dict[str, dict]:
    if _INDEX_FILE.exists():
        try:
            return json.loads(_INDEX_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_index(index: Dict[str, dict]) -> None:
    _INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    _INDEX_FILE.write_text(json.dumps(index, indent=2))


def register_session(session_id: str, project_root: str, title: Optional[str] = None) -> None:
    index = _load_index()
    index[session_id] = {
        "session_id": session_id,
        "project_root": project_root,
        "title": title or os.path.basename(project_root),
    }
    _save_index(index)


def find_sessions_for_project(project_root: str) -> List[dict]:
    index = _load_index()
    return [s for s in index.values() if s.get("project_root") == project_root]


def get_session_metadata(session_id: str) -> Optional[dict]:
    return _load_index().get(session_id)


def list_all_sessions() -> List[dict]:
    return list(_load_index().values())
