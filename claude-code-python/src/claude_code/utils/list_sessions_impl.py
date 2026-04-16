"""
列出历史会话的独立实现。
原始 TS: utils/listSessionsImpl.ts

扫描 ~/.claude/projects/ 目录，提取每个会话的元数据摘要。
仅依赖 session_storage_portable 中的可移植工具函数。
"""
from __future__ import annotations

import asyncio
import functools
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from claude_code.utils.session_storage_portable import (
    MAX_SANITIZED_LENGTH, LiteSessionFile, canonicalize_path,
    extract_first_prompt_from_head, extract_json_string_field,
    extract_last_json_string_field, find_project_dir, get_projects_dir,
    read_session_lite, sanitize_path, validate_uuid,
)

READ_BATCH_SIZE = 32


@dataclass
class SessionInfo:
    """会话元数据摘要（仅需 stat + head/tail 读取）。"""
    session_id: str
    summary: str
    last_modified: float
    file_size: Optional[int] = None
    custom_title: Optional[str] = None
    first_prompt: Optional[str] = None
    git_branch: Optional[str] = None
    cwd: Optional[str] = None
    tag: Optional[str] = None
    created_at: Optional[float] = None


@dataclass
class SessionSummary:
    """简化 API 返回类型（向后兼容）。"""
    session_id: str
    cwd: Optional[str]
    timestamp: float
    message_count: int
    title: str


@dataclass
class ListSessionsOptions:
    dir: Optional[str] = None
    limit: Optional[int] = None
    offset: int = 0
    include_worktrees: bool = True


def parse_session_info_from_lite(
    session_id: str,
    lite: LiteSessionFile,
    project_path: Optional[str] = None,
) -> Optional[SessionInfo]:
    """从 lite 读取结果中解析 SessionInfo；sidechain 会话或无摘要时返回 None。"""
    head, tail = lite.head, lite.tail
    first_nl = head.find("\n")
    first_line = head[:first_nl] if first_nl >= 0 else head
    if '"isSidechain":true' in first_line or '"isSidechain": true' in first_line:
        return None

    custom_title = (
        extract_last_json_string_field(tail, "customTitle")
        or extract_last_json_string_field(head, "customTitle")
        or extract_last_json_string_field(tail, "aiTitle")
        or extract_last_json_string_field(head, "aiTitle")
    ) or None
    first_prompt = extract_first_prompt_from_head(head) or None
    summary = (
        custom_title
        or extract_last_json_string_field(tail, "lastPrompt")
        or extract_last_json_string_field(tail, "summary")
        or first_prompt
    )
    if not summary:
        return None

    first_ts = extract_json_string_field(head, "timestamp")
    created_at: Optional[float] = None
    if first_ts:
        import datetime
        try:
            created_at = datetime.datetime.fromisoformat(
                first_ts.replace("Z", "+00:00")
            ).timestamp() * 1000.0
        except ValueError:
            pass

    tag: Optional[str] = None
    for line in reversed(tail.split("\n")):
        if line.startswith('{"type":"tag"'):
            tag = extract_last_json_string_field(line, "tag") or None
            break

    return SessionInfo(
        session_id=session_id, summary=summary, last_modified=lite.mtime,
        file_size=lite.size, custom_title=custom_title,
        first_prompt=first_prompt,
        git_branch=(extract_last_json_string_field(tail, "gitBranch")
                    or extract_json_string_field(head, "gitBranch")) or None,
        cwd=extract_json_string_field(head, "cwd") or project_path or None,
        tag=tag, created_at=created_at,
    )


@dataclass
class _Candidate:
    session_id: str
    file_path: str
    mtime: float
    project_path: Optional[str] = None


async def _list_candidates(
    project_dir: str,
    do_stat: bool,
    project_path: Optional[str] = None,
) -> List[_Candidate]:
    loop = asyncio.get_event_loop()
    try:
        names = await loop.run_in_executor(None, os.listdir, project_dir)
    except OSError:
        return []

    async def _make(name: str) -> Optional[_Candidate]:
        if not name.endswith(".jsonl"):
            return None
        sid = validate_uuid(name[:-6])
        if not sid:
            return None
        fp = os.path.join(project_dir, name)
        if not do_stat:
            return _Candidate(sid, fp, 0.0, project_path)
        try:
            st = await loop.run_in_executor(None, os.stat, fp)
            return _Candidate(sid, fp, st.st_mtime * 1000.0, project_path)
        except OSError:
            return None

    results = await asyncio.gather(*[_make(n) for n in names])
    return [c for c in results if c is not None]


async def _read_candidate(c: _Candidate) -> Optional[SessionInfo]:
    lite = await read_session_lite(c.file_path)
    if lite is None:
        return None
    info = parse_session_info_from_lite(c.session_id, lite, c.project_path)
    if info and c.mtime:
        info.last_modified = c.mtime
    return info


async def _apply_sort_and_limit(
    candidates: List[_Candidate], limit: Optional[int], offset: int
) -> List[SessionInfo]:
    def _cmp(a: _Candidate, b: _Candidate) -> int:
        if b.mtime != a.mtime:
            return 1 if b.mtime > a.mtime else -1
        return (b.session_id > a.session_id) - (b.session_id < a.session_id)

    candidates.sort(key=functools.cmp_to_key(_cmp))
    want = limit if (limit and limit > 0) else float("inf")
    sessions: List[SessionInfo] = []
    seen: Set[str] = set()
    skipped = 0
    i = 0
    while i < len(candidates) and len(sessions) < want:
        batch = candidates[i: i + READ_BATCH_SIZE]
        results = await asyncio.gather(*[_read_candidate(c) for c in batch])
        for r in results:
            i += 1
            if r is None or r.session_id in seen:
                continue
            seen.add(r.session_id)
            if skipped < offset:
                skipped += 1
                continue
            sessions.append(r)
            if len(sessions) >= want:
                break
    return sessions


async def _read_all_and_sort(candidates: List[_Candidate]) -> List[SessionInfo]:
    all_results = await asyncio.gather(*[_read_candidate(c) for c in candidates])
    by_id: Dict[str, SessionInfo] = {}
    for s in all_results:
        if s and (s.session_id not in by_id
                  or s.last_modified > by_id[s.session_id].last_modified):
            by_id[s.session_id] = s
    sessions = sorted(by_id.values(), key=lambda s: (-s.last_modified, s.session_id))
    return sessions


async def _gather_project_candidates(dir_path: str, do_stat: bool) -> List[_Candidate]:
    canonical = await canonicalize_path(dir_path)
    project_dir = await find_project_dir(canonical)
    if not project_dir:
        return []
    return await _list_candidates(project_dir, do_stat, canonical)


async def _gather_all_candidates(do_stat: bool) -> List[_Candidate]:
    projects_dir = get_projects_dir()
    loop = asyncio.get_event_loop()
    try:
        dirs = await loop.run_in_executor(
            None, lambda: [e.name for e in os.scandir(projects_dir) if e.is_dir()]
        )
    except OSError:
        return []
    groups = await asyncio.gather(*[
        _list_candidates(os.path.join(projects_dir, d), do_stat) for d in dirs
    ])
    return [c for g in groups for c in g]


async def list_sessions_impl(options: Optional[ListSessionsOptions] = None) -> List[SessionInfo]:
    """列出会话元数据。dir 指定时仅返回该项目会话，否则返回所有会话。"""
    opts = options or ListSessionsOptions()
    do_stat = bool((opts.limit and opts.limit > 0) or opts.offset > 0)
    candidates = (
        await _gather_project_candidates(opts.dir, do_stat)
        if opts.dir
        else await _gather_all_candidates(do_stat)
    )
    if not do_stat:
        return await _read_all_and_sort(candidates)
    return await _apply_sort_and_limit(candidates, opts.limit, opts.offset)


async def list_sessions(
    cwd: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[SessionSummary]:
    """简化 API（向后兼容）：返回 SessionSummary 列表。"""
    infos = await list_sessions_impl(ListSessionsOptions(dir=cwd, limit=limit))
    return [
        SessionSummary(
            session_id=i.session_id, cwd=i.cwd,
            timestamp=i.last_modified, message_count=0, title=i.summary,
        )
        for i in infos
    ]
