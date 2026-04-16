"""
git_diff.py - Python port of gitDiff.ts
Source: claude-code-analysis/claude-code-source/utils/gitDiff.ts

Core functionality:
- Generate git diff output
- Format/parse diff content
- Support various diff options (numstat, shortstat, hunks)
"""

import asyncio
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GIT_TIMEOUT_S = 5.0
MAX_FILES = 50
MAX_DIFF_SIZE_BYTES = 1_000_000  # 1 MB
MAX_LINES_PER_FILE = 400
MAX_FILES_FOR_DETAILS = 500


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class GitDiffStats:
    files_count: int = 0
    lines_added: int = 0
    lines_removed: int = 0


@dataclass
class PerFileStats:
    added: int = 0
    removed: int = 0
    is_binary: bool = False
    is_untracked: bool = False


@dataclass
class StructuredPatchHunk:
    old_start: int = 0
    old_lines: int = 1
    new_start: int = 0
    new_lines: int = 1
    lines: List[str] = field(default_factory=list)


@dataclass
class GitDiffResult:
    stats: GitDiffStats = field(default_factory=GitDiffStats)
    per_file_stats: Dict[str, PerFileStats] = field(default_factory=dict)
    hunks: Dict[str, List[StructuredPatchHunk]] = field(default_factory=dict)


@dataclass
class NumstatResult:
    stats: GitDiffStats = field(default_factory=GitDiffStats)
    per_file_stats: Dict[str, PerFileStats] = field(default_factory=dict)


@dataclass
class ToolUseDiff:
    filename: str = ""
    status: str = "modified"  # 'modified' | 'added'
    additions: int = 0
    deletions: int = 0
    changes: int = 0
    patch: str = ""
    repository: Optional[str] = None  # "owner/repo" or None


# ---------------------------------------------------------------------------
# Helper: run git command
# ---------------------------------------------------------------------------

async def _run_git(
    args: List[str],
    cwd: Optional[str] = None,
    timeout: float = GIT_TIMEOUT_S,
) -> Tuple[int, str, str]:
    """
    Run a git command asynchronously.
    Returns (returncode, stdout, stderr).
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        return proc.returncode or 0, stdout_bytes.decode("utf-8", errors="replace"), stderr_bytes.decode("utf-8", errors="replace")
    except asyncio.TimeoutError:
        return -1, "", "timeout"
    except Exception:
        return -1, "", "error"


def _git_exe() -> str:
    """Return the path to the git executable."""
    return "git"


# ---------------------------------------------------------------------------
# Transient state check
# ---------------------------------------------------------------------------

async def is_in_transient_git_state(cwd: Optional[str] = None) -> bool:
    """
    Check if we are in a transient git state (merge, rebase, cherry-pick, revert).
    """
    work_dir = cwd or os.getcwd()
    # Find .git directory
    code, git_dir_out, _ = await _run_git(
        ["rev-parse", "--git-dir"], cwd=work_dir
    )
    if code != 0:
        return False
    git_dir = git_dir_out.strip()
    if not os.path.isabs(git_dir):
        git_dir = os.path.join(work_dir, git_dir)

    transient_files = ["MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD"]
    for fname in transient_files:
        if os.path.exists(os.path.join(git_dir, fname)):
            return True
    return False


# ---------------------------------------------------------------------------
# Untracked files
# ---------------------------------------------------------------------------

async def _fetch_untracked_files(
    max_files: int, cwd: Optional[str] = None
) -> Optional[Dict[str, PerFileStats]]:
    """Fetch untracked file names (no content reading)."""
    code, stdout, _ = await _run_git(
        ["--no-optional-locks", "ls-files", "--others", "--exclude-standard"],
        cwd=cwd,
        timeout=GIT_TIMEOUT_S,
    )
    if code != 0 or not stdout.strip():
        return None

    untracked_paths = [p for p in stdout.strip().split("\n") if p]
    if not untracked_paths:
        return None

    per_file_stats: Dict[str, PerFileStats] = {}
    for file_path in untracked_paths[:max_files]:
        per_file_stats[file_path] = PerFileStats(
            added=0, removed=0, is_binary=False, is_untracked=True
        )
    return per_file_stats


# ---------------------------------------------------------------------------
# Parse functions
# ---------------------------------------------------------------------------

def parse_git_numstat(stdout: str) -> NumstatResult:
    """
    Parse git diff --numstat output into stats.
    Format: <added>\\t<removed>\\t<filename>
    Binary files show '-' for counts.
    Only stores first MAX_FILES entries in per_file_stats.
    """
    lines = [l for l in stdout.strip().split("\n") if l]
    added = 0
    removed = 0
    valid_file_count = 0
    per_file_stats: Dict[str, PerFileStats] = {}

    for line in lines:
        parts = line.split("\t")
        if len(parts) < 3:
            continue

        valid_file_count += 1
        add_str = parts[0]
        rem_str = parts[1]
        file_path = "\t".join(parts[2:])  # filename may contain tabs

        is_binary = add_str == "-" or rem_str == "-"
        file_added = 0 if is_binary else (int(add_str) if add_str.isdigit() else 0)
        file_removed = 0 if is_binary else (int(rem_str) if rem_str.isdigit() else 0)

        added += file_added
        removed += file_removed

        if len(per_file_stats) < MAX_FILES:
            per_file_stats[file_path] = PerFileStats(
                added=file_added, removed=file_removed, is_binary=is_binary
            )

    return NumstatResult(
        stats=GitDiffStats(
            files_count=valid_file_count,
            lines_added=added,
            lines_removed=removed,
        ),
        per_file_stats=per_file_stats,
    )


def parse_git_diff(stdout: str) -> Dict[str, List[StructuredPatchHunk]]:
    """
    Parse unified diff output into per-file hunks.
    Splits by "diff --git" and parses each file's hunks.

    Applies limits:
    - MAX_FILES: stop after this many files
    - Files >1MB: skipped entirely
    - Files <=1MB: parsed but limited to MAX_LINES_PER_FILE lines
    """
    result: Dict[str, List[StructuredPatchHunk]] = {}
    if not stdout.strip():
        return result

    # Split by file diffs
    file_diffs = [f for f in re.split(r"^diff --git ", stdout, flags=re.MULTILINE) if f]

    for file_diff in file_diffs:
        if len(result) >= MAX_FILES:
            break

        # Skip files larger than 1MB
        if len(file_diff.encode("utf-8")) > MAX_DIFF_SIZE_BYTES:
            continue

        lines = file_diff.split("\n")

        # Extract filename from first line: "a/path/to/file b/path/to/file"
        if not lines:
            continue
        header_match = re.match(r"^a\/(.+?) b\/(.+)$", lines[0])
        if not header_match:
            continue
        file_path = header_match.group(2) or header_match.group(1) or ""

        # Find and parse hunks
        file_hunks: List[StructuredPatchHunk] = []
        current_hunk: Optional[StructuredPatchHunk] = None
        line_count = 0

        for i in range(1, len(lines)):
            line = lines[i]

            # Hunk header: @@ -oldStart,oldLines +newStart,newLines @@
            hunk_match = re.match(
                r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line
            )
            if hunk_match:
                if current_hunk is not None:
                    file_hunks.append(current_hunk)
                current_hunk = StructuredPatchHunk(
                    old_start=int(hunk_match.group(1)),
                    old_lines=int(hunk_match.group(2) or "1"),
                    new_start=int(hunk_match.group(3)),
                    new_lines=int(hunk_match.group(4) or "1"),
                    lines=[],
                )
                continue

            # Skip binary file markers and other metadata
            if any(
                line.startswith(prefix)
                for prefix in (
                    "index ",
                    "---",
                    "+++",
                    "new file",
                    "deleted file",
                    "old mode",
                    "new mode",
                    "Binary files",
                )
            ):
                continue

            # Add diff lines to current hunk (with line limit)
            if current_hunk is not None and (
                line.startswith("+")
                or line.startswith("-")
                or line.startswith(" ")
                or line == ""
            ):
                if line_count < MAX_LINES_PER_FILE:
                    current_hunk.lines.append(line)
                    line_count += 1

        # Don't forget the last hunk
        if current_hunk is not None:
            file_hunks.append(current_hunk)

        if file_hunks:
            result[file_path] = file_hunks

    return result


def parse_shortstat(stdout: str) -> Optional[GitDiffStats]:
    """
    Parse git diff --shortstat output into stats.
    Format: " 1648 files changed, 52341 insertions(+), 8123 deletions(-)"
    """
    match = re.search(
        r"(\d+)\s+files?\s+changed(?:,\s+(\d+)\s+insertions?\(\+\))?(?:,\s+(\d+)\s+deletions?\(-\))?",
        stdout,
    )
    if not match:
        return None
    return GitDiffStats(
        files_count=int(match.group(1) or "0"),
        lines_added=int(match.group(2) or "0"),
        lines_removed=int(match.group(3) or "0"),
    )


# ---------------------------------------------------------------------------
# Main fetch functions
# ---------------------------------------------------------------------------

async def fetch_git_diff(cwd: Optional[str] = None) -> Optional[GitDiffResult]:
    """
    Fetch git diff stats and hunks comparing working tree to HEAD.
    Returns None if not in a git repo or if git commands fail.

    Returns None during merge/rebase/cherry-pick/revert operations since the
    working tree contains incoming changes.
    """
    work_dir = cwd or os.getcwd()

    # Check if in git repo
    code, _, _ = await _run_git(["rev-parse", "--is-inside-work-tree"], cwd=work_dir)
    if code != 0:
        return None

    # Skip diff calculation during transient git states
    if await is_in_transient_git_state(work_dir):
        return None

    # Quick probe: use --shortstat to get totals without loading all content
    code_ss, shortstat_out, _ = await _run_git(
        ["--no-optional-locks", "diff", "HEAD", "--shortstat"],
        cwd=work_dir,
        timeout=GIT_TIMEOUT_S,
    )

    if code_ss == 0:
        quick_stats = parse_shortstat(shortstat_out)
        if quick_stats and quick_stats.files_count > MAX_FILES_FOR_DETAILS:
            return GitDiffResult(
                stats=quick_stats,
                per_file_stats={},
                hunks={},
            )

    # Get stats via --numstat (all uncommitted changes vs HEAD)
    numstat_code, numstat_out, _ = await _run_git(
        ["--no-optional-locks", "diff", "HEAD", "--numstat"],
        cwd=work_dir,
        timeout=GIT_TIMEOUT_S,
    )

    if numstat_code != 0:
        return None

    numstat_result = parse_git_numstat(numstat_out)
    stats = numstat_result.stats
    per_file_stats = numstat_result.per_file_stats

    # Include untracked files
    remaining_slots = MAX_FILES - len(per_file_stats)
    if remaining_slots > 0:
        untracked_stats = await _fetch_untracked_files(remaining_slots, cwd=work_dir)
        if untracked_stats:
            stats.files_count += len(untracked_stats)
            per_file_stats.update(untracked_stats)

    return GitDiffResult(stats=stats, per_file_stats=per_file_stats, hunks={})


async def fetch_git_diff_hunks(
    cwd: Optional[str] = None,
) -> Dict[str, List[StructuredPatchHunk]]:
    """
    Fetch git diff hunks on-demand.
    Separated from fetch_git_diff() to avoid expensive calls during polling.
    """
    work_dir = cwd or os.getcwd()

    code, _, _ = await _run_git(["rev-parse", "--is-inside-work-tree"], cwd=work_dir)
    if code != 0:
        return {}

    if await is_in_transient_git_state(work_dir):
        return {}

    diff_code, diff_out, _ = await _run_git(
        ["--no-optional-locks", "diff", "HEAD"],
        cwd=work_dir,
        timeout=GIT_TIMEOUT_S,
    )

    if diff_code != 0:
        return {}

    return parse_git_diff(diff_out)


# ---------------------------------------------------------------------------
# Single-file diff
# ---------------------------------------------------------------------------

SINGLE_FILE_DIFF_TIMEOUT_S = 3.0


def _parse_raw_diff_to_tool_use_diff(
    filename: str, raw_diff: str, status: str
) -> ToolUseDiff:
    """
    Parse raw unified diff output into the structured ToolUseDiff format.
    """
    lines = raw_diff.split("\n")
    patch_lines: List[str] = []
    in_hunks = False
    additions = 0
    deletions = 0

    for line in lines:
        if line.startswith("@@"):
            in_hunks = True
        if in_hunks:
            patch_lines.append(line)
            if line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1

    return ToolUseDiff(
        filename=filename,
        status=status,
        additions=additions,
        deletions=deletions,
        changes=additions + deletions,
        patch="\n".join(patch_lines),
    )


async def _get_diff_ref(git_root: str) -> str:
    """
    Determine the best ref to diff against for a PR-like diff.
    Priority:
    1. CLAUDE_CODE_BASE_REF env var
    2. Merge base with default branch
    3. HEAD (fallback)
    """
    base_branch = os.environ.get("CLAUDE_CODE_BASE_REF")
    if not base_branch:
        # Try to get the default branch
        code, out, _ = await _run_git(
            ["symbolic-ref", "refs/remotes/origin/HEAD"],
            cwd=git_root,
            timeout=SINGLE_FILE_DIFF_TIMEOUT_S,
        )
        if code == 0:
            base_branch = out.strip().replace("refs/remotes/origin/", "")
        else:
            base_branch = "main"

    merge_code, merge_out, _ = await _run_git(
        ["--no-optional-locks", "merge-base", "HEAD", base_branch],
        cwd=git_root,
        timeout=SINGLE_FILE_DIFF_TIMEOUT_S,
    )
    if merge_code == 0 and merge_out.strip():
        return merge_out.strip()
    return "HEAD"


async def _generate_synthetic_diff(
    git_path: str, absolute_file_path: str
) -> Optional[ToolUseDiff]:
    """Generate a synthetic diff for untracked files (all additions)."""
    try:
        file_size = os.path.getsize(absolute_file_path)
        if file_size > MAX_DIFF_SIZE_BYTES:
            return None
        with open(absolute_file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        lines = content.split("\n")
        # Remove trailing empty line from split if file ends with newline
        if lines and lines[-1] == "":
            lines.pop()
        line_count = len(lines)
        added_lines = "\n".join(f"+{l}" for l in lines)
        patch = f"@@ -0,0 +1,{line_count} @@\n{added_lines}"
        return ToolUseDiff(
            filename=git_path,
            status="added",
            additions=line_count,
            deletions=0,
            changes=line_count,
            patch=patch,
        )
    except Exception:
        return None


async def fetch_single_file_git_diff(
    absolute_file_path: str,
    repository: Optional[str] = None,
) -> Optional[ToolUseDiff]:
    """
    Fetch a structured diff for a single file against the merge base with the
    default branch. Falls back to diffing against HEAD if the merge base
    cannot be determined.
    For untracked files, generates a synthetic diff showing all additions.
    Returns None if not in a git repo or if git commands fail.
    """
    # Find git root
    abs_path = os.path.abspath(absolute_file_path)
    file_dir = os.path.dirname(abs_path)

    git_root_code, git_root_out, _ = await _run_git(
        ["rev-parse", "--show-toplevel"], cwd=file_dir
    )
    if git_root_code != 0:
        return None
    git_root = git_root_out.strip()

    # Compute relative path with forward slashes
    git_path = os.path.relpath(abs_path, git_root).replace(os.sep, "/")

    # Check if the file is tracked by git
    ls_code, _, _ = await _run_git(
        ["--no-optional-locks", "ls-files", "--error-unmatch", git_path],
        cwd=git_root,
        timeout=SINGLE_FILE_DIFF_TIMEOUT_S,
    )

    if ls_code == 0:
        # File is tracked - diff against merge base for PR-like view
        diff_ref = await _get_diff_ref(git_root)
        diff_code, diff_out, _ = await _run_git(
            ["--no-optional-locks", "diff", diff_ref, "--", git_path],
            cwd=git_root,
            timeout=SINGLE_FILE_DIFF_TIMEOUT_S,
        )
        if diff_code != 0 or not diff_out:
            return None
        result = _parse_raw_diff_to_tool_use_diff(git_path, diff_out, "modified")
        result.repository = repository
        return result

    # File is untracked - generate synthetic diff
    synthetic = await _generate_synthetic_diff(git_path, abs_path)
    if synthetic is None:
        return None
    synthetic.repository = repository
    return synthetic
