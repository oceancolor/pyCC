"""Teammate Mailbox — file-based messaging for agent swarms."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

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
