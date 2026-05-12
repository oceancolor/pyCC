"""
API query hook helper - creates reusable API query hooks.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

TResult = TypeVar("TResult")


class ApiQueryHookConfig:
    """Configuration for an API query hook."""

    def __init__(
        self,
        name: str,
        should_run: Callable,
        build_messages: Callable,
        parse_response: Callable,
        log_result: Callable,
        get_model: Callable,
        system_prompt: Optional[str] = None,
        use_tools: bool = True,
    ) -> None:
        self.name = name
        self.should_run = should_run
        self.build_messages = build_messages
        self.parse_response = parse_response
        self.log_result = log_result
        self.get_model = get_model
        self.system_prompt = system_prompt
        self.use_tools = use_tools


def create_api_query_hook(config: ApiQueryHookConfig) -> Callable:
    """Create an API query hook from the given configuration."""

    async def hook(context: Dict[str, Any]) -> None:
        try:
            should_run = await config.should_run(context)
            if not should_run:
                return

            query_uuid = str(uuid.uuid4())
            messages = config.build_messages(context)
            context["queryMessageCount"] = len(messages)

            model = config.get_model(context)

            from ...services.api.claude import query_model_without_streaming
            from ..system_prompt_type import as_system_prompt

            system_prompt = (
                as_system_prompt([config.system_prompt])
                if config.system_prompt
                else context.get("systemPrompt")
            )

            tools = (
                context.get("toolUseContext", {}).get("options", {}).get("tools", [])
                if config.use_tools
                else []
            )

            response = await query_model_without_streaming(
                messages=messages,
                system_prompt=system_prompt,
                tools=tools,
                model=model,
            )

            content = ""
            if hasattr(response, "content"):
                from ..messages import extract_text_content
                content = extract_text_content(response)

            result = config.parse_response(content, context)
            query_result = {
                "type": "success",
                "queryName": config.name,
                "result": result,
                "model": model,
                "uuid": query_uuid,
            }
            config.log_result(query_result, context)

        except Exception as e:
            from ..log import log_error
            log_error(e)

    return hook
