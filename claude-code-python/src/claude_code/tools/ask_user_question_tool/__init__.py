"""AskUserQuestionTool package.

Re-exports the AskUserQuestionTool class from its implementation module.

The AskUserQuestionTool allows an agent to pause execution and ask the user
a direct question, waiting for a response before continuing.  Unlike a
regular assistant message, using this tool signals that the agent
*requires* human input to proceed.

This tool is especially useful in automated/non-interactive pipelines where
the agent would otherwise make an assumption that could lead to data loss
or incorrect results.

Ported from: tools/AskUserQuestionTool/ (TypeScript)

Usage::

    from claude_code.tools.ask_user_question_tool import AskUserQuestionTool
"""
from __future__ import annotations

from claude_code.tools.ask_user_question_tool.ask_user_question_tool import AskUserQuestionTool

__all__ = ["AskUserQuestionTool"]
