"""AskUserQuestion tool stub. Ported from AskUserQuestionTool."""
from __future__ import annotations
from typing import Any

ASK_USER_QUESTION_TOOL_NAME = "AskUserQuestion"
DESCRIPTION = "Ask the user a clarifying question and wait for their response"


class AskUserQuestionTool:
    name = ASK_USER_QUESTION_TOOL_NAME
    description = DESCRIPTION

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question to ask the user"},
                },
                "required": ["question"]
            }
        }
