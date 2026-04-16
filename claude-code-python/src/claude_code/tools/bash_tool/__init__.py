"""
Bash tool implementation
原始 TS: src/tools/BashTool/BashTool.tsx

execa/child_process → asyncio.subprocess
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Optional

from pydantic import BaseModel, Field

from claude_code.constants.tools import BASH_TOOL_NAME
from claude_code.tool import Tool, ToolInputJSONSchema, ToolUseContext, ValidationResult, ValidationResultOk, ValidationResultFail
from claude_code.utils.shell import exec_command
from claude_code.utils.shell_command import ExecResult

DEFAULT_TIMEOUT_MS = 120_000  # 2 minutes
MAX_TIMEOUT_MS = 10 * 60 * 1000  # 10 minutes


class BashInput(BaseModel):
    command: str = Field(description="The bash command to execute")
    timeout: Optional[int] = Field(
        default=None,
        description=f"Timeout in milliseconds (max {MAX_TIMEOUT_MS}ms / {MAX_TIMEOUT_MS // 60000} minutes)",
    )
    description: Optional[str] = Field(
        default=None,
        description="Short description of what the command does",
    )
    restart: Optional[bool] = Field(
        default=None,
        description="Whether to restart the shell session",
    )
    run_in_background: Optional[bool] = Field(
        default=None,
        description="Run command in background (don't wait for completion)",
    )


class BashTool(Tool):
    """
    Executes a given bash command and returns its output.
    原始 TS: src/tools/BashTool/BashTool.tsx
    """

    name = BASH_TOOL_NAME
    search_hint = "execute shell commands"
    max_result_size_chars = 200_000

    async def description(self) -> str:
        return "Executes a given bash command and returns its output."

    async def prompt(self) -> str:
        return f"""Executes a given bash command and returns its output.

The working directory persists between commands, but shell state does not.

IMPORTANT: Avoid using this tool to run find, grep, cat, head, tail, sed, awk, or echo commands,
unless explicitly instructed or after you have verified that a dedicated tool cannot accomplish your task.

# Instructions
- If your command will create new directories or files, first use this tool to run `ls` to verify the parent directory exists.
- Always quote file paths that contain spaces with double quotes.
- Try to maintain your current working directory throughout the session by using absolute paths.
- You may specify an optional timeout in milliseconds (up to {MAX_TIMEOUT_MS}ms / {MAX_TIMEOUT_MS // 60000} minutes).
- When issuing multiple commands: if independent, make multiple tool calls in parallel; if sequential, use && to chain them.

# Git Safety Protocol
- NEVER update the git config
- NEVER run destructive git commands (push --force, reset --hard, etc.) unless explicitly requested
- NEVER skip hooks (--no-verify) unless explicitly requested
"""

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": f"Timeout in milliseconds (max {MAX_TIMEOUT_MS})",
                },
                "description": {
                    "type": "string",
                    "description": "Short description of what the command does",
                },
                "restart": {
                    "type": "boolean",
                    "description": "Whether to restart the shell session",
                },
                "run_in_background": {
                    "type": "boolean",
                    "description": "Run command in background",
                },
            },
            "required": ["command"],
        }

    async def validate_input(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> ValidationResult:
        command = input_data.get("command", "")
        if not isinstance(command, str) or not command.strip():
            return ValidationResultFail(
                result=False,
                message="command must be a non-empty string",
                error_code=1,
            )
        timeout = input_data.get("timeout")
        if timeout is not None and (not isinstance(timeout, int) or timeout > MAX_TIMEOUT_MS):
            return ValidationResultFail(
                result=False,
                message=f"timeout must be an integer ≤ {MAX_TIMEOUT_MS}",
                error_code=1,
            )
        return ValidationResultOk()

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        command = input_data["command"]
        timeout_ms = input_data.get("timeout") or DEFAULT_TIMEOUT_MS
        timeout_ms = min(int(timeout_ms), MAX_TIMEOUT_MS)

        cwd = os.getcwd()

        result: ExecResult = await exec_command(
            command,
            cwd=cwd,
            timeout_ms=timeout_ms,
        )

        # Build output
        output_parts: list[str] = []
        if result.stdout:
            output_parts.append(result.stdout)
        if result.stderr:
            output_parts.append(result.stderr)

        output = "\n".join(output_parts)

        return {
            "output": output,
            "exit_code": result.code,
            "interrupted": result.interrupted,
        }

    def user_facing_name(self, input_data: Optional[dict[str, Any]] = None) -> str:
        if input_data and "command" in input_data:
            cmd = input_data["command"]
            # Shorten long commands
            if len(cmd) > 60:
                cmd = cmd[:57] + "..."
            return f"$ {cmd}"
        return f"$ ..."

    def get_tool_use_summary(self, input_data: dict[str, Any]) -> Optional[str]:
        return input_data.get("command", "")
