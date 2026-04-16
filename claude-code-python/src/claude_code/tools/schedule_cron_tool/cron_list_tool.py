"""Cron list tool. Ported from ScheduleCronTool/cronListTool.ts"""
from __future__ import annotations
from claude_code.tools.schedule_cron_tool.cron_prompts import (
    CRON_LIST_TOOL_NAME, CRON_LIST_DESCRIPTION, build_cron_list_prompt, is_durable_cron_enabled)


class CronListTool:
    name = CRON_LIST_TOOL_NAME
    description = CRON_LIST_DESCRIPTION

    def get_schema(self) -> dict:
        durable = is_durable_cron_enabled()
        return {
            "name": self.name,
            "description": build_cron_list_prompt(durable),
            "input_schema": {"type": "object", "properties": {}, "required": []}
        }

    async def call(self, **kwargs) -> dict:
        from claude_code.utils.cron_scheduler import CronScheduler
        scheduler = CronScheduler.get_instance()
        jobs = scheduler.list_jobs() if scheduler else []
        return {"jobs": jobs}
