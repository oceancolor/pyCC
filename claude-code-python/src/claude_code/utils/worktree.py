"""
Worktree utilities
原始 TS: utils/worktree.ts

Provides git worktree lifecycle management:
  - validate_worktree_slug
  - worktree_branch_name
  - create_worktree_for_session
  - cleanup_worktree / keep_worktree
  - create_agent_worktree / remove_agent_worktree
  - cleanup_stale_agent_worktrees
  - has_worktree_changes
  - copy_worktree_include_files
  - parse_pr_reference
  - generate_tmux_session_name
  - is_tmux_available / get_tmux_install_instructions
  - create_tmux_session_for_worktree / kill_tmux_session
  - exec_into_tmux_worktree
  - get_current_worktree_session / restore_worktree_session
"""
from __future__ import annotations

import asyncio
import os
import platform
import random
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from .debug import debug_log as _debug_log
from .errors import error_message, get_errno_code
from .exec_file_no_throw import exec_file_no_throw, exec_file_no_throw_sync, ExecResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_WORKTREE_SLUG_SEGMENT = re.compile(r'^[a-zA-Z0-9._-]+$')
_MAX_WORKTREE_SLUG_LENGTH = 64

# Env vars that suppress git/SSH credential prompts
_GIT_NO_PROMPT_ENV: Dict[str, str] = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "",
}

# Ephemeral slug patterns created by agent/workflow/bridge tools
_EPHEMERAL_WORKTREE_PATTERNS = [
    re.compile(r'^agent-a[0-9a-f]{7}$'),
    re.compile(r'^wf_[0-9a-f]{8}-[0-9a-f]{3}-\d+$'),
    re.compile(r'^wf-\d+$'),
    re.compile(r'^bridge-[A-Za-z0-9_]+(-[A-Za-z0-9_]+)*$'),
    re.compile(r'^job-[a-zA-Z0-9._-]{1,55}-[0-9a-f]{8}$'),
]


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class WorktreeSession:
    original_cwd: str
    worktree_path: str
    worktree_name: str
    session_id: str
    worktree_branch: Optional[str] = None
    original_branch: Optional[str] = None
    original_head_commit: Optional[str] = None
    tmux_session_name: Optional[str] = None
    hook_based: Optional[bool] = None
    creation_duration_ms: Optional[int] = None
    used_sparse_paths: Optional[bool] = None


@dataclass
class _WorktreeCreateResult:
    worktree_path: str
    worktree_branch: str
    head_commit: str
    existed: bool
    base_branch: Optional[str] = None  # only when existed=False


# ---------------------------------------------------------------------------
# Global session state
# ---------------------------------------------------------------------------

_current_worktree_session: Optional[WorktreeSession] = None


def get_current_worktree_session() -> Optional[WorktreeSession]:
    """Return the active WorktreeSession, or None."""
    return _current_worktree_session


def restore_worktree_session(session: Optional[WorktreeSession]) -> None:
    """Restore a session from persistent storage (--resume)."""
    global _current_worktree_session
    _current_worktree_session = session


# ---------------------------------------------------------------------------
# Slug validation
# ---------------------------------------------------------------------------

def validate_worktree_slug(slug: str) -> None:
    """
    Validate a worktree slug to prevent path traversal.

    原始 TS: validateWorktreeSlug
    Raises ValueError on invalid input.
    """
    if len(slug) > _MAX_WORKTREE_SLUG_LENGTH:
        raise ValueError(
            f"Invalid worktree name: must be {_MAX_WORKTREE_SLUG_LENGTH} "
            f"characters or fewer (got {len(slug)})"
        )
    for segment in slug.split('/'):
        if segment in ('.', '..'):
            raise ValueError(
                f'Invalid worktree name "{slug}": must not contain "." or ".." path segments'
            )
        if not _VALID_WORKTREE_SLUG_SEGMENT.match(segment):
            raise ValueError(
                f'Invalid worktree name "{slug}": each "/"-separated segment must be '
                f'non-empty and contain only letters, digits, dots, underscores, and dashes'
            )


# ---------------------------------------------------------------------------
# Name / path helpers
# ---------------------------------------------------------------------------

def _flatten_slug(slug: str) -> str:
    """Replace '/' with '+' to avoid nested paths and D/F conflicts."""
    return slug.replace('/', '+')


def worktree_branch_name(slug: str) -> str:
    """Return the git branch name for a worktree slug.  原始 TS: worktreeBranchName"""
    return f"worktree-{_flatten_slug(slug)}"


def _worktrees_dir(repo_root: str) -> str:
    return str(Path(repo_root) / ".claude" / "worktrees")


def _worktree_path_for(repo_root: str, slug: str) -> str:
    return str(Path(_worktrees_dir(repo_root)) / _flatten_slug(slug))


def generate_tmux_session_name(repo_path: str, branch: str) -> str:
    """原始 TS: generateTmuxSessionName"""
    repo_name = Path(repo_path).name
    combined = f"{repo_name}_{branch}"
    return re.sub(r'[/.]', '_', combined)


# ---------------------------------------------------------------------------
# Git helpers (thin wrappers over exec_file_no_throw)
# ---------------------------------------------------------------------------

def _git_exe() -> str:
    """Return the git executable (honour GIT_EXEC_PATH env)."""
    return os.environ.get("GIT_EXEC_PATH", "git")


async def _exec_git(args: List[str], *, cwd: str, env: Optional[Dict] = None) -> ExecResult:
    merged_env = {**os.environ, **_GIT_NO_PROMPT_ENV, **(env or {})}
    return await exec_file_no_throw(_git_exe(), args, cwd=cwd, env=merged_env)


async def _read_worktree_head_sha(worktree_path: str) -> Optional[str]:
    """
    Fast-path: read HEAD SHA directly from the worktree's .git pointer
    without spawning a subprocess.  Returns None if the worktree doesn't exist
    or HEAD can't be resolved.

    原始 TS: readWorktreeHeadSha (from git/gitFilesystem.ts)
    """
    git_file = Path(worktree_path) / ".git"
    if not git_file.exists():
        return None

    try:
        if git_file.is_file():
            # Worktree pointer: "gitdir: <path>"
            content = git_file.read_text().strip()
            m = re.match(r'gitdir:\s*(.+)', content)
            if not m:
                return None
            git_dir = str((git_file.parent / m.group(1).strip()).resolve())
        elif git_file.is_dir():
            git_dir = str(git_file)
        else:
            return None

        head_file = Path(git_dir) / "HEAD"
        if not head_file.exists():
            return None
        head_content = head_file.read_text().strip()

        if head_content.startswith("ref: "):
            ref_path = head_content[5:]  # e.g. "refs/heads/main"
            # Try packed-refs first, then loose ref file
            ref_file = Path(git_dir) / ref_path
            if ref_file.exists():
                sha = ref_file.read_text().strip()
                if re.match(r'^[0-9a-f]{40,}$', sha):
                    return sha
            # Try packed-refs
            packed_refs_file = Path(git_dir) / "packed-refs"
            if packed_refs_file.exists():
                for line in packed_refs_file.read_text().splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] == ref_path:
                        return parts[0]
            return None
        elif re.match(r'^[0-9a-f]{40,}$', head_content):
            return head_content
        return None
    except Exception:
        return None


async def _resolve_git_dir(repo_root: str) -> Optional[str]:
    """Return the .git directory path for a repo root."""
    git_path = Path(repo_root) / ".git"
    if git_path.is_dir():
        return str(git_path)
    if git_path.is_file():
        content = git_path.read_text().strip()
        m = re.match(r'gitdir:\s*(.+)', content)
        if m:
            return str((git_path.parent / m.group(1).strip()).resolve())
    return None


async def _get_common_dir(git_dir: str) -> Optional[str]:
    """Return the commondir for a worktree git dir, or None."""
    common_file = Path(git_dir) / "commondir"
    if not common_file.exists():
        return None
    try:
        rel = common_file.read_text().strip()
        candidate = (Path(git_dir) / rel).resolve()
        if candidate.is_dir():
            return str(candidate)
    except Exception:
        pass
    return None


async def _resolve_ref(git_dir: str, ref: str) -> Optional[str]:
    """Read a git ref from loose files or packed-refs."""
    # Try loose ref
    loose = Path(git_dir) / ref
    try:
        if loose.exists():
            sha = loose.read_text().strip()
            if re.match(r'^[0-9a-f]{40,}$', sha):
                return sha
    except Exception:
        pass
    # Try packed-refs
    try:
        packed = Path(git_dir) / "packed-refs"
        if packed.exists():
            for line in packed.read_text().splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1] == ref:
                    return parts[0]
    except Exception:
        pass
    return None


def _find_canonical_git_root(start: str) -> Optional[str]:
    """
    Like find_git_root but follows worktree .git pointers to the main repo.
    原始 TS: findCanonicalGitRoot
    """
    current = os.path.realpath(start)
    while True:
        git_path = Path(current) / ".git"
        if git_path.is_dir():
            return current
        if git_path.is_file():
            # Worktree pointer – follow it to the main repo
            content = git_path.read_text().strip()
            m = re.match(r'gitdir:\s*(.+)', content)
            if m:
                git_dir = str((git_path.parent / m.group(1).strip()).resolve())
                # commondir points to main repo .git
                common_file = Path(git_dir) / "commondir"
                if common_file.exists():
                    rel = common_file.read_text().strip()
                    main_git = (Path(git_dir) / rel).resolve()
                    main_root = main_git.parent
                    if main_root.exists():
                        return str(main_root)
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


def _find_git_root(start: str) -> Optional[str]:
    """Find nearest ancestor with .git (dir or file)."""
    current = os.path.realpath(start)
    while True:
        if (Path(current) / ".git").exists():
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


async def _get_branch(cwd: Optional[str] = None) -> Optional[str]:
    """Return current branch name or None."""
    result = await exec_file_no_throw(
        _git_exe(),
        ["rev-parse", "--abbrev-ref", "HEAD"],
        cwd=cwd or os.getcwd(),
    )
    if result.code == 0:
        return result.stdout.strip()
    return None


async def _get_default_branch(cwd: Optional[str] = None) -> str:
    """Return the remote default branch (main/master)."""
    result = await exec_file_no_throw(
        _git_exe(),
        ["symbolic-ref", "refs/remotes/origin/HEAD", "--short"],
        cwd=cwd or os.getcwd(),
    )
    if result.code == 0:
        branch = result.stdout.strip()
        if branch.startswith("origin/"):
            return branch[7:]
        return branch
    # Fallback: try to infer from common names
    for candidate in ("main", "master"):
        res = await exec_file_no_throw(
            _git_exe(),
            ["rev-parse", "--verify", f"origin/{candidate}"],
            cwd=cwd or os.getcwd(),
        )
        if res.code == 0:
            return candidate
    return "main"


async def _parse_git_config_value(
    git_dir: str,
    section: str,
    subsection: Optional[str],
    key: str,
) -> Optional[str]:
    """Read a single git config value from file directly."""
    from .git.git_config_parser import parse_git_config_value as _pgcv
    return await _pgcv(git_dir, section, subsection, key)


# ---------------------------------------------------------------------------
# Settings helpers (minimal stubs for what worktree.ts needs)
# ---------------------------------------------------------------------------

class _WorktreeSettings:
    sparse_paths: List[str] = []
    symlink_directories: List[str] = []


class _InitialSettings:
    worktree: Optional[_WorktreeSettings] = None


def _get_initial_settings() -> _InitialSettings:
    """
    Stub for getInitialSettings().  In a full port this would read
    settings.json; here we return empty defaults so the porting layer is
    complete but non-destructive.
    """
    try:
        from .settings.settings import get_initial_settings as _gs
        return _gs()
    except Exception:
        return _InitialSettings()


def _get_relative_settings_file_path_for_source(source: str) -> str:
    """Stub for getRelativeSettingsFilePathForSource."""
    try:
        from .settings.settings import get_relative_settings_file_path_for_source as _f
        return _f(source)
    except Exception:
        return ".claude/settings.local.json"


def _save_current_project_config(updater) -> None:  # type: ignore[type-arg]
    """Stub for saveCurrentProjectConfig."""
    try:
        from .config import save_current_project_config
        save_current_project_config(updater)
    except Exception:
        pass


def _get_cwd() -> str:
    """Stub for getCwd()."""
    try:
        from .cwd import get_cwd
        return get_cwd()
    except Exception:
        return os.getcwd()


# ---------------------------------------------------------------------------
# Hook helpers
# ---------------------------------------------------------------------------

def _has_worktree_create_hook() -> bool:
    try:
        from .hooks import has_worktree_create_hook
        return has_worktree_create_hook()
    except Exception:
        return False


async def _execute_worktree_create_hook(slug: str):  # type: ignore[return]
    from .hooks import execute_worktree_create_hook
    return await execute_worktree_create_hook(slug)


async def _execute_worktree_remove_hook(worktree_path: str) -> bool:
    try:
        from .hooks import execute_worktree_remove_hook
        return await execute_worktree_remove_hook(worktree_path)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Platform helper
# ---------------------------------------------------------------------------

def _get_platform() -> str:
    s = sys.platform.lower()
    if s == "darwin":
        return "macos"
    if "linux" in s:
        return "linux"
    if s == "win32":
        return "windows"
    return s


# ---------------------------------------------------------------------------
# Path traversal helper
# ---------------------------------------------------------------------------

def _contains_path_traversal(path: str) -> bool:
    """Return True if path contains '..' components or is absolute."""
    try:
        from .path import contains_path_traversal
        return contains_path_traversal(path)
    except Exception:
        parts = Path(path).parts
        return any(p in ('..', '.') for p in parts) or Path(path).is_absolute()


# ---------------------------------------------------------------------------
# Symlink / mkdir helpers
# ---------------------------------------------------------------------------

async def _mkdir_recursive(dir_path: str) -> None:
    Path(dir_path).mkdir(parents=True, exist_ok=True)


async def _symlink_directories(
    repo_root_path: str,
    worktree_path: str,
    dirs_to_symlink: List[str],
) -> None:
    """Symlink directories from main repo to worktree to avoid disk bloat."""
    for d in dirs_to_symlink:
        if _contains_path_traversal(d):
            log_for_debugging(
                f'Skipping symlink for "{d}": path traversal detected',
                level="warn",
            )
            continue

        source_path = str(Path(repo_root_path) / d)
        dest_path = str(Path(worktree_path) / d)

        try:
            os.symlink(source_path, dest_path)
            log_for_debugging(
                f"Symlinked {d} from main repository to worktree to avoid disk bloat"
            )
        except OSError as e:
            code = get_errno_code(e)
            import errno
            if code not in (errno.ENOENT, errno.EEXIST):
                log_for_debugging(
                    f"Failed to symlink {d} ({code or 'unknown'}): {error_message(e)}",
                    level="warn",
                )


# ---------------------------------------------------------------------------
# Core: get_or_create_worktree
# ---------------------------------------------------------------------------

async def _get_or_create_worktree(
    repo_root: str,
    slug: str,
    *,
    pr_number: Optional[int] = None,
) -> _WorktreeCreateResult:
    """
    Create a new git worktree for *slug*, or resume if it already exists.
    原始 TS: getOrCreateWorktree
    """
    worktree_path = _worktree_path_for(repo_root, slug)
    worktree_branch = worktree_branch_name(slug)

    # Fast-path resume: read HEAD directly without spawning git
    existing_head = await _read_worktree_head_sha(worktree_path)
    if existing_head:
        return _WorktreeCreateResult(
            worktree_path=worktree_path,
            worktree_branch=worktree_branch,
            head_commit=existing_head,
            existed=True,
        )

    # New worktree: create the worktrees directory
    await _mkdir_recursive(_worktrees_dir(repo_root))

    fetch_env = {**os.environ, **_GIT_NO_PROMPT_ENV}
    base_branch: str
    base_sha: Optional[str] = None

    if pr_number is not None:
        pr_fetch = await exec_file_no_throw(
            _git_exe(),
            ["fetch", "origin", f"pull/{pr_number}/head"],
            cwd=repo_root,
            env=fetch_env,
        )
        if pr_fetch.code != 0:
            stderr_msg = pr_fetch.stderr.strip() or (
                'PR may not exist or the repository may not have a remote named "origin"'
            )
            raise RuntimeError(
                f"Failed to fetch PR #{pr_number}: {stderr_msg}"
            )
        base_branch = "FETCH_HEAD"
    else:
        default_branch, git_dir = await asyncio.gather(
            _get_default_branch(repo_root),
            _resolve_git_dir(repo_root),
        )
        origin_ref = f"origin/{default_branch}"
        origin_sha = (
            await _resolve_ref(git_dir, f"refs/remotes/origin/{default_branch}")
            if git_dir
            else None
        )
        if origin_sha:
            base_branch = origin_ref
            base_sha = origin_sha
        else:
            fetch_result = await exec_file_no_throw(
                _git_exe(),
                ["fetch", "origin", default_branch],
                cwd=repo_root,
                env=fetch_env,
            )
            base_branch = origin_ref if fetch_result.code == 0 else "HEAD"

    # Resolve SHA if we don't have it yet
    if base_sha is None:
        rev_parse = await exec_file_no_throw(
            _git_exe(),
            ["rev-parse", base_branch],
            cwd=repo_root,
        )
        if rev_parse.code != 0:
            raise RuntimeError(
                f'Failed to resolve base branch "{base_branch}": git rev-parse failed'
            )
        base_sha = rev_parse.stdout.strip()

    settings = _get_initial_settings()
    sparse_paths: List[str] = []
    if settings.worktree and settings.worktree.sparse_paths:
        sparse_paths = list(settings.worktree.sparse_paths)

    add_args = ["worktree", "add"]
    if sparse_paths:
        add_args.append("--no-checkout")
    # -B resets any orphan branch left by a previously-removed worktree dir
    add_args.extend(["-B", worktree_branch, worktree_path, base_branch])

    create_result = await exec_file_no_throw(
        _git_exe(), add_args, cwd=repo_root
    )
    if create_result.code != 0:
        raise RuntimeError(f"Failed to create worktree: {create_result.stderr}")

    if sparse_paths:
        async def tear_down(msg: str) -> None:
            await exec_file_no_throw(
                _git_exe(),
                ["worktree", "remove", "--force", worktree_path],
                cwd=repo_root,
            )
            raise RuntimeError(msg)

        sparse_result = await exec_file_no_throw(
            _git_exe(),
            ["sparse-checkout", "set", "--cone", "--", *sparse_paths],
            cwd=worktree_path,
        )
        if sparse_result.code != 0:
            await tear_down(f"Failed to configure sparse-checkout: {sparse_result.stderr}")

        co_result = await exec_file_no_throw(
            _git_exe(),
            ["checkout", "HEAD"],
            cwd=worktree_path,
        )
        if co_result.code != 0:
            await tear_down(f"Failed to checkout sparse worktree: {co_result.stderr}")

    return _WorktreeCreateResult(
        worktree_path=worktree_path,
        worktree_branch=worktree_branch,
        head_commit=base_sha,
        existed=False,
        base_branch=base_branch,
    )


# ---------------------------------------------------------------------------
# copy_worktree_include_files
# ---------------------------------------------------------------------------

async def copy_worktree_include_files(
    repo_root: str,
    worktree_path: str,
) -> List[str]:
    """
    Copy gitignored files specified in .worktreeinclude from base repo to worktree.
    Returns list of relative paths that were copied.
    原始 TS: copyWorktreeIncludeFiles
    """
    include_file = Path(repo_root) / ".worktreeinclude"
    try:
        include_content = include_file.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return []

    patterns = [
        line.strip()
        for line in include_content.splitlines()
        if line.strip() and not line.strip().startswith('#')
    ]
    if not patterns:
        return []

    gitignored = await exec_file_no_throw(
        _git_exe(),
        ["ls-files", "--others", "--ignored", "--exclude-standard", "--directory"],
        cwd=repo_root,
    )
    if gitignored.code != 0 or not gitignored.stdout.strip():
        return []

    entries = [e for e in gitignored.stdout.strip().split('\n') if e]

    try:
        import ignore as _ignore_lib  # type: ignore[import]
        matcher = _ignore_lib.ignore().add(include_content)
        def _matches(p: str) -> bool:
            return matcher.ignores(p)
    except ImportError:
        # Fallback: basic glob matching using fnmatch
        import fnmatch
        def _matches(p: str) -> bool:  # type: ignore[misc]
            return any(fnmatch.fnmatch(p, pat) for pat in patterns)

    collapsed_dirs = [e for e in entries if e.endswith('/')]
    files = [e for e in entries if not e.endswith('/') and _matches(e)]

    # Expand collapsed dirs that are explicitly targeted by a pattern
    dirs_to_expand = []
    for d in collapsed_dirs:
        should_expand = False
        for p in patterns:
            normalized = p.lstrip('/')
            if normalized.startswith(d):
                should_expand = True
                break
            glob_idx = len(re.split(r'[*?\[]', normalized)[0])
            if glob_idx > 0:
                literal_prefix = normalized[:glob_idx]
                if d.startswith(literal_prefix):
                    should_expand = True
                    break
        if not should_expand and _matches(d.rstrip('/')):
            should_expand = True
        if should_expand:
            dirs_to_expand.append(d)

    if dirs_to_expand:
        expanded = await exec_file_no_throw(
            _git_exe(),
            ["ls-files", "--others", "--ignored", "--exclude-standard", "--", *dirs_to_expand],
            cwd=repo_root,
        )
        if expanded.code == 0 and expanded.stdout.strip():
            for f in expanded.stdout.strip().split('\n'):
                if f and _matches(f):
                    files.append(f)

    import shutil as _shutil
    copied: List[str] = []
    for rel_path in files:
        src = Path(repo_root) / rel_path
        dst = Path(worktree_path) / rel_path
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            _shutil.copy2(str(src), str(dst))
            copied.append(rel_path)
        except Exception as e:
            log_for_debugging(
                f"Failed to copy {rel_path} to worktree: {error_message(e)}",
                level="warn",
            )

    if copied:
        log_for_debugging(
            f"Copied {len(copied)} files from .worktreeinclude: {', '.join(copied)}"
        )

    return copied


# ---------------------------------------------------------------------------
# performPostCreationSetup
# ---------------------------------------------------------------------------

async def _perform_post_creation_setup(repo_root: str, worktree_path: str) -> None:
    """
    Post-creation setup: copy settings.local.json, configure git hooks,
    symlink directories, copy .worktreeinclude files.
    原始 TS: performPostCreationSetup
    """
    # Copy settings.local.json
    local_settings_rel = _get_relative_settings_file_path_for_source("localSettings")
    src_settings = Path(repo_root) / local_settings_rel
    try:
        dst_settings = Path(worktree_path) / local_settings_rel
        dst_settings.parent.mkdir(parents=True, exist_ok=True)
        import shutil as _sh
        _sh.copy2(str(src_settings), str(dst_settings))
        log_for_debugging(f"Copied settings.local.json to worktree: {dst_settings}")
    except OSError as e:
        import errno
        if e.errno != errno.ENOENT:
            log_for_debugging(
                f"Failed to copy settings.local.json: {error_message(e)}",
                level="warn",
            )

    # Configure git hooks path
    husky_path = str(Path(repo_root) / ".husky")
    git_hooks_path = str(Path(repo_root) / ".git" / "hooks")
    hooks_path: Optional[str] = None
    for candidate in (husky_path, git_hooks_path):
        if Path(candidate).is_dir():
            hooks_path = candidate
            break

    if hooks_path:
        git_dir = await _resolve_git_dir(repo_root)
        config_dir = (
            (await _get_common_dir(git_dir)) or git_dir
            if git_dir
            else None
        )
        existing: Optional[str] = None
        if config_dir:
            try:
                existing = await _parse_git_config_value(
                    config_dir, "core", None, "hooksPath"
                )
            except Exception:
                pass

        if existing != hooks_path:
            cfg_result = await exec_file_no_throw(
                _git_exe(),
                ["config", "core.hooksPath", hooks_path],
                cwd=worktree_path,
            )
            if cfg_result.code == 0:
                log_for_debugging(
                    f"Configured worktree to use hooks from main repository: {hooks_path}"
                )
            else:
                log_for_debugging(
                    f"Failed to configure hooks path: {cfg_result.stderr}",
                    level="error",
                )

    # Symlink directories
    settings = _get_initial_settings()
    dirs_to_symlink: List[str] = []
    if settings.worktree:
        dirs_to_symlink = list(getattr(settings.worktree, 'symlink_directories', []) or [])
    if dirs_to_symlink:
        await _symlink_directories(repo_root, worktree_path, dirs_to_symlink)

    # Copy .worktreeinclude files
    await copy_worktree_include_files(repo_root, worktree_path)


# ---------------------------------------------------------------------------
# PR reference parsing
# ---------------------------------------------------------------------------

def parse_pr_reference(input_str: str) -> Optional[int]:
    """
    Parse a PR number from a GitHub PR URL or '#N' format.
    Returns None if not recognised.
    原始 TS: parsePRReference
    """
    url_match = re.match(
        r'^https?://[^/]+/[^/]+/[^/]+/pull/(\d+)/?(?:[?#].*)?$',
        input_str,
        re.IGNORECASE,
    )
    if url_match:
        return int(url_match.group(1))

    hash_match = re.match(r'^#(\d+)$', input_str)
    if hash_match:
        return int(hash_match.group(1))

    return None


# ---------------------------------------------------------------------------
# Tmux helpers
# ---------------------------------------------------------------------------

async def is_tmux_available() -> bool:
    """原始 TS: isTmuxAvailable"""
    result = await exec_file_no_throw("tmux", ["-V"])
    return result.code == 0


def get_tmux_install_instructions() -> str:
    """原始 TS: getTmuxInstallInstructions"""
    p = _get_platform()
    if p == "macos":
        return "Install tmux with: brew install tmux"
    if p in ("linux", "wsl"):
        return (
            "Install tmux with: sudo apt install tmux (Debian/Ubuntu) "
            "or sudo dnf install tmux (Fedora/RHEL)"
        )
    if p == "windows":
        return "tmux is not natively available on Windows. Consider using WSL or Cygwin."
    return "Install tmux using your system package manager."


async def create_tmux_session_for_worktree(
    session_name: str,
    worktree_path: str,
) -> dict:
    """
    Create a detached tmux session.
    Returns {'created': bool, 'error': Optional[str]}
    原始 TS: createTmuxSessionForWorktree
    """
    result = await exec_file_no_throw(
        "tmux",
        ["new-session", "-d", "-s", session_name, "-c", worktree_path],
    )
    if result.code != 0:
        return {"created": False, "error": result.stderr}
    return {"created": True}


async def kill_tmux_session(session_name: str) -> bool:
    """原始 TS: killTmuxSession"""
    result = await exec_file_no_throw("tmux", ["kill-session", "-t", session_name])
    return result.code == 0


# ---------------------------------------------------------------------------
# createWorktreeForSession
# ---------------------------------------------------------------------------

async def create_worktree_for_session(
    session_id: str,
    slug: str,
    tmux_session_name: Optional[str] = None,
    *,
    pr_number: Optional[int] = None,
) -> WorktreeSession:
    """
    Create (or resume) a git worktree for a session.
    原始 TS: createWorktreeForSession
    """
    global _current_worktree_session

    validate_worktree_slug(slug)
    original_cwd = _get_cwd()

    if _has_worktree_create_hook():
        hook_result = await _execute_worktree_create_hook(slug)
        log_for_debugging(f"Created hook-based worktree at: {hook_result.worktree_path}")
        _current_worktree_session = WorktreeSession(
            original_cwd=original_cwd,
            worktree_path=hook_result.worktree_path,
            worktree_name=slug,
            session_id=session_id,
            tmux_session_name=tmux_session_name,
            hook_based=True,
        )
    else:
        git_root = _find_git_root(_get_cwd())
        if not git_root:
            raise RuntimeError(
                "Cannot create a worktree: not in a git repository and no "
                "WorktreeCreate hooks are configured. Configure WorktreeCreate/"
                "WorktreeRemove hooks in settings.json to use worktree isolation "
                "with other VCS systems."
            )

        original_branch = await _get_branch()

        create_start = _now_ms()
        wt = await _get_or_create_worktree(git_root, slug, pr_number=pr_number)

        creation_duration_ms: Optional[int] = None
        if wt.existed:
            log_for_debugging(f"Resuming existing worktree at: {wt.worktree_path}")
        else:
            log_for_debugging(
                f"Created worktree at: {wt.worktree_path} on branch: {wt.worktree_branch}"
            )
            await _perform_post_creation_setup(git_root, wt.worktree_path)
            creation_duration_ms = _now_ms() - create_start

        settings = _get_initial_settings()
        sparse_paths_len = (
            len(settings.worktree.sparse_paths)
            if settings.worktree and settings.worktree.sparse_paths
            else 0
        )

        _current_worktree_session = WorktreeSession(
            original_cwd=original_cwd,
            worktree_path=wt.worktree_path,
            worktree_name=slug,
            worktree_branch=wt.worktree_branch,
            original_branch=original_branch,
            original_head_commit=wt.head_commit,
            session_id=session_id,
            tmux_session_name=tmux_session_name,
            creation_duration_ms=creation_duration_ms,
            used_sparse_paths=(sparse_paths_len > 0) or None,
        )

    _save_current_project_config(
        lambda current: {**current, "activeWorktreeSession": _current_worktree_session}
    )

    return _current_worktree_session


# ---------------------------------------------------------------------------
# keepWorktree / cleanupWorktree
# ---------------------------------------------------------------------------

async def keep_worktree() -> None:
    """Detach the current session without removing the worktree.  原始 TS: keepWorktree"""
    global _current_worktree_session
    if not _current_worktree_session:
        return

    try:
        wt_path = _current_worktree_session.worktree_path
        orig_cwd = _current_worktree_session.original_cwd
        wt_branch = _current_worktree_session.worktree_branch

        os.chdir(orig_cwd)
        _current_worktree_session = None
        _save_current_project_config(
            lambda current: {**current, "activeWorktreeSession": None}
        )
        log_for_debugging(
            f"Linked worktree preserved at: {wt_path}"
            + (f" on branch: {wt_branch}" if wt_branch else "")
        )
        log_for_debugging(
            f"You can continue working there by running: cd {wt_path}"
        )
    except Exception as e:
        log_for_debugging(f"Error keeping worktree: {e}", level="error")


async def cleanup_worktree() -> None:
    """Remove the current worktree and clean up.  原始 TS: cleanupWorktree"""
    global _current_worktree_session
    if not _current_worktree_session:
        return

    try:
        wt_path = _current_worktree_session.worktree_path
        orig_cwd = _current_worktree_session.original_cwd
        wt_branch = _current_worktree_session.worktree_branch
        hook_based = _current_worktree_session.hook_based

        os.chdir(orig_cwd)

        if hook_based:
            hook_ran = await _execute_worktree_remove_hook(wt_path)
            if hook_ran:
                log_for_debugging(f"Removed hook-based worktree at: {wt_path}")
            else:
                log_for_debugging(
                    f"No WorktreeRemove hook configured, hook-based worktree left at: {wt_path}",
                    level="warn",
                )
        else:
            remove_result = await exec_file_no_throw(
                _git_exe(),
                ["worktree", "remove", "--force", wt_path],
                cwd=orig_cwd,
            )
            if remove_result.code != 0:
                log_for_debugging(
                    f"Failed to remove linked worktree: {remove_result.stderr}",
                    level="error",
                )
            else:
                log_for_debugging(f"Removed linked worktree at: {wt_path}")

        _current_worktree_session = None
        _save_current_project_config(
            lambda current: {**current, "activeWorktreeSession": None}
        )

        if not hook_based and wt_branch:
            from .sleep import sleep as _sleep
            await _sleep(100)
            del_result = await exec_file_no_throw(
                _git_exe(),
                ["branch", "-D", wt_branch],
                cwd=orig_cwd,
            )
            if del_result.code != 0:
                log_for_debugging(
                    f"Could not delete worktree branch: {del_result.stderr}",
                    level="error",
                )
            else:
                log_for_debugging(f"Deleted worktree branch: {wt_branch}")

        log_for_debugging("Linked worktree cleaned up completely")

    except Exception as e:
        log_for_debugging(f"Error cleaning up worktree: {e}", level="error")


# ---------------------------------------------------------------------------
# createAgentWorktree / removeAgentWorktree
# ---------------------------------------------------------------------------

async def create_agent_worktree(slug: str) -> dict:
    """
    Create a lightweight worktree for a subagent (does not touch global state).
    Returns dict with keys: worktree_path, worktree_branch, head_commit, git_root, hook_based.
    原始 TS: createAgentWorktree
    """
    validate_worktree_slug(slug)

    if _has_worktree_create_hook():
        hook_result = await _execute_worktree_create_hook(slug)
        log_for_debugging(f"Created hook-based agent worktree at: {hook_result.worktree_path}")
        return {"worktree_path": hook_result.worktree_path, "hook_based": True}

    git_root = _find_canonical_git_root(_get_cwd())
    if not git_root:
        raise RuntimeError(
            "Cannot create agent worktree: not in a git repository and no "
            "WorktreeCreate hooks are configured. Configure WorktreeCreate/"
            "WorktreeRemove hooks in settings.json to use worktree isolation "
            "with other VCS systems."
        )

    wt = await _get_or_create_worktree(git_root, slug)

    if not wt.existed:
        log_for_debugging(
            f"Created agent worktree at: {wt.worktree_path} on branch: {wt.worktree_branch}"
        )
        await _perform_post_creation_setup(git_root, wt.worktree_path)
    else:
        # Bump mtime so stale-cleanup doesn't reclaim an active worktree
        now = datetime.now()
        wt_path = Path(wt.worktree_path)
        if wt_path.exists():
            import os as _os
            ts = now.timestamp()
            _os.utime(str(wt_path), (ts, ts))
        log_for_debugging(f"Resuming existing agent worktree at: {wt.worktree_path}")

    return {
        "worktree_path": wt.worktree_path,
        "worktree_branch": wt.worktree_branch,
        "head_commit": wt.head_commit,
        "git_root": git_root,
    }


async def remove_agent_worktree(
    worktree_path: str,
    worktree_branch: Optional[str] = None,
    git_root: Optional[str] = None,
    hook_based: Optional[bool] = None,
) -> bool:
    """
    Remove a worktree created by create_agent_worktree.
    原始 TS: removeAgentWorktree
    """
    if hook_based:
        hook_ran = await _execute_worktree_remove_hook(worktree_path)
        if hook_ran:
            log_for_debugging(f"Removed hook-based agent worktree at: {worktree_path}")
        else:
            log_for_debugging(
                f"No WorktreeRemove hook configured, hook-based agent worktree left at: {worktree_path}",
                level="warn",
            )
        return hook_ran

    if not git_root:
        log_for_debugging(
            "Cannot remove agent worktree: no git root provided",
            level="error",
        )
        return False

    remove_result = await exec_file_no_throw(
        _git_exe(),
        ["worktree", "remove", "--force", worktree_path],
        cwd=git_root,
    )
    if remove_result.code != 0:
        log_for_debugging(
            f"Failed to remove agent worktree: {remove_result.stderr}",
            level="error",
        )
        return False
    log_for_debugging(f"Removed agent worktree at: {worktree_path}")

    if not worktree_branch:
        return True

    del_result = await exec_file_no_throw(
        _git_exe(),
        ["branch", "-D", worktree_branch],
        cwd=git_root,
    )
    if del_result.code != 0:
        log_for_debugging(
            f"Could not delete agent worktree branch: {del_result.stderr}",
            level="error",
        )
    return True


# ---------------------------------------------------------------------------
# cleanupStaleAgentWorktrees
# ---------------------------------------------------------------------------

async def cleanup_stale_agent_worktrees(cutoff_date: datetime) -> int:
    """
    Remove ephemeral agent/workflow worktrees older than cutoff_date.
    Returns the number of worktrees removed.
    原始 TS: cleanupStaleAgentWorktrees
    """
    git_root = _find_canonical_git_root(_get_cwd())
    if not git_root:
        return 0

    wt_dir = _worktrees_dir(git_root)
    try:
        entries = list(os.listdir(wt_dir))
    except OSError:
        return 0

    cutoff_ms = cutoff_date.timestamp() * 1000
    current_path = (
        _current_worktree_session.worktree_path if _current_worktree_session else None
    )
    removed = 0

    for slug in entries:
        if not any(p.match(slug) for p in _EPHEMERAL_WORKTREE_PATTERNS):
            continue

        wt_path = str(Path(wt_dir) / slug)
        if current_path == wt_path:
            continue

        try:
            mtime_ms = os.stat(wt_path).st_mtime * 1000
        except OSError:
            continue
        if mtime_ms >= cutoff_ms:
            continue

        # Safety: skip if there are uncommitted changes or unpushed commits
        status, unpushed = await asyncio.gather(
            exec_file_no_throw(
                _git_exe(),
                ["--no-optional-locks", "status", "--porcelain", "-uno"],
                cwd=wt_path,
            ),
            exec_file_no_throw(
                _git_exe(),
                ["rev-list", "--max-count=1", "HEAD", "--not", "--remotes"],
                cwd=wt_path,
            ),
        )
        if status.code != 0 or status.stdout.strip():
            continue
        if unpushed.code != 0 or unpushed.stdout.strip():
            continue

        if await remove_agent_worktree(wt_path, worktree_branch_name(slug), git_root):
            removed += 1

    if removed > 0:
        await exec_file_no_throw(_git_exe(), ["worktree", "prune"], cwd=git_root)
        log_for_debugging(
            f"cleanupStaleAgentWorktrees: removed {removed} stale worktree(s)"
        )
    return removed


# ---------------------------------------------------------------------------
# hasWorktreeChanges
# ---------------------------------------------------------------------------

async def has_worktree_changes(
    worktree_path: str,
    head_commit: str,
) -> bool:
    """
    Return True if the worktree has uncommitted changes or new commits since head_commit.
    Fail-closed: returns True on git errors.
    原始 TS: hasWorktreeChanges
    """
    status_result = await exec_file_no_throw(
        _git_exe(),
        ["status", "--porcelain"],
        cwd=worktree_path,
    )
    if status_result.code != 0:
        return True
    if status_result.stdout.strip():
        return True

    rev_list_result = await exec_file_no_throw(
        _git_exe(),
        ["rev-list", "--count", f"{head_commit}..HEAD"],
        cwd=worktree_path,
    )
    if rev_list_result.code != 0:
        return True
    try:
        if int(rev_list_result.stdout.strip()) > 0:
            return True
    except ValueError:
        return True

    return False


# ---------------------------------------------------------------------------
# execIntoTmuxWorktree
# ---------------------------------------------------------------------------

async def exec_into_tmux_worktree(args: List[str]) -> dict:
    """
    Fast-path handler for --worktree --tmux.
    Returns {'handled': bool, 'error': Optional[str]}
    原始 TS: execIntoTmuxWorktree
    """
    if sys.platform == "win32":
        return {"handled": False, "error": "Error: --tmux is not supported on Windows"}

    tmux_check = subprocess.run(
        ["tmux", "-V"], capture_output=True, text=True
    )
    if tmux_check.returncode != 0:
        install_hint = (
            "Install tmux with: brew install tmux"
            if sys.platform == "darwin"
            else "Install tmux with: sudo apt install tmux"
        )
        return {
            "handled": False,
            "error": f"Error: tmux is not installed. {install_hint}",
        }

    # Parse --worktree and --tmux args
    worktree_name: Optional[str] = None
    force_classic_tmux = False
    i = 0
    while i < len(args):
        arg = args[i]
        if not arg:
            i += 1
            continue
        if arg in ("-w", "--worktree"):
            if i + 1 < len(args) and not args[i + 1].startswith("-"):
                worktree_name = args[i + 1]
        elif arg.startswith("--worktree="):
            worktree_name = arg[len("--worktree="):]
        elif arg == "--tmux=classic":
            force_classic_tmux = True
        i += 1

    # Check for PR reference
    pr_number: Optional[int] = None
    if worktree_name:
        pr_number = parse_pr_reference(worktree_name)
        if pr_number is not None:
            worktree_name = f"pr-{pr_number}"

    # Generate random slug if none provided
    if not worktree_name:
        adjectives = ["swift", "bright", "calm", "keen", "bold"]
        nouns = ["fox", "owl", "elm", "oak", "ray"]
        adj = random.choice(adjectives)
        noun = random.choice(nouns)
        suffix = "%04x" % random.randint(0, 0xFFFF)
        worktree_name = f"{adj}-{noun}-{suffix}"

    try:
        validate_worktree_slug(worktree_name)
    except ValueError as e:
        return {"handled": False, "error": f"Error: {e}"}

    # Create or resume the worktree
    worktree_dir: str
    repo_name: str
    if _has_worktree_create_hook():
        try:
            hook_result = await _execute_worktree_create_hook(worktree_name)
            worktree_dir = hook_result.worktree_path
        except Exception as e:
            return {"handled": False, "error": f"Error: {error_message(e)}"}
        canonical = _find_canonical_git_root(_get_cwd())
        repo_name = Path(canonical or _get_cwd()).name
        print(f"Using worktree via hook: {worktree_dir}")
    else:
        repo_root = _find_canonical_git_root(_get_cwd())
        if not repo_root:
            return {"handled": False, "error": "Error: --worktree requires a git repository"}
        repo_name = Path(repo_root).name
        worktree_dir = _worktree_path_for(repo_root, worktree_name)

        try:
            result = await _get_or_create_worktree(
                repo_root,
                worktree_name,
                pr_number=pr_number,
            )
            if not result.existed:
                print(
                    f"Created worktree: {worktree_dir} "
                    f"(based on {result.base_branch})"
                )
                await _perform_post_creation_setup(repo_root, worktree_dir)
        except Exception as e:
            return {"handled": False, "error": f"Error: {error_message(e)}"}

    tmux_session_name = re.sub(
        r'[/.]', '_', f"{repo_name}_{worktree_branch_name(worktree_name)}"
    )

    # Strip --tmux / --worktree from forwarded args
    new_args: List[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if not arg:
            i += 1
            continue
        if arg in ("--tmux", "--tmux=classic"):
            i += 1
            continue
        if arg in ("-w", "--worktree"):
            if i + 1 < len(args) and not args[i + 1].startswith("-"):
                i += 2
            else:
                i += 1
            continue
        if arg.startswith("--worktree="):
            i += 1
            continue
        new_args.append(arg)
        i += 1

    # Determine tmux prefix
    tmux_prefix = "C-b"
    prefix_result = subprocess.run(
        ["tmux", "show-options", "-g", "prefix"],
        capture_output=True, text=True,
    )
    if prefix_result.returncode == 0 and prefix_result.stdout:
        m = re.search(r'prefix\s+(\S+)', prefix_result.stdout)
        if m:
            tmux_prefix = m.group(1)

    claude_bindings = ["C-b", "C-c", "C-d", "C-t", "C-o", "C-r", "C-s", "C-g", "C-e"]
    prefix_conflicts = tmux_prefix in claude_bindings

    tmux_env = {
        **os.environ,
        "CLAUDE_CODE_TMUX_SESSION": tmux_session_name,
        "CLAUDE_CODE_TMUX_PREFIX": tmux_prefix,
        "CLAUDE_CODE_TMUX_PREFIX_CONFLICTS": "1" if prefix_conflicts else "",
    }

    # Check for existing session
    has_session = subprocess.run(
        ["tmux", "has-session", "-t", tmux_session_name],
        capture_output=True, text=True,
    )
    session_exists = has_session.returncode == 0
    is_already_in_tmux = bool(os.environ.get("TMUX"))

    # Note: isInITerm2 detection is platform-specific; simplified here
    use_control_mode = False  # simplified: skip iTerm2 detection
    tmux_global_args: List[str] = ["-CC"] if use_control_mode else []

    python_exe = sys.executable

    if is_already_in_tmux:
        if session_exists:
            subprocess.run(["tmux", "switch-client", "-t", tmux_session_name])
        else:
            subprocess.run(
                [
                    "tmux", "new-session", "-d", "-s", tmux_session_name,
                    "-c", worktree_dir, "--", python_exe, *new_args,
                ],
                cwd=worktree_dir, env=tmux_env,
            )
            subprocess.run(["tmux", "switch-client", "-t", tmux_session_name])
    else:
        tmux_args = [
            *tmux_global_args,
            "new-session", "-A", "-s", tmux_session_name,
            "-c", worktree_dir, "--", python_exe, *new_args,
        ]
        subprocess.run(
            ["tmux", *tmux_args],
            cwd=worktree_dir, env=tmux_env,
        )

    return {"handled": True}


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------

def _now_ms() -> int:
    """Return current time in milliseconds."""
    import time
    return int(time.time() * 1000)


def log_for_debugging(msg: str, *, level: str = "info") -> None:  # type: ignore[misc]
    """Thin wrapper — delegates to debug.log_for_debugging if available."""
    try:
        _debug_log(msg, level=level)
    except Exception:
        pass
