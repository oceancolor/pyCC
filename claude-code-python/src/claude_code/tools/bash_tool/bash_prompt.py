"""
BashTool prompt / description generation. Ported from BashTool/prompt.ts.
"""
from __future__ import annotations
import os
from typing import Optional

from claude_code.tools.bash_tool.tool_name import BASH_TOOL_NAME
from claude_code.utils.timeouts import get_default_bash_timeout_ms, get_max_bash_timeout_ms


def get_default_timeout_ms() -> int:
    return get_default_bash_timeout_ms()


def get_max_timeout_ms() -> int:
    return get_max_bash_timeout_ms()


def _get_background_usage_note() -> Optional[str]:
    if os.environ.get("CLAUDE_CODE_DISABLE_BACKGROUND_TASKS", "").lower() in ("1", "true"):
        return None
    return ("You can use the `run_in_background` parameter to run the command in the background. "
            "Only use this if you don't need the result immediately and are OK being notified "
            "when the command completes later.")


def get_simple_prompt() -> str:
    return f"""Executes a given bash command in a persistent shell session with timeout, ensuring proper
handling and security measures.

IMPORTANT: Avoid commands that produce very large outputs (>200KB). Use head/tail/grep to limit output.

Default timeout: {get_default_timeout_ms() // 1000}s (max: {get_max_timeout_ms() // 1000}s).
"""


def build_bash_prompt() -> str:
    default_ms = get_default_timeout_ms()
    max_ms = get_max_timeout_ms()
    bg_note = _get_background_usage_note()

    bg_section = f"\n\n{bg_note}" if bg_note else ""

    return f"""Executes a given bash command in a persistent shell session with timeout,
ensuring proper handling and security measures.{bg_section}

## Timeout

Default timeout: {default_ms // 1000}s. Maximum: {max_ms // 1000}s.
Override with the `timeout` parameter (milliseconds).

## Output limits

Commands producing >200KB of output will be truncated. Use tools like head, tail,
grep, or pipe to a file to reduce output size.

## Security

- No network access in sandbox mode
- File access restricted to project directories
- Destructive operations require explicit permission

## Working directory

The shell persists between calls. Use `cd` to change directories.
The working directory resets to the project root if you navigate outside allowed paths.

## Shell features

Full bash: pipes, redirects, subshells, env vars, loops, functions.
Background tasks via `run_in_background` parameter (no `&` needed).
"""


BASH_TOOL_DESCRIPTION = "Execute bash commands in a persistent shell session"
