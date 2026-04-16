"""Message builder helpers. Ported from utils/messages/."""
from __future__ import annotations
from typing import Any

def create_user_message(content: Any) -> dict:
    return {"role": "user", "content": content}

def create_assistant_message(content: Any) -> dict:
    return {"role": "assistant", "content": content}
