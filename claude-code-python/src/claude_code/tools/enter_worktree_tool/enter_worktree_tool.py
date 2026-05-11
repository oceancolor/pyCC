"""EnterWorktreeTool. Ported from EnterWorktreeTool/EnterWorktreeTool.ts"""
from __future__ import annotations
import os
import re
import subprocess
from typing import Any, Dict, Optional

ENTER_WORKTREE_TOOL_NAME = "EnterWorktree"
_MAX_SLUG_LEN = 64
_VALID_SEGMENT = re.compile(r'^[A-Za-z0-9._-]+$')


def validate_worktree_slug(name: str) -> None:
    """Raise ValueError if the worktree name is invalid.

    Each '/'-separated segment may only contain letters, digits, dots,
    underscores and dashes; total length must not exceed 64 chars.
    """
    if not name:
        raise ValueError("Worktree name must not be empty")
    if len(name) > _MAX_SLUG_LEN:
        raise ValueError(f"Worktree name must be at most {_MAX_SLUG_LEN} characters")
    for segment in name.split("/"):
        if not _VALID_SEGMENT.match(segment):
            raise ValueError(
                f"Invalid segment '{segment}': each part may only contain "
                "letters, digits, '.', '_', and '-'"
            )


def _get_cwd() -> str:
    try:
        from claude_code.utils.cwd import get_cwd  # type: ignore[import]
        return get_cwd()
    except Exception:
        return os.getcwd()


def _find_canonical_git_root(cwd: str) -> Optional[str]:
    """Return the top-level of the git repository containing *cwd*, or None."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


class EnterWorktreeOutput:
    def __init__(self, worktree_path: str, worktree_branch: Optional[str], message: str) -> None:
        self.worktree_path = worktree_path
        self.worktree_branch = worktree_branch
        self.message = message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worktree_path": self.worktree_path,
            "worktree_branch": self.worktree_branch,
            "message": self.message,
        }


class EnterWorktreeTool:
    """Create an isolated git worktree and switch the session into it.

    Ported from EnterWorktreeTool/EnterWorktreeTool.ts.
    """

    name = ENTER_WORKTREE_TOOL_NAME
    search_hint = "create an isolated git worktree and switch into it"
    max_result_size_chars = 100_000
    should_defer = True
    is_read_only = False

    async def description(self) -> str:
        return (
            "Creates an isolated worktree (via git or configured hooks) and switches "
            "the session into it"
        )

    async def call(
        self,
        name: Optional[str] = None,
        context: Any = None,
    ) -> Dict[str, Any]:
        """Create a git worktree and return its path."""
        import uuid

        cwd = _get_cwd()

        # Resolve to main repo root so worktree creation works from within a worktree
        main_root = _find_canonical_git_root(cwd)
        if main_root and main_root != cwd:
            os.chdir(main_root)
            cwd = main_root

        slug = name or str(uuid.uuid4())[:8]
        if name:
            validate_worktree_slug(name)

        # Derive a branch name from the slug
        branch_name = f"worktree/{slug}"
        worktree_path = os.path.join(cwd, ".git", "worktrees-sessions", slug)

        try:
            subprocess.run(
                ["git", "worktree", "add", "-b", branch_name, worktree_path],
                cwd=cwd,
                check=True,
                capture_output=True,
                timeout=30,
            )
            os.chdir(worktree_path)
        except subprocess.CalledProcessError as exc:
            error_msg = exc.stderr.decode() if exc.stderr else str(exc)
            raise RuntimeError(f"Failed to create worktree: {error_msg}") from exc
        except FileNotFoundError:
            raise RuntimeError("git is not available — cannot create worktree")

        branch_info = f" on branch {branch_name}"
        message = (
            f"Created worktree at {worktree_path}{branch_info}. "
            "The session is now working in the worktree. "
            "Use ExitWorktree to leave mid-session, or exit the session to be prompted."
        )

        return {
            "data": {
                "worktree_path": worktree_path,
                "worktree_branch": branch_name,
                "message": message,
            }
        }

    def map_tool_result(self, data: Dict[str, Any], tool_use_id: str) -> Dict[str, Any]:
        inner = data.get("data", data)
        return {
            "type": "tool_result",
            "content": inner.get("message", ""),
            "tool_use_id": tool_use_id,
        }
