"""CCR session polling for /ultraplan. Ported from utils/ultraplan/ccrSession.ts"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Union

POLL_INTERVAL_MS = 3000
MAX_CONSECUTIVE_FAILURES = 5

# Sentinel the browser PlanModal includes in feedback when the user clicks
# "teleport back to terminal". Plan text follows on the next line.
ULTRAPLAN_TELEPORT_SENTINEL = "__ULTRAPLAN_TELEPORT_LOCAL__"

PollFailReason = str  # 'terminated'|'timeout_pending'|'timeout_no_plan'|...


class UltraplanPollError(Exception):
    """Raised when CCR session polling fails."""

    def __init__(
        self,
        message: str,
        reason: PollFailReason,
        reject_count: int,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.reject_count = reject_count
        self.name = "UltraplanPollError"


@dataclass
class ScanResult:
    """Result of scanning the event stream for ExitPlanMode tool results."""

    kind: str  # 'approved'|'teleport'|'rejected'|'pending'|'terminated'|'unchanged'
    plan: Optional[str] = None
    id: Optional[str] = None
    subtype: Optional[str] = None


def scan_events_for_exit_plan_mode(
    events: List[Dict[str, Any]],
    last_event_id: Optional[str] = None,
) -> ScanResult:
    """Scan a list of SDK events for an approved or rejected ExitPlanMode tool_result.

    Args:
        events: List of SDK message event dicts.
        last_event_id: ID of the last processed event (for delta tracking).

    Returns:
        A :class:`ScanResult` describing what was found.
    """
    EXIT_PLAN_TOOL_NAME = "exit_plan_mode"

    for event in events:
        if event.get("type") != "message":
            continue

        content = event.get("content") or []
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue

            # Check for tool_result blocks
            if block.get("type") == "tool_result":
                inner_content = block.get("content") or []
                for inner in inner_content if isinstance(inner_content, list) else []:
                    if isinstance(inner, dict) and inner.get("type") == "text":
                        text = inner.get("text", "")
                        if ULTRAPLAN_TELEPORT_SENTINEL in text:
                            lines = text.split("\n", 1)
                            plan = lines[1].strip() if len(lines) > 1 else ""
                            return ScanResult(kind="teleport", plan=plan)

            # Check for ExitPlanMode tool_use approval
            if block.get("type") == "tool_use" and block.get("name") == EXIT_PLAN_TOOL_NAME:
                input_data = block.get("input") or {}
                if isinstance(input_data, dict):
                    if input_data.get("exit_plan_mode_approved") is True:
                        plan_text = input_data.get("plan_summary", "")
                        return ScanResult(kind="approved", plan=plan_text)
                    if input_data.get("exit_plan_mode_approved") is False:
                        return ScanResult(kind="rejected", id=block.get("id", ""))

        # Check for session termination
        if event.get("type") == "session" and event.get("subtype") in (
            "terminated", "error", "stopped"
        ):
            return ScanResult(kind="terminated", subtype=event.get("subtype"))

    return ScanResult(kind="unchanged")


async def poll_ccr_session_for_plan(
    session_id: str,
    auth_token: str,
    timeout_s: float = 30 * 60,  # 30 minutes
) -> str:
    """Poll a CCR session until an approved plan is received.

    Args:
        session_id: The remote CCR session ID.
        auth_token: Bearer token for API authentication.
        timeout_s: Maximum polling duration in seconds.

    Returns:
        The approved plan text.

    Raises:
        UltraplanPollError: If polling times out or the session terminates.
    """
    from claude_code.utils.teleport.api import get_with_retry, is_transient_network_error
    import os
    import time

    base_url = os.environ.get("CLAUDE_API_BASE_URL", "https://api.claude.ai")
    start = time.time()
    cursor: Optional[str] = None
    consecutive_failures = 0

    while time.time() - start < timeout_s:
        try:
            params: dict = {}
            if cursor:
                params["cursor"] = cursor

            data = await get_with_retry(
                f"{base_url}/api/ccr/sessions/{session_id}/events",
                headers={"Authorization": f"Bearer {auth_token}"},
                params=params,
            )

            events = data.get("events", [])
            cursor = data.get("next_cursor")
            consecutive_failures = 0

            result = scan_events_for_exit_plan_mode(events)

            if result.kind == "approved":
                return result.plan or ""
            if result.kind == "teleport":
                return result.plan or ""
            if result.kind == "rejected":
                raise UltraplanPollError(
                    "Plan was rejected", reason="terminated", reject_count=1
                )
            if result.kind == "terminated":
                raise UltraplanPollError(
                    f"Session terminated: {result.subtype}",
                    reason="terminated",
                    reject_count=0,
                )

        except UltraplanPollError:
            raise
        except Exception as exc:
            consecutive_failures += 1
            if not is_transient_network_error(exc) or consecutive_failures > MAX_CONSECUTIVE_FAILURES:
                raise UltraplanPollError(
                    f"Polling failed: {exc}",
                    reason="network_or_unknown",
                    reject_count=consecutive_failures,
                ) from exc

        await asyncio.sleep(POLL_INTERVAL_MS / 1000)

    raise UltraplanPollError(
        "Polling timed out waiting for plan approval",
        reason="timeout_no_plan",
        reject_count=0,
    )
