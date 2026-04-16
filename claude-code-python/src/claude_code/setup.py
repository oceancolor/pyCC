"""
Session setup and initialization.
Ported from setup.ts (477 lines → core).
"""
from __future__ import annotations
import os
from typing import Optional


async def setup(
    cwd: str,
    permission_mode: str = "default",
    allow_dangerously_skip_permissions: bool = False,
    worktree_enabled: bool = False,
    resume_session_id: Optional[str] = None,
    mcps: Optional[list] = None,
    is_non_interactive: bool = False,
) -> dict:
    """
    Initialize a Claude Code session:
    - Set cwd / project root
    - Load git root
    - Initialize session memory
    - Restore terminal backup
    - Init file watchers
    """
    import os
    os.chdir(cwd)

    from claude_code.utils.cwd import set_cwd
    set_cwd(cwd)

    # Find git root
    git_root = cwd
    try:
        from claude_code.utils.git import find_git_root
        found = find_git_root(cwd)
        if found:
            git_root = found
    except ImportError:
        pass

    # Initialize session
    session_id = resume_session_id or os.environ.get("CLAUDE_CODE_SESSION_ID", "")

    return {
        "cwd": cwd,
        "git_root": git_root,
        "session_id": session_id,
        "permission_mode": permission_mode,
        "worktree_enabled": worktree_enabled,
    }
