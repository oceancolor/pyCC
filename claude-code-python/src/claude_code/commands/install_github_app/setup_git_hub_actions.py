"""GitHub Actions setup utilities.

Ported from commands/install-github-app/setupGitHubActions.ts (325L).
Provides helpers to create and manage Claude Code GitHub Actions workflows.
"""
from __future__ import annotations

import base64
import subprocess
from typing import Any, Dict, Optional


WORKFLOW_PATH = ".github/workflows/claude.yml"
CODE_REVIEW_WORKFLOW_PATH = ".github/workflows/claude-code-review.yml"

_WORKFLOW_CONTENT_TEMPLATE = """\
name: Claude
on:
  issue_comment:
    types: [created]
  pull_request_review_comment:
    types: [created]
  issues:
    types: [opened]
  pull_request_review:
    types: [submitted]
  pull_request:
    types: [opened, synchronize]

jobs:
  claude:
    if: |
      (github.event_name == 'issue_comment' && contains(github.event.comment.body, '@claude')) ||
      (github.event_name == 'pull_request_review_comment' && contains(github.event.comment.body, '@claude')) ||
      (github.event_name == 'pull_request_review' && contains(github.event.review.body, '@claude')) ||
      (github.event_name == 'issues' && contains(github.event.issue.body, '@claude')) ||
      (github.event_name == 'pull_request' && contains(github.event.pull_request.body, '@claude'))
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
      issues: write
    steps:
      - name: Run Claude Code
        id: claude
        uses: anthropics/claude-code-action@beta
        with:
          anthropic_api_key: ${{{{ secrets.{secret_name} }}}}
"""


def _run_gh(*args: str) -> tuple[int, str, str]:
    """Run the gh CLI and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return 1, "", "gh CLI not found. Install GitHub CLI: https://cli.github.com"
    except subprocess.TimeoutExpired:
        return 1, "", "gh CLI timed out"


def _encode_content(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


async def create_workflow_file(
    repo_name: str,
    branch_name: str,
    workflow_path: str,
    workflow_content: str,
    secret_name: str,
    commit_message: str,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """Create or update a GitHub Actions workflow file via the GitHub API.

    Args:
        repo_name: Repository in ``owner/repo`` format.
        branch_name: Branch to commit the workflow to.
        workflow_path: Path within the repo (e.g. ``.github/workflows/claude.yml``).
        workflow_content: Raw YAML content for the workflow.
        secret_name: Name of the secret to use for the Anthropic API key.
        commit_message: Git commit message.
        context: Optional dict with flags ``useCurrentRepo``, ``workflowExists``,
            ``secretExists``.
    """
    if context is None:
        context = {}

    # Adjust secret placeholder if necessary
    if secret_name != "ANTHROPIC_API_KEY":
        if secret_name == "CLAUDE_CODE_OAUTH_TOKEN":
            workflow_content = workflow_content.replace(
                "anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}",
                "claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}",
            )
        else:
            workflow_content = workflow_content.replace(
                "anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}",
                f"anthropic_api_key: ${{{{ secrets.{secret_name} }}}}",
            )

    encoded = _encode_content(workflow_content)

    # Check for existing file SHA
    rc, sha_out, _ = _run_gh(
        "api",
        f"repos/{repo_name}/contents/{workflow_path}",
        "--jq",
        ".sha",
    )
    file_sha: Optional[str] = sha_out if rc == 0 and sha_out else None

    api_args = [
        "api",
        "--method", "PUT",
        f"repos/{repo_name}/contents/{workflow_path}",
        "-f", f"message={commit_message}",
        "-f", f"content={encoded}",
        "-f", f"branch={branch_name}",
    ]
    if file_sha:
        api_args += ["-f", f"sha={file_sha}"]

    rc, _, err = _run_gh(*api_args)
    if rc != 0:
        raise RuntimeError(f"Failed to create workflow file: {err}")


async def setup_github_actions(
    repo: str,
    token: Optional[str] = None,
    secret_name: str = "ANTHROPIC_API_KEY",
    branch: str = "main",
) -> Dict[str, Any]:
    """Set up Claude Code GitHub Actions for a repository.

    Creates the required workflow files and configures repository secrets.

    Args:
        repo: Repository in ``owner/repo`` format.
        token: Optional GitHub personal access token; uses gh CLI auth if omitted.
        secret_name: Name to use for the Anthropic key secret.
        branch: Branch to commit workflow files to.

    Returns:
        Dict with keys ``success`` (bool), ``message`` (str), and optionally
        ``workflow_url`` (str).
    """
    workflow_content = _WORKFLOW_CONTENT_TEMPLATE.format(secret_name=secret_name)

    try:
        await create_workflow_file(
            repo_name=repo,
            branch_name=branch,
            workflow_path=WORKFLOW_PATH,
            workflow_content=workflow_content,
            secret_name=secret_name,
            commit_message="Add Claude Code GitHub Actions workflow",
        )
        return {
            "success": True,
            "message": f"GitHub Actions workflow created for {repo}.",
            "workflow_url": f"https://github.com/{repo}/actions",
        }
    except RuntimeError as exc:
        return {"success": False, "message": str(exc)}
