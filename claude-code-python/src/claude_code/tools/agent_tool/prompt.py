"""AgentTool prompt builder. Ported from AgentTool/prompt.ts"""
from __future__ import annotations
import os
from typing import Any, Dict, List, Optional

AGENT_TOOL_NAME = "Agent"

# File-tool names used in prompt copy.
FILE_READ_TOOL_NAME = "Read"
FILE_WRITE_TOOL_NAME = "Write"
GLOB_TOOL_NAME = "Glob"
SEND_MESSAGE_TOOL_NAME = "SendMessage"


def _get_tools_description(agent: Dict[str, Any]) -> str:
    """Render the tools available to an agent as a human-readable string."""
    tools: List[str] = agent.get("tools") or []
    disallowed: List[str] = agent.get("disallowed_tools") or []

    has_allowlist = bool(tools)
    has_denylist = bool(disallowed)

    if has_allowlist and has_denylist:
        deny_set = set(disallowed)
        effective = [t for t in tools if t not in deny_set]
        return ", ".join(effective) if effective else "None"
    if has_allowlist:
        return ", ".join(tools)
    if has_denylist:
        return f"All tools except {', '.join(disallowed)}"
    return "All tools"


def format_agent_line(agent: Dict[str, Any]) -> str:
    """Format one agent line for the agent listing: `- type: whenToUse (Tools: ...)`."""
    tools_desc = _get_tools_description(agent)
    agent_type = agent.get("agent_type") or agent.get("agentType", "unknown")
    when_to_use = agent.get("when_to_use") or agent.get("whenToUse", "")
    return f"- {agent_type}: {when_to_use} (Tools: {tools_desc})"


def should_inject_agent_list_in_messages() -> bool:
    """Whether the agent list should be injected as an attachment message."""
    val = os.environ.get("CLAUDE_CODE_AGENT_LIST_IN_MESSAGES", "")
    if val.lower() in ("1", "true", "yes"):
        return True
    if val.lower() in ("0", "false", "no"):
        return False
    return False  # default off (feature flag would control this in TS)


async def get_prompt(
    agent_definitions: List[Dict[str, Any]],
    is_coordinator: bool = False,
    allowed_agent_types: Optional[List[str]] = None,
) -> str:
    """Build the AgentTool prompt string.

    Mirrors the TypeScript getPrompt() logic, including fork-subagent and
    coordinator-mode variants.
    """
    from claude_code.tools.agent_tool.fork_subagent import is_fork_subagent_enabled  # noqa: PLC0415

    # Filter by allowed types when Agent(x,y) restricts spawnable agents
    effective_agents = (
        [a for a in agent_definitions if (a.get("agent_type") or a.get("agentType")) in allowed_agent_types]
        if allowed_agent_types
        else agent_definitions
    )

    fork_enabled = is_fork_subagent_enabled()
    list_via_attachment = should_inject_agent_list_in_messages()

    # Agent list section
    if list_via_attachment:
        agent_list_section = (
            "Available agent types are listed in <system-reminder> messages in the conversation."
        )
    else:
        lines = "\n".join(format_agent_line(a) for a in effective_agents)
        agent_list_section = (
            f"Available agent types and the tools they have access to:\n{lines}"
        )

    # Whether subagent_type is optional (fork) or required
    if fork_enabled:
        spawn_note = (
            f"When using the {AGENT_TOOL_NAME} tool, specify a subagent_type to use a "
            "specialized agent, or omit it to fork yourself — a fork inherits your full "
            "conversation context."
        )
    else:
        spawn_note = (
            f"When using the {AGENT_TOOL_NAME} tool, specify a subagent_type parameter to "
            "select which agent type to use. If omitted, the general-purpose agent is used."
        )

    shared = (
        f"Launch a new agent to handle complex, multi-step tasks autonomously.\n\n"
        f"The {AGENT_TOOL_NAME} tool launches specialized agents (subprocesses) that autonomously "
        f"handle complex tasks. Each agent type has specific capabilities and tools available to it.\n\n"
        f"{agent_list_section}\n\n"
        f"{spawn_note}"
    )

    if is_coordinator:
        return shared

    # When NOT to use section (omitted when fork is enabled)
    if not fork_enabled:
        when_not = (
            f"\nWhen NOT to use the {AGENT_TOOL_NAME} tool:\n"
            f"- If you want to read a specific file path, use the {FILE_READ_TOOL_NAME} tool instead\n"
            f"- If you are searching for a specific class definition, use the {GLOB_TOOL_NAME} tool instead\n"
            f"- If you are searching for code within a specific file, use the {FILE_READ_TOOL_NAME} tool instead\n"
            "- Other tasks that are not related to the agent descriptions above\n"
        )
    else:
        when_not = ""

    usage_notes = (
        "\nUsage notes:\n"
        "- Always include a short description (3-5 words) summarizing what the agent will do\n"
        "- When the agent is done, it will return a single message back to you. "
        "The result returned by the agent is not visible to the user. "
        "To show the user the result, you should send a text message back to the user "
        "with a concise summary of the result.\n"
        f"- To continue a previously spawned agent, use {SEND_MESSAGE_TOOL_NAME} with the "
        "agent's ID or name as the `to` field.\n"
        "- The agent's outputs should generally be trusted\n"
        "- Clearly tell the agent whether you expect it to write code or just to do research\n"
        "- You can optionally set `isolation: \"worktree\"` to run the agent in a temporary "
        "git worktree, giving it an isolated copy of the repository.\n"
    )

    examples = (
        "\nExample usage:\n\n"
        "<example>\n"
        'user: "Please write a function that checks if a number is prime"\n'
        f"assistant: Uses the {AGENT_TOOL_NAME} tool to launch the test-runner agent\n"
        "</example>\n"
    )

    return f"{shared}{when_not}{usage_notes}{examples}"


# Convenience constants used by other modules
DESCRIPTION = (
    "Launch a new agent to handle complex, multi-step tasks autonomously. "
    "Each agent type has specific capabilities and tools available to it."
)
DEFAULT_AGENT_PROMPT = (
    "You are an AI assistant helping with a sub-task delegated from a parent agent. "
    "Complete the task described and report back."
)
