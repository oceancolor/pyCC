# 原始 TS: utils/concurrentSessions.ts
"""并发 session 管理：跟踪同时运行的 agent session"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import time


@dataclass
class SessionInfo:
    session_id: str
    model: str
    started_at: float = field(default_factory=time.monotonic)
    title: Optional[str] = None
    is_active: bool = True


class ConcurrentSessionManager:
    """线程安全的并发 session 注册表"""

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionInfo] = {}
        self._lock = threading.Lock()

    def register(self, session_id: str, model: str, title: Optional[str] = None) -> None:
        with self._lock:
            self._sessions[session_id] = SessionInfo(
                session_id=session_id, model=model, title=title
            )

    def unregister(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def mark_inactive(self, session_id: str) -> None:
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].is_active = False

    def active_sessions(self) -> List[SessionInfo]:
        with self._lock:
            return [s for s in self._sessions.values() if s.is_active]

    def count(self) -> int:
        return len(self.active_sessions())

    def get(self, session_id: str) -> Optional[SessionInfo]:
        with self._lock:
            return self._sessions.get(session_id)


_manager = ConcurrentSessionManager()

def get_session_manager() -> ConcurrentSessionManager:
    return _manager
