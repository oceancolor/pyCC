"""
git_operation_tracking.py — Shell-agnostic git operation tracking.

Ported from tools/shared/gitOperationTracking.ts.

Detects `git commit`, `git push`, `gh pr create`, `glab mr create`, and
curl-based PR creation in command strings, extracting structured info for
the collapsed tool-use summary ("committed a1b2c3, created PR #42").
"""
from __future__ import annotations

import re
from typing import Dict, List, Literal, Optional, Tuple, TypedDict

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

CommitKind = Literal["committed", "amended", "cherry-picked"]
BranchAction = Literal["merged", "rebased"]
PrAction = Literal["created", "edited", "merged", "commented", "closed", "ready"]


class CommitInfo(TypedDict):
    sha: str
    kind: CommitKind


class PushInfo(TypedDict):
    branch: str


class BranchInfo(TypedDict):
    ref: str
    action: BranchAction


class PrInfo(TypedDict, total=False):
    number: int
    url: str
    action: PrAction


class GitOperationResult(TypedDict, total=False):
    commit: CommitInfo
    push: PushInfo
    branch: BranchInfo
    pr: PrInfo


# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

def _git_cmd_re(subcmd: str, suffix: str = "") -> re.Pattern:
    """
    Build a regex that matches `git <subcmd>` while tolerating git's global
    options between `git` and the subcommand (e.g. `-c key=val`, `-C path`,
    `--git-dir=path`).
    """
    return re.compile(
        r"\bgit(?:\s+-[cC]\s+\S+|\s+--\S+=\S+)*\s+" + subcmd + r"\b" + suffix
    )


_GIT_COMMIT_RE = _git_cmd_re("commit")
_GIT_PUSH_RE = _git_cmd_re("push")
_GIT_CHERRY_PICK_RE = _git_cmd_re("cherry-pick")
_GIT_MERGE_RE = _git_cmd_re("merge", r"(?!-)")
_GIT_REBASE_RE = _git_cmd_re("rebase")

_GH_PR_ACTIONS: List[Tuple[re.Pattern, PrAction, str]] = [
    (re.compile(r"\bgh\s+pr\s+create\b"), "created", "pr_create"),
    (re.compile(r"\bgh\s+pr\s+edit\b"), "edited", "pr_edit"),
    (re.compile(r"\bgh\s+pr\s+merge\b"), "merged", "pr_merge"),
    (re.compile(r"\bgh\s+pr\s+comment\b"), "commented", "pr_comment"),
    (re.compile(r"\bgh\s+pr\s+close\b"), "closed", "pr_close"),
    (re.compile(r"\bgh\s+pr\s+ready\b"), "ready", "pr_ready"),
]


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_git_commit_id(stdout: str) -> Optional[str]:
    """
    Parse a commit SHA from `git commit` output.
    Format: "[branch abc1234] message" or "[branch (root-commit) abc1234] message"
    """
    match = re.search(r"\[[\w./-]+(?:\s+\(root-commit\))?\s+([0-9a-f]+)\]", stdout)
    return match.group(1) if match else None


def _parse_git_push_branch(output: str) -> Optional[str]:
    """
    Parse branch name from git push output.
    Handles formats like:
      " * [new branch]  branch -> branch"
      "   abc..def  branch -> branch"
      " + abc...def  branch -> branch (forced update)"
    """
    match = re.search(
        r"^\s*[+\-*!= ]?\s*(?:\[new branch\]|\S+\.\.+\S+)\s+\S+\s*->\s*(\S+)",
        output,
        re.MULTILINE,
    )
    return match.group(1) if match else None


def _parse_pr_number_from_text(stdout: str) -> Optional[int]:
    """
    gh pr merge/close/ready print "✓ <Verb> pull request owner/repo#1234".
    Extract the PR number from that text.
    """
    match = re.search(r"[Pp]ull request (?:\S+#)?#?(\d+)", stdout)
    return int(match.group(1)) if match else None


def _parse_ref_from_command(command: str, verb: str) -> Optional[str]:
    """
    Extract target ref from `git merge <ref>` / `git rebase <ref>` command.
    Skips flags and keywords — first non-flag argument is the ref.
    """
    parts = _git_cmd_re(verb).split(command, maxsplit=1)
    if len(parts) < 2:
        return None
    after = parts[1].strip()
    for token in after.split():
        if re.match(r"^[&|;><]", token):
            break
        if token.startswith("-"):
            continue
        return token
    return None


def _parse_pr_url(url: str) -> Optional[Dict]:
    """
    Parse PR info from a GitHub PR URL.
    Returns {"prNumber": int, "prUrl": str, "prRepository": str} or None.
    """
    match = re.search(r"https://github\.com/([^/]+/[^/]+)/pull/(\d+)", url)
    if match and match.group(1) and match.group(2):
        return {
            "prNumber": int(match.group(2)),
            "prUrl": url,
            "prRepository": match.group(1),
        }
    return None


def _find_pr_in_stdout(stdout: str) -> Optional[Dict]:
    """Find a GitHub PR URL embedded anywhere in stdout and parse it."""
    match = re.search(
        r"https://github\.com/[^/\s]+/[^/\s]+/pull/\d+", stdout
    )
    return _parse_pr_url(match.group(0)) if match else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_git_operation(command: str, output: str) -> GitOperationResult:
    """
    Scan bash command + output for git operations worth surfacing in the
    collapsed tool-use summary ("committed a1b2c3, created PR #42, ran 3
    bash commands").

    Checks the command to avoid matching SHAs/URLs in unrelated output
    (e.g. `git log`).

    Pass stdout+stderr concatenated — git push writes the ref update to stderr.

    Returns a GitOperationResult with optional keys:
        commit, push, branch, pr
    """
    result: GitOperationResult = {}

    # commit / cherry-pick — both produce "[branch sha] msg" output
    is_cherry_pick = bool(_GIT_CHERRY_PICK_RE.search(command))
    if _GIT_COMMIT_RE.search(command) or is_cherry_pick:
        sha = _parse_git_commit_id(output)
        if sha:
            kind: CommitKind = (
                "cherry-picked"
                if is_cherry_pick
                else "amended"
                if re.search(r"--amend\b", command)
                else "committed"
            )
            result["commit"] = CommitInfo(sha=sha[:6], kind=kind)

    if _GIT_PUSH_RE.search(command):
        branch = _parse_git_push_branch(output)
        if branch:
            result["push"] = PushInfo(branch=branch)

    if _GIT_MERGE_RE.search(command) and re.search(
        r"(Fast-forward|Merge made by)", output
    ):
        ref = _parse_ref_from_command(command, "merge")
        if ref:
            result["branch"] = BranchInfo(ref=ref, action="merged")

    if _GIT_REBASE_RE.search(command) and re.search(
        r"Successfully rebased", output
    ):
        ref = _parse_ref_from_command(command, "rebase")
        if ref:
            result["branch"] = BranchInfo(ref=ref, action="rebased")

    # gh pr actions
    pr_action: Optional[PrAction] = None
    for pattern, action, _ in _GH_PR_ACTIONS:
        if pattern.search(command):
            pr_action = action
            break

    if pr_action:
        pr = _find_pr_in_stdout(output)
        if pr:
            result["pr"] = PrInfo(
                number=pr["prNumber"], url=pr["prUrl"], action=pr_action
            )
        else:
            num = _parse_pr_number_from_text(output)
            if num:
                result["pr"] = PrInfo(number=num, action=pr_action)

    return result
