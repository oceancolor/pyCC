"""
Ported from: commands/review/reviewRemote.ts (316 lines)

Teleported /ultrareview execution. Creates a CCR session with the current
repo, sends the review prompt as the initial message, and registers a
RemoteAgentTask so the polling loop pipes results back into the local
session via task-notification.

Mirrors the /ultraplan → CCR flow. React/Ink UI components are omitted.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Union

# ---------------------------------------------------------------------------
# One-time session flag: once the user confirms overage billing, all
# subsequent /ultrareview invocations in this session proceed without
# re-prompting.
# ---------------------------------------------------------------------------
_session_overage_confirmed: bool = False


def confirm_overage() -> None:
    """Mark that the user has confirmed Extra Usage billing for this session."""
    global _session_overage_confirmed
    _session_overage_confirmed = True


# ---------------------------------------------------------------------------
# Type aliases for overage gate outcomes
# ---------------------------------------------------------------------------
# Mirrors OverageGate union from TS source.
OverageGate = Dict[str, Any]
# Possible shapes:
#   {"kind": "proceed",      "billing_note": str}
#   {"kind": "not-enabled"}
#   {"kind": "low-balance",  "available": float}
#   {"kind": "needs-confirm"}


# ---------------------------------------------------------------------------
# Auth helpers (stub wrappers)
# ---------------------------------------------------------------------------

def _is_team_subscriber() -> bool:
    try:
        from claude_code.utils.auth import is_team_subscriber
        return is_team_subscriber()
    except ImportError:
        return False


def _is_enterprise_subscriber() -> bool:
    try:
        from claude_code.utils.auth import is_enterprise_subscriber
        return is_enterprise_subscriber()
    except ImportError:
        return False


async def _fetch_ultrareview_quota() -> Optional[Dict[str, Any]]:
    try:
        from claude_code.services.api.ultrareview_quota import fetch_ultrareview_quota
        return await fetch_ultrareview_quota()
    except (ImportError, Exception):
        return None


async def _fetch_utilization() -> Optional[Dict[str, Any]]:
    try:
        from claude_code.services.api.usage import fetch_utilization
        return await fetch_utilization()
    except (ImportError, Exception):
        return None


def _log_event(event: str, data: Dict[str, Any]) -> None:
    try:
        from claude_code.services.analytics.index import log_event
        log_event(event, data)
    except (ImportError, Exception):
        pass


# ---------------------------------------------------------------------------
# Overage gate
# ---------------------------------------------------------------------------

async def check_overage_gate() -> OverageGate:
    """
    Determine whether the user can launch an ultrareview and under what
    billing terms. Fetches quota and utilization in parallel.
    Mirrors checkOverageGate() from the TS source.
    """
    # Team and Enterprise plans include ultrareview — skip billing dialog
    if _is_team_subscriber() or _is_enterprise_subscriber():
        return {"kind": "proceed", "billing_note": ""}

    import asyncio
    quota, utilization = await asyncio.gather(
        _fetch_ultrareview_quota(),
        _fetch_utilization(),
        return_exceptions=True,
    )

    # If gather raised, treat as None
    if isinstance(quota, BaseException):
        quota = None
    if isinstance(utilization, BaseException):
        utilization = None

    # No quota info — let it through
    if not quota:
        return {"kind": "proceed", "billing_note": ""}

    reviews_remaining = quota.get("reviews_remaining", 0)
    if reviews_remaining > 0:
        reviews_used = quota.get("reviews_used", 0)
        reviews_limit = quota.get("reviews_limit", reviews_used + reviews_remaining)
        return {
            "kind": "proceed",
            "billing_note": f" This is free ultrareview {reviews_used + 1} of {reviews_limit}.",
        }

    # Utilization fetch failed — let it through
    if not utilization:
        return {"kind": "proceed", "billing_note": ""}

    extra_usage = utilization.get("extra_usage") or {}
    if not extra_usage.get("is_enabled"):
        _log_event("tengu_review_overage_not_enabled", {})
        return {"kind": "not-enabled"}

    monthly_limit = extra_usage.get("monthly_limit")
    used_credits = extra_usage.get("used_credits") or 0
    if monthly_limit is None:
        available = float("inf")
    else:
        available = monthly_limit - used_credits

    if available < 10:
        _log_event("tengu_review_overage_low_balance", {"available": available})
        return {"kind": "low-balance", "available": available}

    if not _session_overage_confirmed:
        _log_event("tengu_review_overage_dialog_shown", {})
        return {"kind": "needs-confirm"}

    return {"kind": "proceed", "billing_note": " This review bills as Extra Usage."}


# ---------------------------------------------------------------------------
# Remote review launch
# ---------------------------------------------------------------------------

# Synthetic environment ID for code-review (mirrors TS constant)
CODE_REVIEW_ENV_ID = "env_011111111111111111111113"


def _get_feature_value_cached(key: str, default: Any) -> Any:
    try:
        from claude_code.services.analytics.growthbook import get_feature_value_cached_may_be_stale
        return get_feature_value_cached_may_be_stale(key, default)
    except ImportError:
        return default


async def _check_remote_agent_eligibility() -> Any:
    try:
        from claude_code.tasks.remote_agent_task.remote_agent_task import check_remote_agent_eligibility
        return await check_remote_agent_eligibility()
    except (ImportError, Exception):
        # Stub: always eligible
        return type("E", (), {"eligible": True, "errors": []})()


def _format_precondition_error(error: Any) -> str:
    try:
        from claude_code.tasks.remote_agent_task.remote_agent_task import format_precondition_error
        return format_precondition_error(error)
    except ImportError:
        return str(error)


def _get_remote_task_session_url(session_id: str) -> str:
    try:
        from claude_code.tasks.remote_agent_task.remote_agent_task import get_remote_task_session_url
        return get_remote_task_session_url(session_id)
    except ImportError:
        return f"https://claude.ai/sessions/{session_id}"


async def _register_remote_agent_task(
    remote_task_type: str,
    session: Any,
    command: str,
    context: Any,
    is_remote_review: bool = False,
) -> None:
    try:
        from claude_code.tasks.remote_agent_task.remote_agent_task import register_remote_agent_task
        register_remote_agent_task(
            remote_task_type=remote_task_type,
            session=session,
            command=command,
            context=context,
            is_remote_review=is_remote_review,
        )
    except (ImportError, Exception):
        pass


async def _teleport_to_remote(
    description: str,
    signal: Any,
    branch_name: Optional[str] = None,
    use_bundle: bool = False,
    environment_id: str = CODE_REVIEW_ENV_ID,
    environment_variables: Optional[Dict[str, str]] = None,
) -> Optional[Any]:
    try:
        from claude_code.utils.teleport import teleport_to_remote
        return await teleport_to_remote(
            initial_message=None,
            description=description,
            signal=signal,
            branch_name=branch_name,
            use_bundle=use_bundle,
            environment_id=environment_id,
            environment_variables=environment_variables or {},
        )
    except (ImportError, Exception):
        return None


async def _detect_current_repository_with_host() -> Optional[Dict[str, Any]]:
    try:
        from claude_code.utils.detect_repository import detect_current_repository_with_host
        return await detect_current_repository_with_host()
    except (ImportError, Exception):
        return None


async def _exec_file_no_throw(exe: str, args: List[str]) -> Dict[str, Any]:
    try:
        from claude_code.utils.exec_file_no_throw import exec_file_no_throw
        return await exec_file_no_throw(exe, args)
    except ImportError:
        import asyncio
        proc = await asyncio.create_subprocess_exec(
            exe, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await proc.communicate()
        return {
            "stdout": stdout_b.decode("utf-8", errors="replace"),
            "stderr": stderr_b.decode("utf-8", errors="replace"),
            "code": proc.returncode or 0,
        }


async def _get_default_branch() -> Optional[str]:
    try:
        from claude_code.utils.git import get_default_branch
        return await get_default_branch()
    except ImportError:
        return "main"


def _git_exe() -> str:
    try:
        from claude_code.utils.git import git_exe
        return git_exe()
    except ImportError:
        return "git"


def _pos_int(v: Any, fallback: int, max_val: Optional[int] = None) -> int:
    """Coerce v to a positive int with fallback and optional ceiling."""
    try:
        n = int(float(v))
        if n <= 0:
            return fallback
        if max_val is not None and n > max_val:
            return fallback
        return n
    except (TypeError, ValueError):
        return fallback


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

ContentBlock = Dict[str, Any]


async def launch_remote_review(
    args: str,
    context: Any,
    billing_note: Optional[str] = None,
) -> Optional[List[ContentBlock]]:
    """
    Launch a teleported review session.

    Returns a list of ContentBlockParam-like dicts describing the outcome for
    injection into the local conversation, or None on non-recoverable failures.
    Caller must run check_overage_gate() BEFORE calling this function.

    Mirrors launchRemoteReview() from the TS source.
    """
    eligibility = await _check_remote_agent_eligibility()

    if not getattr(eligibility, "eligible", True):
        errors = getattr(eligibility, "errors", [])
        blockers = [e for e in errors if getattr(e, "type", None) != "no_remote_environment"]
        if blockers:
            _log_event(
                "tengu_review_remote_precondition_failed",
                {
                    "precondition_errors": ",".join(
                        getattr(e, "type", str(e)) for e in blockers
                    )
                },
            )
            reasons = "\n".join(_format_precondition_error(e) for e in blockers)
            return [{"type": "text", "text": f"Ultrareview cannot launch:\n{reasons}"}]

    resolved_billing_note = billing_note or ""

    # Read bughunter config from feature flags (may be stale)
    raw = _get_feature_value_cached("tengu_review_bughunter_config", None)
    if not isinstance(raw, dict):
        raw = {}

    common_env_vars = {
        "BUGHUNTER_DRY_RUN": "1",
        "BUGHUNTER_FLEET_SIZE": str(_pos_int(raw.get("fleet_size"), 5, 20)),
        "BUGHUNTER_MAX_DURATION": str(_pos_int(raw.get("max_duration_minutes"), 10, 25)),
        "BUGHUNTER_AGENT_TIMEOUT": str(_pos_int(raw.get("agent_timeout_seconds"), 600, 1800)),
        "BUGHUNTER_TOTAL_WALLCLOCK": str(_pos_int(raw.get("total_wallclock_minutes"), 22, 27)),
    }
    dev_bundle = os.environ.get("BUGHUNTER_DEV_BUNDLE_B64")
    if dev_bundle:
        common_env_vars["BUGHUNTER_DEV_BUNDLE_B64"] = dev_bundle

    pr_number = (args or "").strip()
    is_pr_number = bool(re.match(r"^\d+$", pr_number))

    # Get abort signal from context
    abort_controller = getattr(context, "abort_controller", None)
    signal = getattr(abort_controller, "signal", None)

    if is_pr_number:
        # PR mode: refs/pull/N/head via github.com
        repo = await _detect_current_repository_with_host()
        if not repo or repo.get("host") != "github.com":
            _log_event("tengu_review_remote_precondition_failed", {})
            return None

        owner = repo.get("owner", "")
        name = repo.get("name", "")
        session = await _teleport_to_remote(
            description=f"ultrareview: {owner}/{name}#{pr_number}",
            signal=signal,
            branch_name=f"refs/pull/{pr_number}/head",
            environment_id=CODE_REVIEW_ENV_ID,
            environment_variables={
                "BUGHUNTER_PR_NUMBER": pr_number,
                "BUGHUNTER_REPOSITORY": f"{owner}/{name}",
                **common_env_vars,
            },
        )
        command = f"/ultrareview {pr_number}"
        target = f"{owner}/{name}#{pr_number}"

    else:
        # Branch mode: bundle working tree, diff against fork point
        base_branch = await _get_default_branch() or "main"

        mb_result = await _exec_file_no_throw(
            _git_exe(),
            ["merge-base", base_branch, "HEAD"],
        )
        merge_base_sha = (mb_result.get("stdout") or "").strip()
        if mb_result.get("code", 1) != 0 or not merge_base_sha:
            _log_event("tengu_review_remote_precondition_failed", {})
            return [
                {
                    "type": "text",
                    "text": (
                        f"Could not find merge-base with {base_branch}. "
                        f"Make sure you're in a git repo with a {base_branch} branch."
                    ),
                }
            ]

        diff_result = await _exec_file_no_throw(
            _git_exe(),
            ["diff", "--shortstat", merge_base_sha],
        )
        if diff_result.get("code", 1) == 0 and not (diff_result.get("stdout") or "").strip():
            _log_event("tengu_review_remote_precondition_failed", {})
            return [
                {
                    "type": "text",
                    "text": (
                        f"No changes against the {base_branch} fork point. "
                        "Make some commits or stage files first."
                    ),
                }
            ]

        session = await _teleport_to_remote(
            description=f"ultrareview: {base_branch}",
            signal=signal,
            use_bundle=True,
            environment_id=CODE_REVIEW_ENV_ID,
            environment_variables={
                "BUGHUNTER_BASE_BRANCH": merge_base_sha,
                **common_env_vars,
            },
        )
        if not session:
            _log_event("tengu_review_remote_teleport_failed", {})
            return [
                {
                    "type": "text",
                    "text": (
                        "Repo is too large. Push a PR and use "
                        "`/ultrareview <PR#>` instead."
                    ),
                }
            ]
        command = "/ultrareview"
        target = base_branch

    if not session:
        _log_event("tengu_review_remote_teleport_failed", {})
        return None

    session_id = getattr(session, "id", None) or (session.get("id") if isinstance(session, dict) else None) or ""
    await _register_remote_agent_task(
        remote_task_type="ultrareview",
        session=session,
        command=command,
        context=context,
        is_remote_review=True,
    )
    _log_event("tengu_review_remote_launched", {})
    session_url = _get_remote_task_session_url(session_id)

    return [
        {
            "type": "text",
            "text": (
                f"Ultrareview launched for {target} (~10\u201320 min, runs in the cloud). "
                f"Track: {session_url}{resolved_billing_note} "
                "Findings arrive via task-notification. "
                "Briefly acknowledge the launch to the user without repeating "
                "the target or URL \u2014 both are already visible in the tool output above."
            ),
        }
    ]
