"""Teammate Mailbox — file-based messaging for agent swarms."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class TeammateMessage:
    from_agent: str
    text: str
    timestamp: str
    read: bool = False
    color: Optional[str] = None
    summary: Optional[str] = None


def _get_teams_dir() -> Path:
    default = Path.home() / ".claude" / "teams"
    return Path(os.environ.get("CLAUDE_CODE_TEAMS_DIR", str(default)))


def _sanitize(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-.]", "_", name)


def get_inbox_path(agent_name: str, team_name: Optional[str] = None) -> Path:
    team = team_name or os.environ.get("CLAUDE_CODE_TEAM_NAME") or "default"
    inbox_dir = _get_teams_dir() / _sanitize(team) / "inboxes"
    return inbox_dir / f"{_sanitize(agent_name)}.json"


async def _ensure_inbox_dir(team_name: Optional[str] = None) -> None:
    team = team_name or os.environ.get("CLAUDE_CODE_TEAM_NAME") or "default"
    inbox_dir = _get_teams_dir() / _sanitize(team) / "inboxes"
    await asyncio.to_thread(inbox_dir.mkdir, parents=True, exist_ok=True)


def _read_inbox_sync(path: Path) -> list[TeammateMessage]:
    try:
        raw = json.loads(path.read_text("utf-8"))
        return [TeammateMessage(**m) for m in raw]
    except FileNotFoundError:
        return []
    except Exception as exc:
        logger.error("Failed to read inbox %s: %s", path, exc)
        return []


def _write_inbox_sync(path: Path, messages: list[TeammateMessage]) -> None:
    path.write_text(
        json.dumps([asdict(m) for m in messages], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


_mem_locks: dict[str, asyncio.Lock] = {}


class _FileLock:
    def __init__(self, path: Path) -> None:
        self._path = path
        try:
            import filelock  # type: ignore
            self._lock = filelock.AsyncFileLock(str(path) + ".lock", timeout=5)
            self._use_filelock = True
        except ImportError:
            key = str(path)
            if key not in _mem_locks:
                _mem_locks[key] = asyncio.Lock()
            self._lock = _mem_locks[key]
            self._use_filelock = False

    async def __aenter__(self) -> "_FileLock":
        await self._lock.acquire()
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._use_filelock:
            await self._lock.release()
        else:
            self._lock.release()  # type: ignore[union-attr]


async def read_mailbox(agent_name: str, team_name: Optional[str] = None) -> list[TeammateMessage]:
    return await asyncio.to_thread(_read_inbox_sync, get_inbox_path(agent_name, team_name))


async def read_unread_messages(agent_name: str, team_name: Optional[str] = None) -> list[TeammateMessage]:
    return [m for m in await read_mailbox(agent_name, team_name) if not m.read]


async def write_to_mailbox(
    recipient_name: str, message: TeammateMessage, team_name: Optional[str] = None
) -> None:
    await _ensure_inbox_dir(team_name)
    path = get_inbox_path(recipient_name, team_name)

    def _init_file() -> None:
        try:
            path.open("x").close()
            path.write_text("[]", encoding="utf-8")
        except FileExistsError:
            pass

    await asyncio.to_thread(_init_file)
    async with _FileLock(path):
        messages = await asyncio.to_thread(_read_inbox_sync, path)
        message.read = False
        messages.append(message)
        await asyncio.to_thread(_write_inbox_sync, path, messages)


async def mark_message_as_read_by_index(
    agent_name: str, message_index: int, team_name: Optional[str] = None
) -> None:
    path = get_inbox_path(agent_name, team_name)
    async with _FileLock(path):
        messages = await asyncio.to_thread(_read_inbox_sync, path)
        if 0 <= message_index < len(messages) and not messages[message_index].read:
            messages[message_index].read = True
            await asyncio.to_thread(_write_inbox_sync, path, messages)


async def mark_messages_as_read(agent_name: str, team_name: Optional[str] = None) -> None:
    path = get_inbox_path(agent_name, team_name)
    async with _FileLock(path):
        messages = await asyncio.to_thread(_read_inbox_sync, path)
        updated = [TeammateMessage(**{**asdict(m), "read": True}) for m in messages]
        await asyncio.to_thread(_write_inbox_sync, path, updated)


class TeammateMailbox:
    def __init__(self, agent_name: str, team_name: Optional[str] = None) -> None:
        self.agent_name = agent_name
        self.team_name = team_name

    async def send(self, to_agent: str, text: str, **kwargs: object) -> None:
        msg = TeammateMessage(
            from_agent=self.agent_name, text=text, timestamp=str(time.time()), **kwargs  # type: ignore
        )
        await write_to_mailbox(to_agent, msg, self.team_name)

    async def receive(self) -> list[TeammateMessage]:
        msgs = await read_unread_messages(self.agent_name, self.team_name)
        all_msgs = await read_mailbox(self.agent_name, self.team_name)
        for i, m in enumerate(all_msgs):
            if not m.read:
                await mark_message_as_read_by_index(self.agent_name, i, self.team_name)
        return msgs

    async def get_messages(self, unread_only: bool = False) -> list[TeammateMessage]:
        if unread_only:
            return await read_unread_messages(self.agent_name, self.team_name)
        return await read_mailbox(self.agent_name, self.team_name)

    async def mark_read(self, index: Optional[int] = None) -> None:
        if index is None:
            await mark_messages_as_read(self.agent_name, self.team_name)
        else:
            await mark_message_as_read_by_index(self.agent_name, index, self.team_name)


# ─────────────────────────────────────────────────────────────
# Additional functions ported from TS teammateMailbox.ts
# ─────────────────────────────────────────────────────────────


async def clear_mailbox(agent_name: str, team_name: Optional[str] = None) -> None:
    """Clear a teammate's inbox (delete all messages)."""
    path = get_inbox_path(agent_name, team_name)
    try:
        # 'r+' throws FileNotFoundError if the file doesn't exist
        with open(path, "r+", encoding="utf-8") as f:
            f.seek(0)
            f.write("[]")
            f.truncate()
        logger.debug("Cleared inbox for %s", agent_name)
    except FileNotFoundError:
        return
    except Exception as exc:
        logger.error("Failed to clear inbox for %s: %s", agent_name, exc)


def format_teammate_messages(
    messages: List[Dict[str, Any]],
) -> str:
    """Format teammate messages as XML for attachment display."""
    parts: list[str] = []
    for m in messages:
        color_attr = f' color="{m["color"]}"' if m.get("color") else ""
        summary_attr = f' summary="{m["summary"]}"' if m.get("summary") else ""
        tag = "teammate_message"
        parts.append(
            f'<{tag} teammate_id="{m["from"]}"'
            f'{color_attr}{summary_attr}>\n{m["text"]}\n</{tag}>'
        )
    return "\n\n".join(parts)


# ── Idle Notification ──────────────────────────────────────────


@dataclass
class IdleNotificationMessage:
    type: str = "idle_notification"
    from_agent: str = ""
    timestamp: str = ""
    idle_reason: Optional[str] = None   # 'available' | 'interrupted' | 'failed'
    summary: Optional[str] = None
    completed_task_id: Optional[str] = None
    completed_status: Optional[str] = None   # 'resolved' | 'blocked' | 'failed'
    failure_reason: Optional[str] = None


def create_idle_notification(
    agent_id: str,
    *,
    idle_reason: Optional[str] = None,
    summary: Optional[str] = None,
    completed_task_id: Optional[str] = None,
    completed_status: Optional[str] = None,
    failure_reason: Optional[str] = None,
) -> IdleNotificationMessage:
    """Creates an idle notification message to send to the team leader."""
    from datetime import datetime, timezone
    return IdleNotificationMessage(
        type="idle_notification",
        from_agent=agent_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        idle_reason=idle_reason,
        summary=summary,
        completed_task_id=completed_task_id,
        completed_status=completed_status,
        failure_reason=failure_reason,
    )


def is_idle_notification(message_text: str) -> Optional[IdleNotificationMessage]:
    """Checks if a message text contains an idle notification."""
    try:
        parsed = json.loads(message_text)
        if isinstance(parsed, dict) and parsed.get("type") == "idle_notification":
            return IdleNotificationMessage(
                type=parsed.get("type", "idle_notification"),
                from_agent=parsed.get("from", ""),
                timestamp=parsed.get("timestamp", ""),
                idle_reason=parsed.get("idleReason"),
                summary=parsed.get("summary"),
                completed_task_id=parsed.get("completedTaskId"),
                completed_status=parsed.get("completedStatus"),
                failure_reason=parsed.get("failureReason"),
            )
    except Exception:
        pass
    return None


# ── Permission Request / Response ────────────────────────────


@dataclass
class PermissionRequestMessage:
    type: str
    request_id: str
    agent_id: str
    tool_name: str
    tool_use_id: str
    description: str
    input: Dict[str, Any]
    permission_suggestions: List[Any] = field(default_factory=list)


@dataclass
class PermissionResponseSuccessMessage:
    type: str
    request_id: str
    subtype: str  # 'success'
    response: Optional[Dict[str, Any]] = None


@dataclass
class PermissionResponseErrorMessage:
    type: str
    request_id: str
    subtype: str  # 'error'
    error: str = ""


PermissionResponseMessage = Union[PermissionResponseSuccessMessage, PermissionResponseErrorMessage]


def create_permission_request_message(
    *,
    request_id: str,
    agent_id: str,
    tool_name: str,
    tool_use_id: str,
    description: str,
    input: Dict[str, Any],
    permission_suggestions: Optional[List[Any]] = None,
) -> PermissionRequestMessage:
    """Creates a permission request message to send to the team leader."""
    return PermissionRequestMessage(
        type="permission_request",
        request_id=request_id,
        agent_id=agent_id,
        tool_name=tool_name,
        tool_use_id=tool_use_id,
        description=description,
        input=input,
        permission_suggestions=permission_suggestions or [],
    )


def create_permission_response_message(
    *,
    request_id: str,
    subtype: str,
    error: Optional[str] = None,
    updated_input: Optional[Dict[str, Any]] = None,
    permission_updates: Optional[List[Any]] = None,
) -> PermissionResponseMessage:
    """Creates a permission response message to send back to a worker."""
    if subtype == "error":
        return PermissionResponseErrorMessage(
            type="permission_response",
            request_id=request_id,
            subtype="error",
            error=error or "Permission denied",
        )
    return PermissionResponseSuccessMessage(
        type="permission_response",
        request_id=request_id,
        subtype="success",
        response={
            "updated_input": updated_input,
            "permission_updates": permission_updates,
        },
    )


def is_permission_request(message_text: str) -> Optional[PermissionRequestMessage]:
    """Checks if a message text contains a permission request."""
    try:
        parsed = json.loads(message_text)
        if isinstance(parsed, dict) and parsed.get("type") == "permission_request":
            return PermissionRequestMessage(
                type=parsed["type"],
                request_id=parsed.get("request_id", ""),
                agent_id=parsed.get("agent_id", ""),
                tool_name=parsed.get("tool_name", ""),
                tool_use_id=parsed.get("tool_use_id", ""),
                description=parsed.get("description", ""),
                input=parsed.get("input", {}),
                permission_suggestions=parsed.get("permission_suggestions", []),
            )
    except Exception:
        pass
    return None


def is_permission_response(message_text: str) -> Optional[PermissionResponseMessage]:
    """Checks if a message text contains a permission response."""
    try:
        parsed = json.loads(message_text)
        if isinstance(parsed, dict) and parsed.get("type") == "permission_response":
            subtype = parsed.get("subtype", "")
            if subtype == "error":
                return PermissionResponseErrorMessage(
                    type=parsed["type"],
                    request_id=parsed.get("request_id", ""),
                    subtype="error",
                    error=parsed.get("error", ""),
                )
            return PermissionResponseSuccessMessage(
                type=parsed["type"],
                request_id=parsed.get("request_id", ""),
                subtype="success",
                response=parsed.get("response"),
            )
    except Exception:
        pass
    return None


# ── Sandbox Permission ────────────────────────────────────────


@dataclass
class SandboxPermissionRequestMessage:
    type: str
    request_id: str
    worker_id: str
    worker_name: str
    host_pattern: Dict[str, str]
    created_at: int
    worker_color: Optional[str] = None


@dataclass
class SandboxPermissionResponseMessage:
    type: str
    request_id: str
    host: str
    allow: bool
    timestamp: str


def create_sandbox_permission_request_message(
    *,
    request_id: str,
    worker_id: str,
    worker_name: str,
    host: str,
    worker_color: Optional[str] = None,
) -> SandboxPermissionRequestMessage:
    """Creates a sandbox permission request message to send to the team leader."""
    return SandboxPermissionRequestMessage(
        type="sandbox_permission_request",
        request_id=request_id,
        worker_id=worker_id,
        worker_name=worker_name,
        worker_color=worker_color,
        host_pattern={"host": host},
        created_at=int(time.time() * 1000),
    )


def create_sandbox_permission_response_message(
    *,
    request_id: str,
    host: str,
    allow: bool,
) -> SandboxPermissionResponseMessage:
    """Creates a sandbox permission response message to send back to a worker."""
    from datetime import datetime, timezone
    return SandboxPermissionResponseMessage(
        type="sandbox_permission_response",
        request_id=request_id,
        host=host,
        allow=allow,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def is_sandbox_permission_request(message_text: str) -> Optional[SandboxPermissionRequestMessage]:
    """Checks if a message text contains a sandbox permission request."""
    try:
        parsed = json.loads(message_text)
        if isinstance(parsed, dict) and parsed.get("type") == "sandbox_permission_request":
            return SandboxPermissionRequestMessage(
                type=parsed["type"],
                request_id=parsed.get("requestId", ""),
                worker_id=parsed.get("workerId", ""),
                worker_name=parsed.get("workerName", ""),
                worker_color=parsed.get("workerColor"),
                host_pattern=parsed.get("hostPattern", {}),
                created_at=parsed.get("createdAt", 0),
            )
    except Exception:
        pass
    return None


def is_sandbox_permission_response(message_text: str) -> Optional[SandboxPermissionResponseMessage]:
    """Checks if a message text contains a sandbox permission response."""
    try:
        parsed = json.loads(message_text)
        if isinstance(parsed, dict) and parsed.get("type") == "sandbox_permission_response":
            return SandboxPermissionResponseMessage(
                type=parsed["type"],
                request_id=parsed.get("requestId", ""),
                host=parsed.get("host", ""),
                allow=parsed.get("allow", False),
                timestamp=parsed.get("timestamp", ""),
            )
    except Exception:
        pass
    return None


# ── Shutdown Messages ─────────────────────────────────────────


@dataclass
class ShutdownRequestMessage:
    type: str
    request_id: str
    from_agent: str
    timestamp: str
    reason: Optional[str] = None


@dataclass
class ShutdownApprovedMessage:
    type: str
    request_id: str
    from_agent: str
    timestamp: str
    pane_id: Optional[str] = None
    backend_type: Optional[str] = None


@dataclass
class ShutdownRejectedMessage:
    type: str
    request_id: str
    from_agent: str
    reason: str
    timestamp: str


def create_shutdown_request_message(
    *,
    request_id: str,
    from_agent: str,
    reason: Optional[str] = None,
) -> ShutdownRequestMessage:
    """Creates a shutdown request message to send to a teammate."""
    from datetime import datetime, timezone
    return ShutdownRequestMessage(
        type="shutdown_request",
        request_id=request_id,
        from_agent=from_agent,
        reason=reason,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def create_shutdown_approved_message(
    *,
    request_id: str,
    from_agent: str,
    pane_id: Optional[str] = None,
    backend_type: Optional[str] = None,
) -> ShutdownApprovedMessage:
    """Creates a shutdown approved message to send to the team leader."""
    from datetime import datetime, timezone
    return ShutdownApprovedMessage(
        type="shutdown_approved",
        request_id=request_id,
        from_agent=from_agent,
        timestamp=datetime.now(timezone.utc).isoformat(),
        pane_id=pane_id,
        backend_type=backend_type,
    )


def create_shutdown_rejected_message(
    *,
    request_id: str,
    from_agent: str,
    reason: str,
) -> ShutdownRejectedMessage:
    """Creates a shutdown rejected message to send to the team leader."""
    from datetime import datetime, timezone
    return ShutdownRejectedMessage(
        type="shutdown_rejected",
        request_id=request_id,
        from_agent=from_agent,
        reason=reason,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


async def send_shutdown_request_to_mailbox(
    target_name: str,
    team_name: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, str]:
    """
    Sends a shutdown request to a teammate's mailbox.
    Returns the requestId and target name.
    """
    import uuid
    from datetime import datetime, timezone

    sender_name = os.environ.get("CLAUDE_CODE_AGENT_NAME", "team_lead")
    request_id = f"shutdown-{target_name}-{uuid.uuid4().hex[:8]}"

    shutdown_message = create_shutdown_request_message(
        request_id=request_id,
        from_agent=sender_name,
        reason=reason,
    )

    msg_dict = asdict(shutdown_message)
    # Convert from_agent key to match TS format
    msg_dict["from"] = msg_dict.pop("from_agent")

    msg = TeammateMessage(
        from_agent=sender_name,
        text=json.dumps({
            "type": shutdown_message.type,
            "requestId": shutdown_message.request_id,
            "from": shutdown_message.from_agent,
            "reason": shutdown_message.reason,
            "timestamp": shutdown_message.timestamp,
        }),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    await write_to_mailbox(target_name, msg, team_name)

    return {"request_id": request_id, "target": target_name}


def is_shutdown_request(message_text: str) -> Optional[ShutdownRequestMessage]:
    """Checks if a message text contains a shutdown request."""
    try:
        parsed = json.loads(message_text)
        if isinstance(parsed, dict) and parsed.get("type") == "shutdown_request":
            return ShutdownRequestMessage(
                type=parsed["type"],
                request_id=parsed.get("requestId", ""),
                from_agent=parsed.get("from", ""),
                reason=parsed.get("reason"),
                timestamp=parsed.get("timestamp", ""),
            )
    except Exception:
        pass
    return None


def is_shutdown_approved(message_text: str) -> Optional[ShutdownApprovedMessage]:
    """Checks if a message text contains a shutdown approved message."""
    try:
        parsed = json.loads(message_text)
        if isinstance(parsed, dict) and parsed.get("type") == "shutdown_approved":
            return ShutdownApprovedMessage(
                type=parsed["type"],
                request_id=parsed.get("requestId", ""),
                from_agent=parsed.get("from", ""),
                timestamp=parsed.get("timestamp", ""),
                pane_id=parsed.get("paneId"),
                backend_type=parsed.get("backendType"),
            )
    except Exception:
        pass
    return None


def is_shutdown_rejected(message_text: str) -> Optional[ShutdownRejectedMessage]:
    """Checks if a message text contains a shutdown rejected message."""
    try:
        parsed = json.loads(message_text)
        if isinstance(parsed, dict) and parsed.get("type") == "shutdown_rejected":
            return ShutdownRejectedMessage(
                type=parsed["type"],
                request_id=parsed.get("requestId", ""),
                from_agent=parsed.get("from", ""),
                reason=parsed.get("reason", ""),
                timestamp=parsed.get("timestamp", ""),
            )
    except Exception:
        pass
    return None


# ── Plan Approval ─────────────────────────────────────────────


@dataclass
class PlanApprovalRequestMessage:
    type: str
    from_agent: str
    timestamp: str
    plan_file_path: str
    plan_content: str
    request_id: str


@dataclass
class PlanApprovalResponseMessage:
    type: str
    request_id: str
    approved: bool
    timestamp: str
    feedback: Optional[str] = None
    permission_mode: Optional[str] = None


def is_plan_approval_request(message_text: str) -> Optional[PlanApprovalRequestMessage]:
    """Checks if a message text contains a plan approval request."""
    try:
        parsed = json.loads(message_text)
        if isinstance(parsed, dict) and parsed.get("type") == "plan_approval_request":
            return PlanApprovalRequestMessage(
                type=parsed["type"],
                from_agent=parsed.get("from", ""),
                timestamp=parsed.get("timestamp", ""),
                plan_file_path=parsed.get("planFilePath", ""),
                plan_content=parsed.get("planContent", ""),
                request_id=parsed.get("requestId", ""),
            )
    except Exception:
        pass
    return None


def is_plan_approval_response(message_text: str) -> Optional[PlanApprovalResponseMessage]:
    """Checks if a message text contains a plan approval response."""
    try:
        parsed = json.loads(message_text)
        if isinstance(parsed, dict) and parsed.get("type") == "plan_approval_response":
            return PlanApprovalResponseMessage(
                type=parsed["type"],
                request_id=parsed.get("requestId", ""),
                approved=parsed.get("approved", False),
                timestamp=parsed.get("timestamp", ""),
                feedback=parsed.get("feedback"),
                permission_mode=parsed.get("permissionMode"),
            )
    except Exception:
        pass
    return None


# ── Task Assignment ───────────────────────────────────────────


@dataclass
class TaskAssignmentMessage:
    type: str
    task_id: str
    subject: str
    description: str
    assigned_by: str
    timestamp: str


def is_task_assignment(message_text: str) -> Optional[TaskAssignmentMessage]:
    """Checks if a message text contains a task assignment."""
    try:
        parsed = json.loads(message_text)
        if isinstance(parsed, dict) and parsed.get("type") == "task_assignment":
            return TaskAssignmentMessage(
                type=parsed["type"],
                task_id=parsed.get("taskId", ""),
                subject=parsed.get("subject", ""),
                description=parsed.get("description", ""),
                assigned_by=parsed.get("assignedBy", ""),
                timestamp=parsed.get("timestamp", ""),
            )
    except Exception:
        pass
    return None


# ── Team Permission Update ────────────────────────────────────


@dataclass
class TeamPermissionUpdateMessage:
    type: str
    permission_update: Dict[str, Any]
    directory_path: str
    tool_name: str


def is_team_permission_update(message_text: str) -> Optional[TeamPermissionUpdateMessage]:
    """Checks if a message text contains a team permission update."""
    try:
        parsed = json.loads(message_text)
        if isinstance(parsed, dict) and parsed.get("type") == "team_permission_update":
            return TeamPermissionUpdateMessage(
                type=parsed["type"],
                permission_update=parsed.get("permissionUpdate", {}),
                directory_path=parsed.get("directoryPath", ""),
                tool_name=parsed.get("toolName", ""),
            )
    except Exception:
        pass
    return None


# ── Mode Set Request ──────────────────────────────────────────


@dataclass
class ModeSetRequestMessage:
    type: str
    mode: str
    from_agent: str


def create_mode_set_request_message(
    *,
    mode: str,
    from_agent: str,
) -> ModeSetRequestMessage:
    """Creates a mode set request message to send to a teammate."""
    return ModeSetRequestMessage(
        type="mode_set_request",
        mode=mode,
        from_agent=from_agent,
    )


def is_mode_set_request(message_text: str) -> Optional[ModeSetRequestMessage]:
    """Checks if a message text contains a mode set request."""
    try:
        parsed = json.loads(message_text)
        if isinstance(parsed, dict) and parsed.get("type") == "mode_set_request":
            return ModeSetRequestMessage(
                type=parsed["type"],
                mode=parsed.get("mode", ""),
                from_agent=parsed.get("from", ""),
            )
    except Exception:
        pass
    return None


# ── Structured Protocol Check ─────────────────────────────────


def is_structured_protocol_message(message_text: str) -> bool:
    """
    Checks if a message text is a structured protocol message that should be
    routed by useInboxPoller rather than consumed as raw LLM context.
    """
    try:
        parsed = json.loads(message_text)
        if not isinstance(parsed, dict) or "type" not in parsed:
            return False
        msg_type = parsed["type"]
        return msg_type in (
            "permission_request",
            "permission_response",
            "sandbox_permission_request",
            "sandbox_permission_response",
            "shutdown_request",
            "shutdown_approved",
            "team_permission_update",
            "mode_set_request",
            "plan_approval_request",
            "plan_approval_response",
        )
    except Exception:
        return False


# ── Predicate-based Read ──────────────────────────────────────


async def mark_messages_as_read_by_predicate(
    agent_name: str,
    predicate: Callable[[TeammateMessage], bool],
    team_name: Optional[str] = None,
) -> None:
    """
    Marks only messages matching a predicate as read, leaving others unread.
    Uses the same file-locking mechanism as mark_messages_as_read.
    """
    path = get_inbox_path(agent_name, team_name)
    async with _FileLock(path):
        messages = await asyncio.to_thread(_read_inbox_sync, path)
        if not messages:
            return

        updated = [
            TeammateMessage(**{**asdict(m), "read": True})
            if not m.read and predicate(m)
            else m
            for m in messages
        ]
        await asyncio.to_thread(_write_inbox_sync, path, updated)
