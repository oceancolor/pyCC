"""
Shell command execution result types
原始 TS: src/utils/ShellCommand.ts (types only)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExecResult:
    """Result of executing a shell command."""
    stdout: str = ""
    stderr: str = ""
    code: int = 0
    interrupted: bool = False
    background_task_id: Optional[str] = None
    backgrounded_by_user: Optional[bool] = None
    assistant_auto_backgrounded: Optional[bool] = None
    output_file_path: Optional[str] = None
    output_file_size: Optional[int] = None
    output_task_id: Optional[str] = None
    pre_spawn_error: Optional[str] = None
