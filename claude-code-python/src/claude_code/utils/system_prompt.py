# 原始 TS: utils/systemPrompt.ts
"""System prompt 构建"""
from __future__ import annotations
import os
import platform
from typing import Optional
from .claude_md import read_claude_md
from .model_utils import get_main_loop_model


BASE_SYSTEM_PROMPT = """You are Claude Code, an AI coding assistant made by Anthropic.
You help with software development tasks including writing, editing, and explaining code,
debugging, testing, and general software engineering questions."""


def build_system_prompt(
    cwd: Optional[str] = None,
    extra: Optional[str] = None,
    include_env_info: bool = True,
) -> str:
    parts = [BASE_SYSTEM_PROMPT]

    if include_env_info:
        parts.append(f"\nCurrent working directory: {cwd or os.getcwd()}")
        parts.append(f"OS: {platform.system()} {platform.release()}")
        parts.append(f"Shell: {os.environ.get('SHELL', 'unknown')}")

    claude_md = read_claude_md(cwd)
    if claude_md:
        parts.append(f"\n---\nProject instructions:\n{claude_md}")

    if extra:
        parts.append(f"\n{extra}")

    return "\n".join(parts)


def get_compact_summary_prompt() -> str:
    return (
        "Please provide a concise summary of the conversation so far, "
        "focusing on the key decisions made, code changes, and current state of the task."
    )
