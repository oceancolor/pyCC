"""
bash_provider.py - Bash shell provider for command execution.

Port of TypeScript bashProvider.ts.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional


def _get_disable_extglob_command(shell_path: str) -> Optional[str]:
    """Get the command to disable extended glob patterns."""
    shell_prefix = os.environ.get('CLAUDE_CODE_SHELL_PREFIX', '')
    if shell_prefix:
        return '{ shopt -u extglob || setopt NO_EXTENDED_GLOB; } >/dev/null 2>&1 || true'

    if 'bash' in shell_path:
        return 'shopt -u extglob 2>/dev/null || true'
    elif 'zsh' in shell_path:
        return 'setopt NO_EXTENDED_GLOB 2>/dev/null || true'
    return None


async def create_bash_shell_provider(
    shell_path: str,
    options: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    Create a bash shell provider for command execution.

    Args:
        shell_path: Path to the bash/zsh executable
        options: Options dict with optional 'skipSnapshot' key

    Returns:
        ShellProvider instance
    """
    from .shell_provider import ShellProvider
    from ..bash.shell_snapshot import create_and_save_snapshot
    from ..bash.shell_quoting import quote_shell_command, rewrite_windows_null_redirect, should_add_stdin_redirect
    from ..bash.bash_pipe_command import rearrange_pipe_command
    from ..bash.shell_prefix import format_shell_prefix_command
    from ..bash.shell_quote import quote

    skip_snapshot = (options or {}).get('skipSnapshot', False)

    # Start snapshot creation
    if skip_snapshot:
        snapshot_promise = asyncio.sleep(0)
        snapshot_value = None
    else:
        try:
            snapshot_value = await asyncio.wait_for(
                create_and_save_snapshot(shell_path),
                timeout=30,
            )
        except Exception:
            snapshot_value = None

    last_snapshot_file_path: Optional[str] = None
    current_sandbox_tmp_dir: Optional[str] = None

    class BashProvider(ShellProvider):
        type = 'bash'
        detached = True

        async def build_exec_command(
            self,
            command: str,
            opts: Dict[str, Any],
        ) -> Dict[str, str]:
            nonlocal last_snapshot_file_path, current_sandbox_tmp_dir

            snap = snapshot_value

            # Check if snapshot file still exists
            if snap:
                try:
                    Path(snap).stat()
                except OSError:
                    snap = None

            last_snapshot_file_path = snap
            current_sandbox_tmp_dir = opts.get('sandboxTmpDir')

            tmpdir = tempfile.gettempdir()
            cmd_id = opts.get('id', 'unknown')
            use_sandbox = opts.get('useSandbox', False)

            if use_sandbox and opts.get('sandboxTmpDir'):
                shell_cwd_file = os.path.join(opts['sandboxTmpDir'], f"cwd-{cmd_id}")
                cwd_file_path = shell_cwd_file
            else:
                cwd_file_path = os.path.join(tmpdir, f"claude-{cmd_id}-cwd")
                shell_cwd_file = cwd_file_path

            normalized = rewrite_windows_null_redirect(command)
            add_stdin = should_add_stdin_redirect(normalized)
            quoted_command = quote_shell_command(normalized, add_stdin)

            if '|' in normalized and add_stdin:
                quoted_command = rearrange_pipe_command(normalized)

            command_parts = []

            if snap:
                command_parts.append(f"source {quote([snap])} 2>/dev/null || true")

            disable_extglob = _get_disable_extglob_command(shell_path)
            if disable_extglob:
                command_parts.append(disable_extglob)

            command_parts.append(f"eval {quoted_command}")
            command_parts.append(f"pwd -P >| {quote([shell_cwd_file])}")

            command_string = ' && '.join(command_parts)

            shell_prefix = os.environ.get('CLAUDE_CODE_SHELL_PREFIX', '')
            if shell_prefix:
                command_string = format_shell_prefix_command(shell_prefix, command_string)

            return {'commandString': command_string, 'cwdFilePath': cwd_file_path}

        def get_spawn_args(self, command_string: str) -> list:
            skip_login = last_snapshot_file_path is not None
            if skip_login:
                return ['-c', command_string]
            return ['-c', '-l', command_string]

        async def get_environment_overrides(self, command: str) -> Dict[str, str]:
            env: Dict[str, str] = {}

            if current_sandbox_tmp_dir:
                env['TMPDIR'] = current_sandbox_tmp_dir
                env['CLAUDE_CODE_TMPDIR'] = current_sandbox_tmp_dir
                env['TMPPREFIX'] = os.path.join(current_sandbox_tmp_dir, 'zsh')

            # Apply session env vars
            try:
                from ...utils.session_env_vars import get_session_env_vars
                for key, value in get_session_env_vars():
                    env[key] = value
            except ImportError:
                pass

            return env

    provider = BashProvider()
    provider.shell_path = shell_path
    return provider
