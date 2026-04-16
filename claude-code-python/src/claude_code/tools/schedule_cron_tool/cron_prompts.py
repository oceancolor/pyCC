"""Cron tool names, descriptions and prompts. Ported from ScheduleCronTool/prompt.ts"""
from __future__ import annotations
import os

CRON_CREATE_TOOL_NAME = "CronCreate"
CRON_DELETE_TOOL_NAME = "CronDelete"
CRON_LIST_TOOL_NAME = "CronList"

DEFAULT_MAX_AGE_DAYS = 30


def is_kairos_cron_enabled() -> bool:
    if os.environ.get("CLAUDE_CODE_DISABLE_CRON", "").lower() in ("1", "true"):
        return False
    return True  # Default enabled; GB kill switch stub


def is_durable_cron_enabled() -> bool:
    return True  # Default enabled


def build_cron_create_description(durable_enabled: bool) -> str:
    if durable_enabled:
        return ("Schedule a prompt to run at a future time — either recurring on a cron schedule, "
                "or once at a specific time. Pass durable: true to persist.")
    return ("Schedule a prompt to run at a future time within this Claude session — "
            "either recurring on a cron schedule, or once at a specific time.")


CRON_DELETE_DESCRIPTION = "Cancel a scheduled cron job by ID"

def build_cron_delete_prompt(durable_enabled: bool) -> str:
    if durable_enabled:
        return f"Cancel a cron job previously scheduled with {CRON_CREATE_TOOL_NAME}. Removes it from disk or memory."
    return f"Cancel a cron job previously scheduled with {CRON_CREATE_TOOL_NAME}. Removes it from the in-memory session store."


CRON_LIST_DESCRIPTION = "List scheduled cron jobs"

def build_cron_list_prompt(durable_enabled: bool) -> str:
    if durable_enabled:
        return f"List all cron jobs scheduled via {CRON_CREATE_TOOL_NAME}, both durable and session-only."
    return f"List all cron jobs scheduled via {CRON_CREATE_TOOL_NAME} in this session."
