"""CronCreateTool stub. Ported from ScheduleCronTool/CronCreateTool.ts"""
from __future__ import annotations
from typing import Any, Optional
from claude_code.tools.schedule_cron_tool.prompt import (
    CRON_CREATE_TOOL_NAME,
    build_cron_create_description,
    build_cron_create_prompt,
    is_durable_cron_enabled,
    is_kairos_cron_enabled,
    DEFAULT_MAX_AGE_DAYS,
)


class CronCreateTool:
    """Create scheduled cron tasks."""
    name = CRON_CREATE_TOOL_NAME

    @property
    def is_enabled(self) -> bool:
        return is_kairos_cron_enabled()

    @property
    def description(self) -> str:
        return build_cron_create_description(is_durable_cron_enabled())

    @property
    def prompt(self) -> str:
        return build_cron_create_prompt(is_durable_cron_enabled())

    async def call(
        self,
        cron: str,
        prompt: str,
        recurring: bool = True,
        durable: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Schedule a cron task."""
        import uuid
        job_id = str(uuid.uuid4())
        return {
            "id": job_id,
            "cron": cron,
            "prompt": prompt,
            "recurring": recurring,
            "durable": durable,
        }
