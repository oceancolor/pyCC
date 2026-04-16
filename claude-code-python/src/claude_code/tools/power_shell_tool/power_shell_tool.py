"""PowerShell tool stub. Ported from PowerShellTool (Windows-specific, 7829 lines → stub)."""
from __future__ import annotations
import sys
from typing import Any

POWER_SHELL_TOOL_NAME = "PowerShell"
DESCRIPTION = "Execute PowerShell commands (Windows/cross-platform)"


class PowerShellTool:
    name = POWER_SHELL_TOOL_NAME
    description = DESCRIPTION

    def is_enabled(self) -> bool:
        return sys.platform == "win32"

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "PowerShell command to execute"},
                    "timeout": {"type": "integer", "default": 120000},
                },
                "required": ["command"]
            }
        }

    async def call(self, command: str = "", timeout: int = 120000, **kwargs: Any) -> dict:
        if sys.platform != "win32":
            return {"error": "PowerShell tool is only available on Windows"}
        import asyncio
        try:
            proc = await asyncio.create_subprocess_exec(
                "pwsh", "-NoLogo", "-NonInteractive", "-Command", command,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout / 1000)
            return {
                "stdout": stdout.decode(errors="replace"),
                "stderr": stderr.decode(errors="replace"),
                "exit_code": proc.returncode,
            }
        except asyncio.TimeoutError:
            return {"error": f"PowerShell command timed out after {timeout}ms"}
        except Exception as e:
            return {"error": str(e)}
