"""
GitHub repository path mapping utilities.
Port of githubRepoPathMapping.ts — track and validate local clones of GitHub repos.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config storage (lightweight, independent of full config module)
# ---------------------------------------------------------------------------

def _config_path() -> Path:
    env_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(env_dir) if env_dir else Path.home() / ".claude"
    return base / "config.json"


def _load_config() -> dict:
    try:
        return json.loads(_config_path().read_text("utf-8"))
    except Exception:
        return {}


def _save_config(data: dict) -> None:
    try:
        _config_path().parent.mkdir(parents=True, exist_ok=True)
        _config_path().write_text(json.dumps(data, indent=2), "utf-8")
    except Exception as exc:
        logger.debug("Failed to save config: %s", exc)


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class GitHubRepoMapping:
    """Represents a mapping between a GitHub repo and a local clone path."""
    owner: str
    repo: str
    local_path: Path
    remote_url: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

_GITHUB_RE = re.compile(
    r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", re.IGNORECASE
)


def _find_git_root(cwd: Path) -> Optional[Path]:
    """Walk up from *cwd* to find the .git directory."""
    current = cwd
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _get_remote_url(cwd: Path) -> Optional[str]:
    """Return the 'origin' remote URL for the git repo at *cwd*."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def parse_github_repo(remote_url: str) -> Optional[tuple[str, str]]:
    """Parse a GitHub remote URL and return (owner, repo), or *None*."""
    m = _GITHUB_RE.search(remote_url)
    if not m:
        return None
    return m.group(1), m.group(2)


def detect_github_repo(cwd: Optional[Path] = None) -> Optional[GitHubRepoMapping]:
    """Detect the GitHub repository for the current working directory.

    Returns a :class:`GitHubRepoMapping` or *None* if not in a GitHub repo.
    """
    cwd = cwd or Path.cwd()
    git_root = _find_git_root(cwd) or cwd
    remote_url = _get_remote_url(git_root)
    if not remote_url:
        return None
    parsed = parse_github_repo(remote_url)
    if not parsed:
        return None
    owner, repo = parsed
    return GitHubRepoMapping(
        owner=owner,
        repo=repo,
        local_path=git_root,
        remote_url=remote_url,
    )


# ---------------------------------------------------------------------------
# Config-backed path tracking
# ---------------------------------------------------------------------------

def update_github_repo_path_mapping(cwd: Optional[Path] = None) -> None:
    """Non-blocking startup call to track the current repo's local path."""
    try:
        mapping = detect_github_repo(cwd)
        if not mapping:
            logger.debug("Not in a GitHub repository, skipping path mapping update")
            return

        try:
            current_path = str(mapping.local_path.resolve())
        except Exception:
            current_path = str(mapping.local_path)

        repo_key = mapping.full_name.lower()
        config = _load_config()
        existing: list[str] = (config.get("githubRepoPaths") or {}).get(repo_key, [])

        if existing and existing[0] == current_path:
            logger.debug("Path %s already tracked for repo %s", current_path, repo_key)
            return

        updated = [current_path] + [p for p in existing if p != current_path]
        if "githubRepoPaths" not in config:
            config["githubRepoPaths"] = {}
        config["githubRepoPaths"][repo_key] = updated
        _save_config(config)
        logger.debug("Added %s to tracked paths for repo %s", current_path, repo_key)
    except Exception as exc:
        logger.debug("Error updating repo path mapping: %s", exc)


def get_known_paths_for_repo(repo: str) -> list[str]:
    """Return known local paths for *repo* (``owner/repo`` format)."""
    config = _load_config()
    return (config.get("githubRepoPaths") or {}).get(repo.lower(), [])


def filter_existing_paths(paths: list[str]) -> list[str]:
    """Return only those *paths* that exist on the filesystem."""
    return [p for p in paths if Path(p).exists()]


def validate_repo_at_path(path: str, expected_repo: str) -> bool:
    """Return *True* if the git repo at *path* has *expected_repo* as its origin."""
    remote_url = _get_remote_url(Path(path))
    if not remote_url:
        return False
    parsed = parse_github_repo(remote_url)
    if not parsed:
        return False
    actual = "/".join(parsed).lower()
    return actual == expected_repo.lower()


def remove_path_from_repo(repo: str, path_to_remove: str) -> None:
    """Remove *path_to_remove* from the tracked paths for *repo*."""
    config = _load_config()
    repo_key = repo.lower()
    paths = config.get("githubRepoPaths") or {}
    existing: list[str] = paths.get(repo_key, [])
    updated = [p for p in existing if p != path_to_remove]
    if len(updated) == len(existing):
        return
    if not updated:
        paths.pop(repo_key, None)
    else:
        paths[repo_key] = updated
    config["githubRepoPaths"] = paths
    _save_config(config)
    logger.debug("Removed %s from tracked paths for repo %s", path_to_remove, repo_key)
