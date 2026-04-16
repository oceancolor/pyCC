"""Compact command descriptor. Ported from commands/compact/index.ts"""
import os

NAME = "compact"
DESCRIPTION = "Clear conversation history but keep a summary in context. Optional: /compact [instructions]"
ARGUMENT_HINT = "<optional custom summarization instructions>"
SUPPORTS_NON_INTERACTIVE = True

def is_enabled() -> bool:
    return os.environ.get("DISABLE_COMPACT", "").lower() not in ("1", "true")
