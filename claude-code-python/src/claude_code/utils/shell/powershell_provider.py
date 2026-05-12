"""
powershell_provider.py - PowerShell shell provider for command execution.

Port of TypeScript powershellProvider.ts.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional


async def create_powershell_provider(
    shell_path: str,
    options: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    Create a PowerShell shell provider for command execution.

    Args:
        shell_path: Path to pwsh or powershell.exe
        options: Optional configuration options

    Returns:
        ShellProvider instance for PowerShell
    """
    from .shell_provider import ShellProvider

    class PowerShellProvider(ShellProvider):
        type = 'powershell'
        detached = False

        async def build_exec_command(
            self,
            command: str,
            opts: Dict[str, Any],
        ) -> Dict[str, str]:
            tmpdir = tempfile.gettempdir()
            cmd_id = opts.get('id', 'unknown')
            cwd_file_path = os.path.join(tmpdir, f"claude-ps-{cmd_id}-cwd")

            # PowerShell execution policy and command structure
            # Use -EncodedCommand to safely pass the command
            import base64

            # Build a PowerShell script that runs the command and saves cwd
            ps_script = f"""
try {{
    {command}
}} finally {{
    $pwd.Path | Out-File -FilePath '{cwd_file_path}' -Encoding UTF8 -NoNewline
}}
"""
            # Encode the script as UTF-16LE base64 for PowerShell -EncodedCommand
            encoded = base64.b64encode(ps_script.encode('utf-16-le')).decode('ascii')
            command_string = encoded

            return {'commandString': command_string, 'cwdFilePath': cwd_file_path}

        def get_spawn_args(self, command_string: str) -> list:
            return [
                '-NoProfile',
                '-NonInteractive',
                '-ExecutionPolicy', 'Bypass',
                '-EncodedCommand', command_string,
            ]

        async def get_environment_overrides(self, command: str) -> Dict[str, str]:
            return {}

    provider = PowerShellProvider()
    provider.shell_path = shell_path
    return provider
