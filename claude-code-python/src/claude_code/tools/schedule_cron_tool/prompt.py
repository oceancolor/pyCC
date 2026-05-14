"""ScheduleCronTool prompt constants. Ported from ScheduleCronTool/prompt.ts"""
from __future__ import annotations

CRON_CREATE_TOOL_NAME = "CronCreate"
CRON_DELETE_TOOL_NAME = "CronDelete"
CRON_LIST_TOOL_NAME = "CronList"

DEFAULT_MAX_AGE_DAYS = 30


def is_kairos_cron_enabled() -> bool:
    """Check if cron scheduling is enabled (stub: always False unless env override)."""
    import os
    disable = os.environ.get("CLAUDE_CODE_DISABLE_CRON", "").lower()
    return disable not in ("1", "true", "yes")


def is_durable_cron_enabled() -> bool:
    """Check if durable (disk-persistent) cron is enabled."""
    return True


def build_cron_create_description(durable_enabled: bool) -> str:
    if durable_enabled:
        return (
            "Schedule a prompt to run at a future time — either recurring on a cron schedule, "
            "or once at a specific time. Pass durable: true to persist to "
            ".claude/scheduled_tasks.json; otherwise session-only."
        )
    return (
        "Schedule a prompt to run at a future time within this Claude session — "
        "either recurring on a cron schedule, or once at a specific time."
    )


def build_cron_create_prompt(durable_enabled: bool) -> str:
    if durable_enabled:
        durability_section = f"""## Durability

By default (durable: false) the job lives only in this Claude session — nothing is written to disk, and the job is gone when Claude exits. Pass durable: true to write to .claude/scheduled_tasks.json so the job survives restarts. Only use durable: true when the user explicitly asks for the task to persist ("keep doing this every day", "set this up permanently"). Most "remind me in 5 minutes" / "check back in an hour" requests should stay session-only."""
        durable_runtime_note = (
            f"Durable jobs persist to .claude/scheduled_tasks.json and survive session "
            f"restarts — on next launch they resume automatically. One-shot durable tasks "
            f"that were missed while the REPL was closed are surfaced for catch-up. "
            f"Session-only jobs die with the process. "
        )
    else:
        durability_section = """## Session-only

Jobs live only in this Claude session — nothing is written to disk, and the job is gone when Claude exits."""
        durable_runtime_note = ""

    return f"""Schedule a prompt to be enqueued at a future time. Use for both recurring schedules and one-shot reminders.

Uses standard 5-field cron in the user's local timezone: minute hour day-of-month month day-of-week. "0 9 * * *" means 9am local — no timezone conversion needed.

## One-shot tasks (recurring: false)

For "remind me at X" or "at <time>, do Y" requests — fire once then auto-delete.
Pin minute/hour/day-of-month/month to specific values:
  "remind me at 2:30pm today to check the deploy" → cron: "30 14 <today_dom> <today_month> *", recurring: false
  "tomorrow morning, run the smoke test" → cron: "57 8 <tomorrow_dom> <tomorrow_month> *", recurring: false

## Recurring jobs (recurring: true, the default)

For "every N minutes" / "every hour" / "weekdays at 9am" requests:
  "*/5 * * * *" (every 5 min), "0 * * * *" (hourly), "0 9 * * 1-5" (weekdays at 9am local)

## Avoid the :00 and :30 minute marks when the task allows it

Every user who asks for "9am" gets `0 9`, and every user who asks for "hourly" gets `0 *` — which means requests from across the planet land on the API at the same instant. When the user's request is approximate, pick a minute that is NOT 0 or 30:
  "every morning around 9" → "57 8 * * *" or "3 9 * * *" (not "0 9 * * *")
  "hourly" → "7 * * * *" (not "0 * * * *")
  "in an hour or so, remind me to..." → pick whatever minute you land on, don't round

Only use minute 0 or 30 when the user names that exact time and clearly means it ("at 9:00 sharp", "at half past", coordinating with a meeting). When in doubt, nudge a few minutes early or late — the user will not notice, and the fleet will.

{durability_section}

## Runtime behavior

Jobs only fire while the REPL is idle (not mid-query). {durable_runtime_note}The scheduler adds a small deterministic jitter on top of whatever you pick: recurring tasks fire up to 10% of their period late (max 15 min); one-shot tasks landing on :00 or :30 fire up to 90 s early. Picking an off-minute is still the bigger lever.

Recurring tasks auto-expire after {DEFAULT_MAX_AGE_DAYS} days — they fire one final time, then are deleted. This bounds session lifetime. Tell the user about the {DEFAULT_MAX_AGE_DAYS}-day limit when scheduling recurring jobs.

Returns a job ID you can pass to {CRON_DELETE_TOOL_NAME}."""


CRON_DELETE_DESCRIPTION = "Cancel a scheduled cron job by ID"


def build_cron_delete_prompt(durable_enabled: bool) -> str:
    if durable_enabled:
        return (
            f"Cancel a cron job previously scheduled with {CRON_CREATE_TOOL_NAME}. "
            "Removes it from .claude/scheduled_tasks.json (durable jobs) or the "
            "in-memory session store (session-only jobs)."
        )
    return (
        f"Cancel a cron job previously scheduled with {CRON_CREATE_TOOL_NAME}. "
        "Removes it from the in-memory session store."
    )


CRON_LIST_DESCRIPTION = "List scheduled cron jobs"


def build_cron_list_prompt(durable_enabled: bool) -> str:
    if durable_enabled:
        return (
            f"List all cron jobs scheduled via {CRON_CREATE_TOOL_NAME}, both durable "
            "(.claude/scheduled_tasks.json) and session-only."
        )
    return f"List all cron jobs scheduled via {CRON_CREATE_TOOL_NAME} in this session."
