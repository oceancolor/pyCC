"""ExitWorktreeTool — exit a worktree session and return to the original directory.

Ported from ExitWorktreeTool/ExitWorktreeTool.ts.
"""
from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, Optional

from claude_code.tools.exit_worktree_tool.constants import EXIT_WORKTREE_TOOL_NAME

# Module-level state mirrors the TypeScript currentWorktreeSession singleton.
_current_worktree_session: Optional[Dict[str, Any]] = None


def set_current_worktree_session(session: Optional[Dict[str, Any]]) -> None:
    """Store the active worktree session (called by EnterWorktreeTool)."""
    global _current_worktree_session
    _current_worktree_session = session


def get_current_worktree_session() -> Optional[Dict[str, Any]]:
    """Return the active worktree session, or None if not in one."""
    return _current_worktree_session


def _count_changed_files(worktree_path: str) -> int:
    """Return the number of changed/untracked files in *worktree_path*."""
    try:
        result = subprocess.run(
            ["git", "-C", worktree_path, "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return 0
        return sum(1 for line in result.stdout.splitlines() if line.strip())
    except Exception:
        return 0


def _count_extra_commits(worktree_path: str, original_head: str) -> int:
    """Return the number of commits in worktree HEAD that are not in *original_head*."""
    try:
        result = subprocess.run(
            ["git", "-C", worktree_path, "rev-list", "--count", f"{original_head}..HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return 0
        return int(result.stdout.strip() or "0")
    except Exception:
        return 0


def _remove_worktree(worktree_path: str, *, force: bool = False) -> None:
    """Remove a git worktree from the repository."""
    args = ["git", "worktree", "remove", worktree_path]
    if force:
        args.append("--force")
    subprocess.run(args, capture_output=True, timeout=30)

    # Best-effort: also prune stale entries
    try:
        main_root = subprocess.run(
            ["git", "-C", worktree_path, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if main_root.returncode == 0:
            root = main_root.stdout.strip()
            subprocess.run(["git", "-C", root, "worktree", "prune"],
                           capture_output=True, timeout=10)
    except Exception:
        pass


class ExitWorktreeTool:
    """Exit the current git worktree session and restore the original directory.

    Supports two actions:
      - "keep"   — leave the worktree and branch on disk; just restore cwd.
      - "remove" — delete the worktree and its branch (fails if uncommitted
                   work exists unless *discard_changes* is True).
    """

    name = EXIT_WORKTREE_TOOL_NAME
    description = "Exits a worktree session created by EnterWorktree and restores the original working directory"
    search_hint = "exit a worktree session and return to the original directory"
    max_result_size_chars = 100_000
    should_defer = True
    is_read_only = False

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["keep", "remove"],
                    "description": (
                        '"keep" leaves the worktree and branch on disk; '
                        '"remove" deletes both.'
                    ),
                },
                "discard_changes": {
                    "type": "boolean",
                    "description": (
                        "Required true when action is \"remove\" and the worktree "
                        "has uncommitted files or unmerged commits. The tool will "
                        "refuse and list them otherwise."
                    ),
                },
            },
            "required": ["action"],
        }

    def validate_input(self, action: str, discard_changes: bool = False) -> Dict[str, Any]:
        """Return {"result": True} or {"result": False, "message": ..., "errorCode": int}."""
        session = get_current_worktree_session()
        if not session:
            return {
                "result": False,
                "message": (
                    "No-op: there is no active EnterWorktree session to exit. "
                    "This tool only operates on worktrees created by EnterWorktree "
                    "in the current session — it will not touch worktrees created "
                    "manually or in a previous session. No filesystem changes were made."
                ),
                "errorCode": 1,
            }

        if action == "remove" and not discard_changes:
            worktree_path = session["worktree_path"]
            original_head = session.get("original_head_commit")

            changed_files = _count_changed_files(worktree_path)
            commits = _count_extra_commits(worktree_path, original_head) if original_head else 0

            if changed_files > 0 or commits > 0:
                parts: list[str] = []
                if changed_files > 0:
                    label = "file" if changed_files == 1 else "files"
                    parts.append(f"{changed_files} uncommitted {label}")
                if commits > 0:
                    label = "commit" if commits == 1 else "commits"
                    branch = session.get("worktree_branch", "the worktree branch")
                    parts.append(f"{commits} {label} on {branch}")
                return {
                    "result": False,
                    "message": (
                        f"Worktree has {' and '.join(parts)}. Removing will discard this work "
                        "permanently. Confirm with the user, then re-invoke with "
                        "discard_changes: true — or use action: \"keep\" to preserve the worktree."
                    ),
                    "errorCode": 2,
                }

        return {"result": True}

    async def call(
        self,
        action: str,
        discard_changes: bool = False,
        context: Any = None,
    ) -> Dict[str, Any]:
        """Execute the exit action and return a result dict."""
        # Validate first
        validation = self.validate_input(action, discard_changes)
        if not validation["result"]:
            raise ValueError(validation["message"])

        session = get_current_worktree_session()
        if not session:
            raise RuntimeError("Not in a worktree session")

        original_cwd: str = session["original_cwd"]
        worktree_path: str = session["worktree_path"]
        worktree_branch: Optional[str] = session.get("worktree_branch")
        original_head: Optional[str] = session.get("original_head_commit")

        changed_files = _count_changed_files(worktree_path)
        commits = _count_extra_commits(worktree_path, original_head) if original_head else 0

        # Restore cwd before any cleanup
        try:
            os.chdir(original_cwd)
        except OSError:
            pass

        # Clear session state
        set_current_worktree_session(None)

        if action == "keep":
            message = (
                f"Exited worktree. Your work is preserved at {worktree_path}"
                + (f" on branch {worktree_branch}" if worktree_branch else "")
                + f". Session is now back in {original_cwd}."
            )
            return {
                "data": {
                    "action": "keep",
                    "original_cwd": original_cwd,
                    "worktree_path": worktree_path,
                    "worktree_branch": worktree_branch,
                    "message": message,
                }
            }

        # action == "remove"
        _remove_worktree(worktree_path, force=discard_changes)

        # Optionally delete the branch too
        if worktree_branch:
            try:
                subprocess.run(
                    ["git", "-C", original_cwd, "branch", "-D", worktree_branch],
                    capture_output=True,
                    timeout=10,
                )
            except Exception:
                pass

        discard_parts: list[str] = []
        if commits > 0:
            label = "commit" if commits == 1 else "commits"
            discard_parts.append(f"{commits} {label}")
        if changed_files > 0:
            label = "file" if changed_files == 1 else "files"
            discard_parts.append(f"{changed_files} uncommitted {label}")

        discard_note = f" Discarded {' and '.join(discard_parts)}." if discard_parts else ""
        message = (
            f"Exited and removed worktree at {worktree_path}.{discard_note} "
            f"Session is now back in {original_cwd}."
        )
        return {
            "data": {
                "action": "remove",
                "original_cwd": original_cwd,
                "worktree_path": worktree_path,
                "worktree_branch": worktree_branch,
                "discarded_files": changed_files,
                "discarded_commits": commits,
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
