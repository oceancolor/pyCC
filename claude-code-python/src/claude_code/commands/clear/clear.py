"""Clear command implementation. Ported from commands/clear/clear.ts"""
from __future__ import annotations

from typing import Any, Dict, Optional


async def call(
    args: str = "",
    context: Any = None,
    set_messages: Any = None,
    read_file_state: Any = None,
    get_app_state: Any = None,
    set_app_state: Any = None,
    set_conversation_id: Any = None,
    discovered_skill_names: Any = None,
    loaded_nested_memory_paths: Any = None,
) -> Dict[str, str]:
    """
    Handle the /clear command.

    Clears the conversation, resets session state, executes session hooks,
    and returns an empty text result.

    Parameters
    ----------
    args:
        Command arguments (unused for /clear).
    context:
        Legacy single-object context (used when keyword args not provided).
    set_messages / read_file_state / ...:
        Individual context components forwarded to clear_conversation().

    Returns
    -------
    dict
        ``{"type": "text", "value": ""}``
    """
    from claude_code.commands.clear.conversation import clear_conversation

    # Build the kwargs for clear_conversation.
    # If the caller passes a legacy `context` object, pull attributes from it.
    kwargs: dict[str, Any] = {}

    if set_messages is not None:
        kwargs["set_messages"] = set_messages
    elif context is not None:
        sm = getattr(context, "set_messages", None)
        if sm is not None:
            kwargs["set_messages"] = sm

    if read_file_state is not None:
        kwargs["read_file_state"] = read_file_state
    elif context is not None:
        rfs = getattr(context, "read_file_state", None)
        if rfs is not None:
            kwargs["read_file_state"] = rfs

    if get_app_state is not None:
        kwargs["get_app_state"] = get_app_state
    elif context is not None:
        gas = getattr(context, "get_app_state", None)
        if gas is not None:
            kwargs["get_app_state"] = gas

    if set_app_state is not None:
        kwargs["set_app_state"] = set_app_state
    elif context is not None:
        sas = getattr(context, "set_app_state", None)
        if sas is not None:
            kwargs["set_app_state"] = sas

    if set_conversation_id is not None:
        kwargs["set_conversation_id"] = set_conversation_id
    elif context is not None:
        sci = getattr(context, "set_conversation_id", None)
        if sci is not None:
            kwargs["set_conversation_id"] = sci

    if discovered_skill_names is not None:
        kwargs["discovered_skill_names"] = discovered_skill_names
    elif context is not None:
        dsn = getattr(context, "discovered_skill_names", None)
        if dsn is not None:
            kwargs["discovered_skill_names"] = dsn

    if loaded_nested_memory_paths is not None:
        kwargs["loaded_nested_memory_paths"] = loaded_nested_memory_paths
    elif context is not None:
        lnmp = getattr(context, "loaded_nested_memory_paths", None)
        if lnmp is not None:
            kwargs["loaded_nested_memory_paths"] = lnmp

    await clear_conversation(**kwargs)
    return {"type": "text", "value": ""}
