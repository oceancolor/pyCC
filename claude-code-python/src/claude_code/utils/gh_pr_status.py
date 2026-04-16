"""GitHub PR status - Python port of ghPrStatus.ts.

Fetches PR status for the current branch via the `gh` CLI.
Returns None on any failure (gh not installed, no PR, not in a git repo, etc.).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Literal, Optional

PrReviewState = Literal['approved', 'pending', 'changes_requested', 'draft', 'merged', 'closed']

GH_TIMEOUT_S = 5  # seconds


@dataclass
class PrStatus:
    number: int
    url: str
    review_state: PrReviewState


def derive_review_state(is_draft: bool, review_decision: str) -> PrReviewState:
    """Map GitHub API values to a PrReviewState.

    Draft PRs always return 'draft'.
    review_decision: APPROVED | CHANGES_REQUESTED | REVIEW_REQUIRED | ''
    """
    if is_draft:
        return 'draft'
    if review_decision == 'APPROVED':
        return 'approved'
    if review_decision == 'CHANGES_REQUESTED':
        return 'changes_requested'
    return 'pending'


def _run_git(args: list[str]) -> Optional[str]:
    """Run a git command and return stripped stdout, or None on failure."""
    try:
        result = subprocess.run(
            ['git'] + args,
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT_S,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _get_branch() -> Optional[str]:
    return _run_git(['rev-parse', '--abbrev-ref', 'HEAD'])


def _get_default_branch() -> Optional[str]:
    """Try to determine the default branch (main/master/…)."""
    remote_head = _run_git(['symbolic-ref', 'refs/remotes/origin/HEAD'])
    if remote_head:
        return remote_head.split('/')[-1]
    # Fallback: check common names
    for name in ('main', 'master'):
        if _run_git(['show-ref', '--verify', f'refs/heads/{name}']) is not None:
            return name
    return None


def _is_git() -> bool:
    return _run_git(['rev-parse', '--is-inside-work-tree']) == 'true'


def fetch_pr_status() -> Optional[PrStatus]:
    """Fetch PR status for the current branch.

    Returns None on any failure or when on the default branch.
    """
    if not _is_git():
        return None

    branch = _get_branch()
    default_branch = _get_default_branch()

    if branch is None or branch == default_branch:
        return None

    try:
        result = subprocess.run(
            [
                'gh', 'pr', 'view',
                '--json', 'number,url,reviewDecision,isDraft,headRefName,state',
            ],
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None

    if result.returncode != 0 or not result.stdout.strip():
        return None

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    head_ref = data.get('headRefName', '')
    if head_ref in (default_branch, 'main', 'master'):
        return None

    state = data.get('state', '')
    if state in ('MERGED', 'CLOSED'):
        return None

    return PrStatus(
        number=data['number'],
        url=data['url'],
        review_state=derive_review_state(data.get('isDraft', False), data.get('reviewDecision', '')),
    )


# Convenience alias matching TS export name
get_pr_status = fetch_pr_status
