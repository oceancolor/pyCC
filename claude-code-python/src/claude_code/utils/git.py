"""
Git utilities. Ported from utils/git.ts (926 lines).

Provides git repository detection, branch info, remote URL, worktree state,
file status, and related helpers.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, TypedDict

_GIT_ROOT_NOT_FOUND = object()

# ---------------------------------------------------------------------------
# LRU caches (module-level)
# ---------------------------------------------------------------------------
_find_git_root_cache: Dict[str, Optional[str]] = {}
_canonical_git_root_cache: Dict[str, Optional[str]] = {}


def find_git_root(start_path: Optional[str] = None) -> Optional[str]:
    """Find the git root by walking up the directory tree.

    Looks for a .git directory or file (worktrees/submodules use a file).
    Returns the directory containing .git, or None if not found.
    Memoized per start_path (LRU, max 50 entries).

    Ported from findGitRoot (TS line 30).
    """
    start = os.path.realpath(start_path or os.getcwd())

    if start in _find_git_root_cache:
        return _find_git_root_cache[start]

    current = start
    while True:
        git_path = os.path.join(current, ".git")
        if os.path.exists(git_path):
            result = current
            _find_git_root_cache[start] = result
            return result

        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    _find_git_root_cache[start] = None
    return None


def _resolve_canonical_root(git_root: str) -> str:
    """Resolve a git root to the canonical main repository root.

    For a regular repo this is a no-op. For a worktree, follows the
    `.git` file → `gitdir:` → `commondir` chain to find the main repo.

    Ported from resolveCanonicalRoot (TS line 121).
    """
    try:
        git_file = os.path.join(git_root, ".git")
        with open(git_file, "r", encoding="utf-8") as f:
            git_content = f.read().strip()

        if not git_content.startswith("gitdir:"):
            return git_root

        worktree_git_dir = os.path.realpath(
            os.path.join(git_root, git_content[len("gitdir:"):].strip())
        )

        # Read commondir (only exists for worktrees, not submodules)
        commondir_file = os.path.join(worktree_git_dir, "commondir")
        with open(commondir_file, "r", encoding="utf-8") as f:
            common_rel = f.read().strip()

        common_dir = os.path.realpath(
            os.path.join(worktree_git_dir, common_rel)
        )

        # Security validation: worktreeGitDir must be a direct child of <commonDir>/worktrees/
        if os.path.realpath(os.path.dirname(worktree_git_dir)) != os.path.join(common_dir, "worktrees"):
            return git_root

        # Validate back-link: gitdir must point back to <gitRoot>/.git
        gitdir_file = os.path.join(worktree_git_dir, "gitdir")
        with open(gitdir_file, "r", encoding="utf-8") as f:
            backlink = os.path.realpath(f.read().strip())

        if backlink != os.path.join(os.path.realpath(git_root), ".git"):
            return git_root

        # Bare-repo worktrees: the common dir isn't inside a working directory.
        if os.path.basename(common_dir) != ".git":
            return common_dir

        return os.path.dirname(common_dir)

    except (OSError, IOError):
        return git_root


def find_canonical_git_root(start_path: Optional[str] = None) -> Optional[str]:
    """Find the canonical git repository root, resolving through worktrees.

    Unlike find_git_root, returns the main repository's working directory.
    All worktrees of the same repo map to the same project identity.

    Ported from findCanonicalGitRoot (TS line 200).
    """
    start = os.path.realpath(start_path or os.getcwd())

    if start in _canonical_git_root_cache:
        return _canonical_git_root_cache[start]

    root = find_git_root(start)
    if not root:
        _canonical_git_root_cache[start] = None
        return None

    result = _resolve_canonical_root(root)
    _canonical_git_root_cache[start] = result
    return result


@lru_cache(maxsize=1)
def git_exe() -> str:
    """Get the git executable path (cached).

    Ported from gitExe (TS line 214).
    """
    import shutil
    path = shutil.which("git")
    return path or "git"


@lru_cache(maxsize=1)
def get_is_git(cwd: Optional[str] = None) -> bool:
    """Check if the current working directory is inside a git repository.

    Ported from getIsGit (TS line 219).
    """
    return find_git_root(cwd or os.getcwd()) is not None


def get_git_dir(cwd: str) -> Optional[str]:
    """Get the .git directory path for the given directory.

    Ported from getGitDir (TS line 233).
    """
    try:
        result = subprocess.run(
            [git_exe(), "rev-parse", "--git-dir"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            git_dir = result.stdout.strip()
            if os.path.isabs(git_dir):
                return git_dir
            return os.path.realpath(os.path.join(cwd, git_dir))
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def is_at_git_root(cwd: Optional[str] = None) -> bool:
    """Check if the current directory is the git root.

    Ported from isAtGitRoot (TS line 237).
    """
    current = cwd or os.getcwd()
    git_root = find_git_root(current)
    if not git_root:
        return False
    try:
        return os.path.realpath(current) == os.path.realpath(git_root)
    except OSError:
        return current == git_root


def dir_is_in_git_repo(cwd: str) -> bool:
    """Check if the given directory is inside a git repository."""
    return find_git_root(cwd) is not None


def get_head(cwd: Optional[str] = None) -> Optional[str]:
    """Get the current HEAD commit hash.

    Ported from getHead (TS line 253).
    """
    try:
        result = subprocess.run(
            [git_exe(), "rev-parse", "HEAD"],
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def get_branch(cwd: Optional[str] = None) -> Optional[str]:
    """Get the current git branch name.

    Ported from getBranch (TS line 257).
    """
    try:
        result = subprocess.run(
            [git_exe(), "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def get_default_branch(cwd: Optional[str] = None) -> Optional[str]:
    """Get the default branch of the repository (main/master/etc.).

    Ported from getDefaultBranch (TS line 261).
    """
    work_dir = cwd or os.getcwd()
    # Try to get the remote's default branch
    try:
        result = subprocess.run(
            [git_exe(), "remote", "show", "origin"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            match = re.search(r"HEAD branch: (\S+)", result.stdout)
            if match:
                return match.group(1)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Fallback: check for symbolic ref origin/HEAD
    try:
        result = subprocess.run(
            [git_exe(), "symbolic-ref", "refs/remotes/origin/HEAD", "--short"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            ref = result.stdout.strip()
            # Strip "origin/" prefix
            if ref.startswith("origin/"):
                return ref[len("origin/"):]
            return ref
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Fallback to common default branch names
    for candidate in ("main", "master", "develop"):
        try:
            result = subprocess.run(
                [git_exe(), "rev-parse", "--verify", f"origin/{candidate}"],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return candidate
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    return None


def get_remote_url(cwd: Optional[str] = None) -> Optional[str]:
    """Get the remote URL of the git repo.

    Ported from getRemoteUrl (TS line 265).
    """
    try:
        result = subprocess.run(
            [git_exe(), "remote", "get-url", "origin"],
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def normalize_git_remote_url(url: str) -> Optional[str]:
    """Normalize a git remote URL to a canonical form for hashing.

    Converts SSH and HTTPS URLs to: host/owner/repo (lowercase, no .git).

    Examples:
        git@github.com:owner/repo.git → github.com/owner/repo
        https://github.com/owner/repo.git → github.com/owner/repo
        ssh://git@github.com/owner/repo → github.com/owner/repo

    Ported from normalizeGitRemoteUrl (TS line 275).
    """
    trimmed = url.strip()
    if not trimmed:
        return None

    # Handle SSH format: git@host:owner/repo.git
    ssh_match = re.match(r"^git@([^:]+):(.+?)(?:\.git)?$", trimmed)
    if ssh_match:
        host, path = ssh_match.group(1), ssh_match.group(2)
        return f"{host}/{path}".lower()

    # Handle HTTPS/SSH URL format: https://host/owner/repo.git
    url_match = re.match(
        r"^(?:https?|ssh)://(?:[^@]+@)?([^/]+)/(.+?)(?:\.git)?$", trimmed
    )
    if url_match:
        host, path = url_match.group(1), url_match.group(2)

        # Handle CCR git proxy URLs (localhost)
        if _is_local_host(host) and path.startswith("git/"):
            proxy_path = path[4:]  # Remove "git/" prefix
            segments = proxy_path.split("/")
            # 3+ segments where first contains a dot → GHE format
            if len(segments) >= 3 and "." in segments[0]:
                return proxy_path.lower()
            # 2 segments → legacy format, assume github.com
            return f"github.com/{proxy_path}".lower()

        return f"{host}/{path}".lower()

    return None


def _is_local_host(host: str) -> bool:
    """Check if host is localhost/127.x.x.x."""
    return host in ("localhost", "127.0.0.1") or host.startswith("127.")


def get_repo_remote_hash(cwd: Optional[str] = None) -> Optional[str]:
    """Get a SHA256 hash (first 16 chars) of the normalized git remote URL.

    Provides a globally unique identifier for the repository that is the same
    regardless of SSH vs HTTPS clone.

    Ported from getRepoRemoteHash (TS line 328).
    """
    remote_url = get_remote_url(cwd)
    if not remote_url:
        return None

    normalized = normalize_git_remote_url(remote_url)
    if not normalized:
        return None

    hash_value = hashlib.sha256(normalized.encode()).hexdigest()
    return hash_value[:16]


def get_is_clean(cwd: Optional[str] = None, ignore_untracked: bool = False) -> bool:
    """Check if the working tree is clean (no changes).

    Ported from getIsClean (TS line 353).
    """
    args = [git_exe(), "--no-optional-locks", "status", "--porcelain"]
    if ignore_untracked:
        args.append("-uno")

    try:
        result = subprocess.run(
            args,
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return len(result.stdout.strip()) == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return False


def get_changed_files(cwd: Optional[str] = None) -> List[str]:
    """Get a list of changed file paths.

    Ported from getChangedFiles (TS line 365).
    """
    try:
        result = subprocess.run(
            [git_exe(), "--no-optional-locks", "status", "--porcelain"],
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            files = []
            for line in lines:
                if not line:
                    continue
                parts = line.strip().split(" ", 1)
                if len(parts) == 2 and parts[1]:
                    files.append(parts[1].strip())
            return files
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return []


class GitFileStatus(TypedDict):
    """Git file status split by tracked/untracked."""
    tracked: List[str]
    untracked: List[str]


def get_file_status(cwd: Optional[str] = None) -> GitFileStatus:
    """Get file status split into tracked and untracked files.

    Ported from getFileStatus (TS line 377).
    """
    tracked: List[str] = []
    untracked: List[str] = []

    try:
        result = subprocess.run(
            [git_exe(), "--no-optional-locks", "status", "--porcelain"],
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                status = line[:2]
                filename = line[2:].strip()

                if status == "??":
                    untracked.append(filename)
                elif filename:
                    tracked.append(filename)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return {"tracked": tracked, "untracked": untracked}


def get_worktree_count(cwd: Optional[str] = None) -> int:
    """Get the number of git worktrees.

    Ported from getWorktreeCount (TS line 420).
    """
    try:
        result = subprocess.run(
            [git_exe(), "worktree", "list", "--porcelain"],
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            # Count "worktree " lines, one per worktree
            count = sum(
                1 for line in result.stdout.split("\n")
                if line.startswith("worktree ")
            )
            return max(count, 1)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return 1


# ---------------------------------------------------------------------------
# Legacy aliases (keep for backward compatibility)
# ---------------------------------------------------------------------------

def find_git_root_legacy(start_path: Optional[str] = None) -> Optional[str]:
    """Alias for find_git_root (backward compat)."""
    return find_git_root(start_path)


def get_git_branch(cwd: Optional[str] = None) -> Optional[str]:
    """Alias for get_branch (backward compat)."""
    return get_branch(cwd)


def get_git_remote_url(cwd: Optional[str] = None) -> Optional[str]:
    """Alias for get_remote_url (backward compat)."""
    return get_remote_url(cwd)


def get_git_head(cwd: Optional[str] = None) -> Optional[str]:
    """Alias for get_head (backward compat)."""
    return get_head(cwd)


def is_git_repo(path: Optional[str] = None) -> bool:
    """Alias for get_is_git (backward compat)."""
    return get_is_git(path)
