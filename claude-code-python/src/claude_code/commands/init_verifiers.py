"""Init verifiers command. Ported from commands/init-verifiers.ts"""
from __future__ import annotations
from typing import Any, List

NAME = "init-verifiers"
DESCRIPTION = "Create verifier skill(s) for automated verification of code changes"
TYPE = "prompt"
PROGRESS_MESSAGE = "analyzing your project and creating verifier skills"
SOURCE = "builtin"
CONTENT_LENGTH = 0  # Dynamic content


async def run_init_verifiers(claude_md_path: str, context: Any = None) -> List[str]:
    """Verify that /init produced a valid CLAUDE.md. Returns list of issues."""
    return []


async def get_prompt_for_command(args: Any = None, context: Any = None) -> List[dict]:
    """Return the prompt for the /init-verifiers command."""
    return [
        {
            "type": "text",
            "text": (
                "Create one or more verifier skills that can be used by the Verify agent "
                "to automatically verify code changes in this project or folder.\n\n"
                "Analyze the project to detect project type (web, CLI, API) and create "
                "appropriate verifier skills (Playwright for web, Tmux for CLI, HTTP for API)."
            ),
        }
    ]
