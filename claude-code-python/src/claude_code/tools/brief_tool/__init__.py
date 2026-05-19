"""BriefTool package.

Re-exports the BriefTool class from its implementation module.

BriefTool is a lightweight tool that produces a brief, one-sentence summary
of the agent's planned or completed action.  It is used to populate the
non-verbose display label shown in compact/spinner UI modes.

When the model is about to perform a long-running operation, it can call
BriefTool first to set a human-readable status message like
"Running database migration" rather than showing the raw command.

Ported from: tools/BriefTool/ (TypeScript)

Usage::

    from claude_code.tools.brief_tool import BriefTool
"""
from __future__ import annotations

from claude_code.tools.brief_tool.brief_tool import BriefTool

__all__ = ["BriefTool"]
