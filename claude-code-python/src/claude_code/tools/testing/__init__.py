"""Testing utilities for tool tests.

Provides shared helpers and mocks for Claude Code tool test suites.
Ported from tools/testing/ (TestingPermissionTool.tsx).

Only the ``TestingPermissionTool`` is exposed here — it is a no-op tool that
always requests permission, used exclusively in end-to-end test scenarios.
The tool is disabled outside of ``NODE_ENV=test`` environments (mirrors the TS
``isEnabled`` check: ``process.env.NODE_ENV === 'test'``).
"""
from __future__ import annotations

import os
from typing import Any

TESTING_PERMISSION_TOOL_NAME = "TestingPermission"


class TestingPermissionTool:
    """A no-op tool that always triggers a permission dialog.

    Used in E2E tests to verify that the permission flow works end-to-end.
    Disabled in production (requires ``CLAUDE_ENV=test``).
    """

    name = TESTING_PERMISSION_TOOL_NAME
    description = "Test tool that always asks for permission before executing."
    is_read_only = True
    is_concurrency_safe = True

    def is_enabled(self) -> bool:
        return os.environ.get("CLAUDE_ENV") == "test"

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        }

    async def check_permissions(self, **kwargs: Any) -> dict:
        """Always require explicit permission — never auto-approve."""
        return {"behavior": "ask", "message": "Run test?"}

    async def call(self, **kwargs: Any) -> dict:
        return {"result": "TestingPermission executed"}


__all__ = ["TestingPermissionTool", "TESTING_PERMISSION_TOOL_NAME"]
