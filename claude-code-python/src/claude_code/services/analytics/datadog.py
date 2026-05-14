"""Datadog analytics integration. Ported from services/analytics/datadog.ts"""
from __future__ import annotations
import asyncio
import hashlib
import os
import time
from typing import Any, Dict, List, Optional

_DATADOG_LOGS_ENDPOINT = "https://http-intake.logs.us5.datadoghq.com/api/v2/logs"
_DATADOG_CLIENT_TOKEN = "pubbbf48e6d78dae54bceaa4acf463299bf"
_DEFAULT_FLUSH_INTERVAL_MS = 15000
_MAX_BATCH_SIZE = 100
_NETWORK_TIMEOUT_S = 5
_NUM_USER_BUCKETS = 30

_DATADOG_ALLOWED_EVENTS = frozenset([
    "chrome_bridge_connection_succeeded", "chrome_bridge_connection_failed",
    "chrome_bridge_disconnected", "chrome_bridge_tool_call_completed",
    "chrome_bridge_tool_call_error", "chrome_bridge_tool_call_started",
    "chrome_bridge_tool_call_timeout", "tengu_api_error", "tengu_api_success",
    "tengu_brief_mode_enabled", "tengu_brief_mode_toggled", "tengu_brief_send",
    "tengu_cancel", "tengu_compact_failed", "tengu_exit", "tengu_flicker",
    "tengu_init", "tengu_model_fallback_triggered", "tengu_oauth_error",
    "tengu_oauth_success", "tengu_oauth_token_refresh_failure",
    "tengu_oauth_token_refresh_success", "tengu_oauth_token_refresh_lock_acquiring",
    "tengu_oauth_token_refresh_lock_acquired", "tengu_oauth_token_refresh_starting",
    "tengu_oauth_token_refresh_completed", "tengu_oauth_token_refresh_lock_releasing",
    "tengu_oauth_token_refresh_lock_released", "tengu_query_error",
    "tengu_session_file_read", "tengu_started", "tengu_tool_use_error",
    "tengu_tool_use_granted_in_prompt_permanent", "tengu_tool_use_granted_in_prompt_temporary",
    "tengu_tool_use_rejected_in_prompt", "tengu_tool_use_success",
    "tengu_uncaught_exception", "tengu_unhandled_rejection",
    "tengu_voice_recording_started", "tengu_voice_toggled",
    "tengu_team_mem_sync_pull", "tengu_team_mem_sync_push",
    "tengu_team_mem_sync_started", "tengu_team_mem_entries_capped",
])

_TAG_FIELDS = [
    "arch", "clientType", "errorType", "http_status_range", "http_status",
    "kairosActive", "model", "platform", "provider", "skillMode",
    "subscriptionType", "toolName", "userBucket", "userType", "version", "versionBase",
]

_log_batch: List[Dict[str, Any]] = []
_flush_task: Optional[asyncio.Task] = None
_datadog_initialized: Optional[bool] = None


def _camel_to_snake(s: str) -> str:
    import re
    return re.sub(r'[A-Z]', lambda m: f"_{m.group(0).lower()}", s)


def _get_flush_interval_ms() -> int:
    val = os.environ.get("CLAUDE_CODE_DATADOG_FLUSH_INTERVAL_MS", "")
    try:
        return int(val)
    except ValueError:
        return _DEFAULT_FLUSH_INTERVAL_MS


async def _flush_logs() -> None:
    global _log_batch
    if not _log_batch:
        return
    to_send = _log_batch
    _log_batch = []
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _DATADOG_LOGS_ENDPOINT,
                json=to_send,
                headers={"Content-Type": "application/json", "DD-API-KEY": _DATADOG_CLIENT_TOKEN},
                timeout=aiohttp.ClientTimeout(total=_NETWORK_TIMEOUT_S),
            ) as resp:
                await resp.read()
    except Exception:
        pass


def _get_user_bucket() -> int:
    """Hash user ID into one of NUM_USER_BUCKETS buckets for cardinality reduction."""
    try:
        from claude_code.utils.config import get_or_create_user_id
        user_id = get_or_create_user_id()
    except Exception:
        user_id = "unknown"
    digest = hashlib.sha256(user_id.encode()).hexdigest()
    return int(digest[:8], 16) % _NUM_USER_BUCKETS


async def initialize_datadog() -> bool:
    """Initialize Datadog. Idempotent via module-level state."""
    global _datadog_initialized
    if _datadog_initialized is not None:
        return _datadog_initialized
    from claude_code.services.analytics.config import is_analytics_disabled
    if is_analytics_disabled():
        _datadog_initialized = False
        return False
    _datadog_initialized = True
    return True


async def shutdown_datadog() -> None:
    """Flush remaining Datadog logs and shut down."""
    global _flush_task
    if _flush_task and not _flush_task.done():
        _flush_task.cancel()
        _flush_task = None
    await _flush_logs()


async def track_datadog_event(
    event_name: str,
    properties: Dict[str, Any],
) -> None:
    """Track an analytics event to Datadog."""
    global _log_batch, _flush_task

    if os.environ.get("NODE_ENV") != "production":
        return

    try:
        from claude_code.utils.model.providers import get_api_provider
        if get_api_provider() != "firstParty":
            return
    except Exception:
        return

    initialized = _datadog_initialized
    if initialized is None:
        initialized = await initialize_datadog()
    if not initialized or event_name not in _DATADOG_ALLOWED_EVENTS:
        return

    try:
        all_data: Dict[str, Any] = {**properties, "userBucket": _get_user_bucket()}

        # Normalize MCP tool names
        if isinstance(all_data.get("toolName"), str) and all_data["toolName"].startswith("mcp__"):
            all_data["toolName"] = "mcp"

        # Normalize model names for non-ant users
        if os.environ.get("USER_TYPE") != "ant" and isinstance(all_data.get("model"), str):
            import re
            all_data["model"] = re.sub(r'\[1m\]$', '', all_data["model"], flags=re.IGNORECASE)

        # Truncate dev version
        if isinstance(all_data.get("version"), str):
            import re
            all_data["version"] = re.sub(
                r'^(\d+\.\d+\.\d+-dev\.\d{8})\.t\d+\.sha[a-f0-9]+$',
                r'\1', all_data["version"]
            )

        # Transform status to http_status
        if all_data.get("status") is not None:
            status_code = str(all_data["status"])
            all_data["http_status"] = status_code
            first_digit = status_code[0] if status_code else ""
            if "1" <= first_digit <= "5":
                all_data["http_status_range"] = f"{first_digit}xx"
            del all_data["status"]

        tags = [f"event:{event_name}"] + [
            f"{_camel_to_snake(f)}:{all_data[f]}"
            for f in _TAG_FIELDS
            if all_data.get(f) is not None
        ]

        log: Dict[str, Any] = {
            "ddsource": "nodejs",
            "ddtags": ",".join(tags),
            "message": event_name,
            "service": "claude-code",
            "hostname": "claude-code",
            "env": os.environ.get("USER_TYPE"),
        }
        for key, value in all_data.items():
            if value is not None:
                log[_camel_to_snake(key)] = value

        _log_batch.append(log)

        if len(_log_batch) >= _MAX_BATCH_SIZE:
            if _flush_task and not _flush_task.done():
                _flush_task.cancel()
                _flush_task = None
            asyncio.ensure_future(_flush_logs())
        else:
            if _flush_task is None or _flush_task.done():
                delay = _get_flush_interval_ms() / 1000.0
                loop = asyncio.get_event_loop()
                _flush_task = loop.call_later(delay, lambda: asyncio.ensure_future(_flush_logs()))  # type: ignore[assignment]
    except Exception:
        pass


# Keep the original send_datadog_event name as an alias
async def send_datadog_event(event: str, tags: dict = None, value: float = 1.0) -> None:  # type: ignore[assignment]
    props: Dict[str, Any] = {"value": value}
    if tags:
        props.update(tags)
    await track_datadog_event(event, props)
