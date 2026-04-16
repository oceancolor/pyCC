# 原始 TS: tasks/
"""任务系统：长期运行的后台任务管理"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    task_id: str
    name: str
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    _asyncio_task: Optional[asyncio.Task] = field(default=None, repr=False)

    def cancel(self) -> bool:
        if self._asyncio_task and not self._asyncio_task.done():
            self._asyncio_task.cancel()
            self.status = TaskStatus.CANCELLED
            return True
        return False

    @property
    def is_done(self) -> bool:
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)


class TaskManager:
    """后台任务管理器"""

    def __init__(self) -> None:
        self._tasks: Dict[str, Task] = {}

    def submit(self, name: str, coro: Coroutine) -> Task:
        task_id = str(uuid.uuid4())[:8]
        task = Task(task_id=task_id, name=name, status=TaskStatus.PENDING)

        async def _run():
            task.status = TaskStatus.RUNNING
            try:
                task.result = await coro
                task.status = TaskStatus.COMPLETED
            except asyncio.CancelledError:
                task.status = TaskStatus.CANCELLED
            except Exception as e:
                task.error = str(e)
                task.status = TaskStatus.FAILED

        asyncio_task = asyncio.get_event_loop().create_task(_run())
        task._asyncio_task = asyncio_task
        self._tasks[task_id] = task
        return task

    def get(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def list_tasks(self, status: Optional[TaskStatus] = None) -> List[Task]:
        if status:
            return [t for t in self._tasks.values() if t.status == status]
        return list(self._tasks.values())

    def cancel(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        return task.cancel() if task else False

    def cleanup_done(self) -> int:
        done = [tid for tid, t in self._tasks.items() if t.is_done]
        for tid in done:
            del self._tasks[tid]
        return len(done)


_manager = TaskManager()

def get_task_manager() -> TaskManager:
    return _manager
