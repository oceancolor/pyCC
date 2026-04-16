"""
handle_prompt_submit.py
处理用户输入提交：解析 /commands、转义、附件处理。
移植自 handlePromptSubmit.ts
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

QueuePriority = str  # 'now' | 'next' | 'later'


@dataclass
class QueuedCommand:
    value: str
    mode: str = "prompt"               # 'prompt' | 'bash' | 'task-notification'
    priority: QueuePriority = "next"
    pasted_contents: Optional[dict[int, Any]] = None
    skip_slash_commands: bool = False
    pre_expansion_value: Optional[str] = None
    uuid: Optional[str] = None
    is_meta: bool = False


@dataclass
class SlashCommandParseResult:
    command_name: str          # e.g. "exit", "model"
    command_args: str          # remainder after the command name
    raw: str                   # original trimmed input


@dataclass
class PromptSubmitResult:
    """Result returned by handle_prompt_submit."""
    queued: bool = False            # True if command was queued (guard active)
    command: Optional[QueuedCommand] = None  # The command to execute
    slash_result: Optional[SlashCommandParseResult] = None
    skipped: bool = False           # True if input was empty / exit shortcut
    exit_requested: bool = False    # True if user typed exit/quit/etc.


# ---------------------------------------------------------------------------
# Slash command parser
# ---------------------------------------------------------------------------

_EXIT_ALIASES = frozenset({"exit", "quit", ":q", ":q!", ":wq", ":wq!"})


def parse_slash_command(input_text: str) -> Optional[SlashCommandParseResult]:
    """
    Parse a /command string.

    Returns SlashCommandParseResult if input starts with '/', else None.

    Examples:
        parse_slash_command("/exit")          -> SlashCommandParseResult("exit", "", "/exit")
        parse_slash_command("/model claude")  -> SlashCommandParseResult("model", "claude", ...)
        parse_slash_command("hello world")    -> None
    """
    trimmed = input_text.strip()
    if not trimmed.startswith("/"):
        return None

    space_idx = trimmed.find(" ", 1)
    if space_idx == -1:
        cmd_name = trimmed[1:]
        cmd_args = ""
    else:
        cmd_name = trimmed[1:space_idx]
        cmd_args = trimmed[space_idx + 1:].strip()

    return SlashCommandParseResult(
        command_name=cmd_name,
        command_args=cmd_args,
        raw=trimmed,
    )


# ---------------------------------------------------------------------------
# Reference / pasted-content helpers
# ---------------------------------------------------------------------------

_REFERENCE_PATTERN = re.compile(r"\[(?:Image|File|Text) #(\d+)\]")


def parse_references(text: str) -> list[dict[str, Any]]:
    """Extract inline placeholder references like [Image #3] from text."""
    results = []
    for m in _REFERENCE_PATTERN.finditer(text):
        results.append({"id": int(m.group(1)), "match": m.group(0), "start": m.start()})
    return results


def expand_pasted_text_refs(
    text: str,
    pasted_contents: dict[int, Any],
) -> str:
    """Replace [Text #N] placeholders with their actual content."""
    def replacer(m: re.Match) -> str:
        ref_id = int(m.group(1))
        entry = pasted_contents.get(ref_id)
        if entry and entry.get("type") == "text":
            return entry.get("content", m.group(0))
        return m.group(0)

    return _REFERENCE_PATTERN.sub(replacer, text)


def filter_pasted_contents(
    input_text: str,
    raw_pasted: dict[int, Any],
) -> dict[int, Any]:
    """Drop image entries whose placeholder was removed from the input."""
    referenced_ids = {r["id"] for r in parse_references(input_text)}
    return {
        k: v for k, v in raw_pasted.items()
        if v.get("type") != "image" or k in referenced_ids
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def handle_prompt_submit(
    input_text: str,
    *,
    mode: str = "prompt",
    pasted_contents: Optional[dict[int, Any]] = None,
    skip_slash_commands: bool = False,
    is_guard_active: bool = False,
    is_external_loading: bool = False,
    uuid: Optional[str] = None,
    on_enqueue: Optional[Callable[[QueuedCommand], None]] = None,
    on_exit: Optional[Callable[[], None]] = None,
) -> PromptSubmitResult:
    """
    Process a user prompt submission.

    Steps:
    1. Filter orphaned image references in pasted_contents.
    2. Skip if empty.
    3. Handle exit aliases (exit/quit/:q etc.).
    4. Expand pasted text references.
    5. If guard is active → enqueue and return queued=True.
    6. Otherwise → return the QueuedCommand for immediate execution.

    Args:
        input_text:           Raw text from the user.
        mode:                 Input mode ('prompt' | 'bash' | 'task-notification').
        pasted_contents:      Dict of id → PastedContent entries.
        skip_slash_commands:  When True, treat /text as plain text (bridge msgs).
        is_guard_active:      True when another query is in progress.
        is_external_loading:  True when external loading is active.
        uuid:                 Optional message UUID for deduplication.
        on_enqueue:           Callback called when a command is queued.
        on_exit:              Callback called when an exit command is detected.

    Returns:
        PromptSubmitResult describing what happened.
    """
    raw_pasted = pasted_contents or {}

    # Step 1: filter orphaned images
    filtered_pasted = filter_pasted_contents(input_text, raw_pasted)
    has_images = any(v.get("type") == "image" for v in filtered_pasted.values())

    # Step 2: skip empty input
    if not input_text.strip():
        return PromptSubmitResult(skipped=True)

    # Step 3: exit aliases (only when slash commands are not skipped)
    if not skip_slash_commands and input_text.strip() in _EXIT_ALIASES:
        if on_exit:
            on_exit()
        return PromptSubmitResult(exit_requested=True, skipped=True)

    # Step 4: expand pasted text references
    final_input = expand_pasted_text_refs(input_text, filtered_pasted)

    # Step 5: parse slash command info (for caller use)
    slash_result: Optional[SlashCommandParseResult] = None
    if not skip_slash_commands and final_input.strip().startswith("/"):
        slash_result = parse_slash_command(final_input)

    # Build the command object
    cmd = QueuedCommand(
        value=final_input.strip(),
        mode=mode,
        priority="next",
        pasted_contents=filtered_pasted if has_images else None,
        skip_slash_commands=skip_slash_commands,
        pre_expansion_value=input_text.strip(),
        uuid=uuid,
    )

    # Step 5: queue if guard is active
    if is_guard_active or is_external_loading:
        if mode not in ("prompt", "bash"):
            return PromptSubmitResult(skipped=True)
        if on_enqueue:
            on_enqueue(cmd)
        return PromptSubmitResult(queued=True, command=cmd, slash_result=slash_result)

    # Step 6: immediate execution path
    return PromptSubmitResult(queued=False, command=cmd, slash_result=slash_result)
