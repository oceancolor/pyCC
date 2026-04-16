# 原始 TS: utils/forkedAgent.ts
"""子 Agent（fork）管理"""
from __future__ import annotations
import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional


@dataclass
class ForkedAgent:
    agent_id: str
    parent_id: Optional[str]
    model: str
    status: str = "pending"
    result: Optional[Any] = None
    error: Optional[str] = None
    _task: Optional[asyncio.Task] = field(default=None, repr=False)

    def cancel(self) -> None:
        if self._task:
            self._task.cancel()
        self.status = "cancelled"


class ForkManager:
    """管理 forked sub-agents"""

    def __init__(self) -> None:
        self._agents: Dict[str, ForkedAgent] = {}

    def fork(self, parent_id: str, model: str,
             coro: Coroutine) -> ForkedAgent:
        agent_id = str(uuid.uuid4())[:8]
        agent = ForkedAgent(agent_id=agent_id, parent_id=parent_id, model=model)

        async def _run():
            agent.status = "running"
            try:
                agent.result = await coro
                agent.status = "completed"
            except asyncio.CancelledError:
                agent.status = "cancelled"
            except Exception as e:
                agent.error = str(e)
                agent.status = "failed"

        agent._task = asyncio.get_event_loop().create_task(_run())
        self._agents[agent_id] = agent
        return agent

    def get(self, agent_id: str) -> Optional[ForkedAgent]:
        return self._agents.get(agent_id)

    def list_active(self) -> List[ForkedAgent]:
        return [a for a in self._agents.values() if a.status == "running"]


_fork_manager = ForkManager()

def get_fork_manager() -> ForkManager:
    return _fork_manager
