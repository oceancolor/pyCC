"""
dump_prompts.py - Dump/cache API requests for debugging.

Port of TypeScript dumpPrompts.ts.
"""

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_CACHED_REQUESTS = 5

_cached_api_requests: List[Dict[str, Any]] = []
_dump_state: Dict[str, Dict[str, Any]] = {}


def get_last_api_requests() -> List[Dict[str, Any]]:
    """Get the cached API requests."""
    return list(_cached_api_requests)


def clear_api_request_cache() -> None:
    """Clear the API request cache."""
    global _cached_api_requests
    _cached_api_requests = []


def clear_dump_state(agent_or_session_id: str) -> None:
    """Clear the dump state for a specific agent/session."""
    _dump_state.pop(agent_or_session_id, None)


def clear_all_dump_state() -> None:
    """Clear all dump state."""
    _dump_state.clear()


def add_api_request_to_cache(request_data: Any) -> None:
    """Add an API request to the cache (ant users only)."""
    if os.environ.get('USER_TYPE') != 'ant':
        return

    from datetime import datetime, timezone

    _cached_api_requests.append({
        'timestamp': datetime.now(tz=timezone.utc).isoformat(),
        'request': request_data,
    })

    while len(_cached_api_requests) > MAX_CACHED_REQUESTS:
        _cached_api_requests.pop(0)


def get_dump_prompts_path(agent_or_session_id: Optional[str] = None) -> str:
    """Get the path for the dump prompts file."""
    from ...utils.env_utils import get_claude_config_home_dir
    from ...bootstrap.state import get_session_id

    session_id = agent_or_session_id or get_session_id()
    return str(Path(get_claude_config_home_dir()) / 'dump-prompts' / f"{session_id}.jsonl")


def _hash_string(s: str) -> str:
    """Hash a string with SHA-256."""
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def _init_fingerprint(req: Dict[str, Any]) -> str:
    """Compute a cheap fingerprint for change detection."""
    tools = req.get('tools', []) or []
    system = req.get('system')
    model = req.get('model', '')

    if isinstance(system, str):
        sys_len = len(system)
    elif isinstance(system, list):
        sys_len = sum(
            len(b.get('text', '') if isinstance(b, dict) else '')
            for b in system
        )
    else:
        sys_len = 0

    tool_names = ','.join(t.get('name', '') for t in tools if isinstance(t, dict))
    return f"{model}|{tool_names}|{sys_len}"


def _append_to_file(file_path: str, entries: List[str]) -> None:
    """Append entries to a file asynchronously (best effort)."""
    if not entries:
        return

    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'a', encoding='utf-8') as f:
            f.write('\n'.join(entries) + '\n')
    except Exception as e:
        logger.debug(f'dump_prompts: append failed: {e}')


def _dump_request(
    body: str,
    ts: str,
    state: Dict[str, Any],
    file_path: str,
) -> None:
    """Dump a request to file for debugging."""
    try:
        req = json.loads(body)
        add_api_request_to_cache(req)

        if os.environ.get('USER_TYPE') != 'ant':
            return

        entries: List[str] = []
        messages = req.get('messages', []) or []

        fingerprint = _init_fingerprint(req)

        if not state.get('initialized') or fingerprint != state.get('lastInitFingerprint'):
            init_data = {k: v for k, v in req.items() if k != 'messages'}
            init_data_str = json.dumps(init_data, ensure_ascii=False)
            init_data_hash = _hash_string(init_data_str)
            state['lastInitFingerprint'] = fingerprint

            if not state.get('initialized'):
                state['initialized'] = True
                state['lastInitDataHash'] = init_data_hash
                entries.append(
                    f'{{"type":"init","timestamp":"{ts}","data":{init_data_str}}}'
                )
            elif init_data_hash != state.get('lastInitDataHash'):
                state['lastInitDataHash'] = init_data_hash
                entries.append(
                    f'{{"type":"system_update","timestamp":"{ts}","data":{init_data_str}}}'
                )

        seen_count = state.get('messageCountSeen', 0)
        for msg in messages[seen_count:]:
            if isinstance(msg, dict) and msg.get('role') == 'user':
                entries.append(json.dumps({'type': 'message', 'timestamp': ts, 'data': msg}))

        state['messageCountSeen'] = len(messages)
        _append_to_file(file_path, entries)

    except Exception as e:
        logger.debug(f'dump_prompts: request dump failed: {e}')


def create_dump_prompts_fetch(agent_or_session_id: str) -> Callable:
    """
    Create a fetch wrapper that dumps prompts to file.

    Args:
        agent_or_session_id: Agent or session identifier

    Returns:
        Async fetch function.
    """
    file_path = get_dump_prompts_path(agent_or_session_id)

    async def dump_fetch(url: str, **kwargs: Any) -> Any:
        import aiohttp
        from datetime import datetime, timezone

        state = _dump_state.setdefault(agent_or_session_id, {
            'initialized': False,
            'messageCountSeen': 0,
            'lastInitDataHash': '',
            'lastInitFingerprint': '',
        })

        timestamp: Optional[str] = None
        method = kwargs.get('method', 'GET').upper()
        body = kwargs.get('data') or kwargs.get('json')

        if method == 'POST' and body:
            timestamp = datetime.now(tz=timezone.utc).isoformat()
            body_str = json.dumps(body) if isinstance(body, dict) else str(body)
            # Defer dump so it doesn't block the actual call
            import asyncio
            asyncio.get_event_loop().call_soon(
                lambda: _dump_request(body_str, timestamp, state, file_path)
            )

        # Make the actual request
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method,
                url,
                **{k: v for k, v in kwargs.items() if k not in ('method',)},
            ) as response:
                return response

    return dump_fetch
