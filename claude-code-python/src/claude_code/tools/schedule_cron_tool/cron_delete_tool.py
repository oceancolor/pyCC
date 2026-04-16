"""Cron delete tool. Ported from ScheduleCronTool/cronDeleteTool.ts"""
from __future__ import annotations
from claude_code.tools.schedule_cron_tool.cron_prompts import (
    CRON_DELETE_TOOL_NAME, CRON_DELETE_DESCRIPTION, build_cron_delete_prompt, is_durable_cron_enabled)


class CronDeleteTool:
    name = CRON_DELETE_TOOL_NAME
    description = CRON_DELETE_DESCRIPTION

    def get_schema(self) -> dict:
        durable = is_durable_cron_enabled()
        return {
            "name": self.name,
            "description": build_cron_delete_prompt(durable),
            "input_schema": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The ID of the cron job to delete"}
                },
                "required": ["job_id"]
            }
        }

    async def call(self, job_id: str, **kwargs) -> dict:
        from claude_code.utils.cron_scheduler import CronScheduler
        scheduler = CronScheduler.get_instance()
        success = scheduler.delete_job(job_id) if scheduler else False
        return {"success": success, "job_id": job_id}
