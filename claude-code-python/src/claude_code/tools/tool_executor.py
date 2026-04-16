# 原始 TS: Tool.ts (buildTool / ToolDef dispatch logic)
"""
tool_executor.py — 工具执行器。

根据 Anthropic API 返回的 tool_use 内容块，查找对应工具并执行。

使用示例::

    executor = ToolExecutor(registry)
    result = await executor.execute(tool_use_block)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..tool import Tool as ToolBase, ToolUseContext
ToolResult = dict  # compat alias
from .tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolExecutionError(Exception):
    """Raised when a tool cannot be found or its execution fails fatally."""


class ToolExecutor:
    """
    Dispatch tool_use blocks from the Anthropic API to registered tools.

    Supports both sync and async execution (sync tools are wrapped in an
    executor thread to avoid blocking the event loop).
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    # ------------------------------------------------------------------
    # Sync interface
    # ------------------------------------------------------------------

    def execute_sync(self, tool_use_block: dict[str, Any]) -> dict[str, Any]:
        """
        Execute a tool_use block synchronously.

        Args:
            tool_use_block: A dict with keys ``id``, ``name``, ``input``.

        Returns:
            A tool_result content block ready to append to the next API call::

                {
                    "type": "tool_result",
                    "tool_use_id": "<id>",
                    "content": [...],
                    "is_error": False,
                }
        """
        tool_use_id = tool_use_block.get("id", "")
        tool_name = tool_use_block.get("name", "")
        tool_input = tool_use_block.get("input", {})

        tool = self.registry.get(tool_name)
        if tool is None:
            error_text = (
                f"Unknown tool: {tool_name!r}. "
                f"Available: {self.registry.names()}"
            )
            logger.warning(error_text)
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": [{"type": "text", "text": error_text}],
                "is_error": True,
            }

        logger.debug("Executing tool %r with input: %s", tool_name, tool_input)
        try:
            result: ToolResult = tool.run(**tool_input)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Tool %r raised an exception", tool_name)
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": [{"type": "text", "text": f"Tool error: {exc}"}],
                "is_error": True,
            }

        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": result.content,
            "is_error": result.is_error,
        }

    # ------------------------------------------------------------------
    # Async interface
    # ------------------------------------------------------------------

    async def execute(self, tool_use_block: dict[str, Any]) -> dict[str, Any]:
        """
        Execute a tool_use block asynchronously.

        Sync tools are offloaded to a thread pool to avoid blocking.
        """
        tool_name = tool_use_block.get("name", "")
        tool = self.registry.get(tool_name)

        if tool is None:
            # Unknown tool — let execute_sync handle the error response
            return self.execute_sync(tool_use_block)

        if asyncio.iscoroutinefunction(getattr(tool, "run", None)):
            # Async tool — call directly
            tool_use_id = tool_use_block.get("id", "")
            tool_input = tool_use_block.get("input", {})
            try:
                result: ToolResult = await tool.run(**tool_input)  # type: ignore[misc]
            except Exception as exc:  # noqa: BLE001
                logger.exception("Async tool %r raised an exception", tool_name)
                return {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": [{"type": "text", "text": f"Tool error: {exc}"}],
                    "is_error": True,
                }
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": result.content,
                "is_error": result.is_error,
            }
        else:
            # Sync tool — run in thread pool
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, self.execute_sync, tool_use_block
            )

    async def execute_all(
        self, tool_use_blocks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Execute multiple tool_use blocks concurrently.

        Returns results in the same order as the input.
        """
        tasks = [self.execute(block) for block in tool_use_blocks]
        return list(await asyncio.gather(*tasks))
