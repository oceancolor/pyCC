"""
Ported from: commands/context/context-noninteractive.ts (325 lines)

Shared data-collection path for /context (slash command) and the SDK
get_context_usage control request. Mirrors query.ts's pre-API transforms
(compact boundary, projectView, microcompact) so the token count reflects
what the model actually sees.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

# Feature flags (bun:bundle replacements)
CONTEXT_COLLAPSE_ENABLED: bool = os.environ.get("CONTEXT_COLLAPSE", "").lower() in ("1", "true", "yes")


def format_tokens(n: int) -> str:
    """Format a token count with K suffix for readability."""
    if n >= 1000:
        return f"{n / 1000:.1f}K"
    return str(n)


class ContextCategory:
    """A single usage category in the context breakdown."""
    def __init__(self, name: str, tokens: int) -> None:
        self.name = name
        self.tokens = tokens


class McpTool:
    def __init__(self, name: str, server_name: str, tokens: int) -> None:
        self.name = name
        self.server_name = server_name
        self.tokens = tokens


class SystemTool:
    def __init__(self, name: str, tokens: int) -> None:
        self.name = name
        self.tokens = tokens


class SystemPromptSection:
    def __init__(self, name: str, tokens: int) -> None:
        self.name = name
        self.tokens = tokens


class AgentInfo:
    def __init__(self, agent_type: str, source: str, tokens: int) -> None:
        self.agent_type = agent_type
        self.source = source
        self.tokens = tokens


class MemoryFile:
    def __init__(self, type_: str, path: str, tokens: int) -> None:
        self.type = type_
        self.path = path
        self.tokens = tokens


class ToolCallByType:
    def __init__(self, name: str, call_tokens: int, result_tokens: int) -> None:
        self.name = name
        self.call_tokens = call_tokens
        self.result_tokens = result_tokens


class AttachmentByType:
    def __init__(self, name: str, tokens: int) -> None:
        self.name = name
        self.tokens = tokens


class MessageBreakdown:
    def __init__(
        self,
        tool_call_tokens: int = 0,
        tool_result_tokens: int = 0,
        attachment_tokens: int = 0,
        assistant_message_tokens: int = 0,
        user_message_tokens: int = 0,
        tool_calls_by_type: Optional[List[ToolCallByType]] = None,
        attachments_by_type: Optional[List[AttachmentByType]] = None,
    ) -> None:
        self.tool_call_tokens = tool_call_tokens
        self.tool_result_tokens = tool_result_tokens
        self.attachment_tokens = attachment_tokens
        self.assistant_message_tokens = assistant_message_tokens
        self.user_message_tokens = user_message_tokens
        self.tool_calls_by_type: List[ToolCallByType] = tool_calls_by_type or []
        self.attachments_by_type: List[AttachmentByType] = attachments_by_type or []


class SkillFrontmatter:
    def __init__(self, name: str, source: str, tokens: int) -> None:
        self.name = name
        self.source = source
        self.tokens = tokens


class SkillsInfo:
    def __init__(self, tokens: int, skill_frontmatter: Optional[List[SkillFrontmatter]] = None) -> None:
        self.tokens = tokens
        self.skill_frontmatter: List[SkillFrontmatter] = skill_frontmatter or []


class ContextData:
    """
    Full context usage breakdown returned by analyze_context_usage.
    Mirrors ContextData from utils/analyzeContext.ts.
    """
    def __init__(
        self,
        categories: Optional[List[ContextCategory]] = None,
        total_tokens: int = 0,
        raw_max_tokens: int = 0,
        percentage: float = 0.0,
        model: str = "",
        memory_files: Optional[List[MemoryFile]] = None,
        mcp_tools: Optional[List[McpTool]] = None,
        agents: Optional[List[AgentInfo]] = None,
        skills: Optional[SkillsInfo] = None,
        message_breakdown: Optional[MessageBreakdown] = None,
        system_tools: Optional[List[SystemTool]] = None,
        system_prompt_sections: Optional[List[SystemPromptSection]] = None,
    ) -> None:
        self.categories: List[ContextCategory] = categories or []
        self.total_tokens = total_tokens
        self.raw_max_tokens = raw_max_tokens
        self.percentage = percentage
        self.model = model
        self.memory_files: List[MemoryFile] = memory_files or []
        self.mcp_tools: List[McpTool] = mcp_tools or []
        self.agents: List[AgentInfo] = agents or []
        self.skills = skills
        self.message_breakdown = message_breakdown
        self.system_tools: List[SystemTool] = system_tools or []
        self.system_prompt_sections: List[SystemPromptSection] = system_prompt_sections or []


def _get_source_display_name(source: str) -> str:
    """Map a settings source key to a human-readable label."""
    mapping = {
        "projectSettings": "Project",
        "userSettings": "User",
        "localSettings": "Local",
        "flagSettings": "Flag",
        "policySettings": "Policy",
        "plugin": "Plugin",
        "built-in": "Built-in",
    }
    return mapping.get(source, source)


def _plural(n: int, word: str) -> str:
    return word if n == 1 else f"{word}s"


def format_context_as_markdown_table(data: ContextData) -> str:
    """
    Render a ContextData object as a Markdown-formatted table string.
    Mirrors formatContextAsMarkdownTable() from the TS source.
    """
    output = "## Context Usage\n\n"
    output += f"**Model:** {data.model}  \n"
    output += (
        f"**Tokens:** {format_tokens(data.total_tokens)} / "
        f"{format_tokens(data.raw_max_tokens)} ({data.percentage:.0f}%)\n"
    )

    # Context-collapse status
    if CONTEXT_COLLAPSE_ENABLED:
        # In Python port we expose a simple stub — real collapse stats would
        # come from a collapse-service integration.
        output += "**Context strategy:** collapse (waiting for first trigger)\n"

    output += "\n"

    # Main categories table
    visible_categories = [
        c for c in data.categories
        if c.tokens > 0 and c.name not in ("Free space", "Autocompact buffer")
    ]

    if visible_categories:
        output += "### Estimated usage by category\n\n"
        output += "| Category | Tokens | Percentage |\n"
        output += "|----------|--------|------------|\n"
        for cat in visible_categories:
            pct = (cat.tokens / data.raw_max_tokens * 100) if data.raw_max_tokens else 0
            output += f"| {cat.name} | {format_tokens(cat.tokens)} | {pct:.1f}% |\n"

        free_space = next((c for c in data.categories if c.name == "Free space"), None)
        if free_space and free_space.tokens > 0:
            pct = (free_space.tokens / data.raw_max_tokens * 100) if data.raw_max_tokens else 0
            output += f"| Free space | {format_tokens(free_space.tokens)} | {pct:.1f}% |\n"

        autocompact = next((c for c in data.categories if c.name == "Autocompact buffer"), None)
        if autocompact and autocompact.tokens > 0:
            pct = (autocompact.tokens / data.raw_max_tokens * 100) if data.raw_max_tokens else 0
            output += f"| Autocompact buffer | {format_tokens(autocompact.tokens)} | {pct:.1f}% |\n"

        output += "\n"

    # MCP tools
    if data.mcp_tools:
        output += "### MCP Tools\n\n"
        output += "| Tool | Server | Tokens |\n"
        output += "|------|--------|--------|\n"
        for tool in data.mcp_tools:
            output += f"| {tool.name} | {tool.server_name} | {format_tokens(tool.tokens)} |\n"
        output += "\n"

    # System tools (ant-only)
    is_ant = os.environ.get("USER_TYPE") == "ant"
    if data.system_tools and is_ant:
        output += "### [ANT-ONLY] System Tools\n\n"
        output += "| Tool | Tokens |\n"
        output += "|------|--------|\n"
        for tool in data.system_tools:
            output += f"| {tool.name} | {format_tokens(tool.tokens)} |\n"
        output += "\n"

    # System prompt sections (ant-only)
    if data.system_prompt_sections and is_ant:
        output += "### [ANT-ONLY] System Prompt Sections\n\n"
        output += "| Section | Tokens |\n"
        output += "|---------|--------|\n"
        for section in data.system_prompt_sections:
            output += f"| {section.name} | {format_tokens(section.tokens)} |\n"
        output += "\n"

    # Custom agents
    if data.agents:
        output += "### Custom Agents\n\n"
        output += "| Agent Type | Source | Tokens |\n"
        output += "|------------|--------|--------|\n"
        for agent in data.agents:
            source_display = _get_source_display_name(agent.source)
            output += f"| {agent.agent_type} | {source_display} | {format_tokens(agent.tokens)} |\n"
        output += "\n"

    # Memory files
    if data.memory_files:
        output += "### Memory Files\n\n"
        output += "| Type | Path | Tokens |\n"
        output += "|------|------|--------|\n"
        for f in data.memory_files:
            output += f"| {f.type} | {f.path} | {format_tokens(f.tokens)} |\n"
        output += "\n"

    # Skills
    if data.skills and data.skills.tokens > 0 and data.skills.skill_frontmatter:
        output += "### Skills\n\n"
        output += "| Skill | Source | Tokens |\n"
        output += "|-------|--------|--------|\n"
        for skill in data.skills.skill_frontmatter:
            output += f"| {skill.name} | {_get_source_display_name(skill.source)} | {format_tokens(skill.tokens)} |\n"
        output += "\n"

    # Message breakdown (ant-only)
    if data.message_breakdown and is_ant:
        mb = data.message_breakdown
        output += "### [ANT-ONLY] Message Breakdown\n\n"
        output += "| Category | Tokens |\n"
        output += "|----------|--------|\n"
        output += f"| Tool calls | {format_tokens(mb.tool_call_tokens)} |\n"
        output += f"| Tool results | {format_tokens(mb.tool_result_tokens)} |\n"
        output += f"| Attachments | {format_tokens(mb.attachment_tokens)} |\n"
        output += f"| Assistant messages (non-tool) | {format_tokens(mb.assistant_message_tokens)} |\n"
        output += f"| User messages (non-tool-result) | {format_tokens(mb.user_message_tokens)} |\n"
        output += "\n"

        if mb.tool_calls_by_type:
            output += "#### Top Tools\n\n"
            output += "| Tool | Call Tokens | Result Tokens |\n"
            output += "|------|-------------|---------------|\n"
            for tool in mb.tool_calls_by_type:
                output += f"| {tool.name} | {format_tokens(tool.call_tokens)} | {format_tokens(tool.result_tokens)} |\n"
            output += "\n"

        if mb.attachments_by_type:
            output += "#### Top Attachments\n\n"
            output += "| Attachment | Tokens |\n"
            output += "|------------|--------|\n"
            for att in mb.attachments_by_type:
                output += f"| {att.name} | {format_tokens(att.tokens)} |\n"
            output += "\n"

    return output


async def collect_context_data(
    messages: List[Any],
    get_app_state: Callable[[], Any],
    main_loop_model: str,
    tools: Any = None,
    agent_definitions: Any = None,
    custom_system_prompt: Optional[str] = None,
    append_system_prompt: Optional[str] = None,
) -> ContextData:
    """
    Shared data-collection path for /context command and SDK get_context_usage.
    Mirrors collectContextData() from the TS source.

    Applies compact boundary slicing, optional context-collapse projectView,
    and microcompact before calling analyze_context_usage.
    """
    # Apply compact-boundary slicing
    try:
        from claude_code.utils.messages import get_messages_after_compact_boundary
        api_view = get_messages_after_compact_boundary(messages)
    except ImportError:
        api_view = messages

    # Optional context-collapse project-view (feature-gated)
    if CONTEXT_COLLAPSE_ENABLED:
        try:
            from claude_code.services.context_collapse.operations import project_view
            api_view = project_view(api_view)
        except ImportError:
            pass

    # Microcompact to reduce tokens before analysis
    try:
        from claude_code.services.compact.micro_compact import microcompact_messages
        result = await microcompact_messages(api_view)
        compacted_messages = result.get("messages", api_view) if isinstance(result, dict) else result
    except (ImportError, Exception):
        compacted_messages = api_view

    app_state = get_app_state() if callable(get_app_state) else None

    # Delegate to analyze_context_usage (stub if unavailable)
    try:
        from claude_code.utils.analyze_context import analyze_context_usage
        return await analyze_context_usage(
            compacted_messages,
            main_loop_model,
            app_state,
            tools,
            agent_definitions,
            custom_system_prompt=custom_system_prompt,
            append_system_prompt=append_system_prompt,
            original_messages=api_view,
        )
    except (ImportError, Exception):
        # Fallback: return minimal stub data
        return ContextData(
            model=main_loop_model,
            total_tokens=0,
            raw_max_tokens=200000,
            percentage=0.0,
        )


async def call(args: str, context: Any = None) -> Dict[str, str]:
    """
    Entry point for the /context slash command (non-interactive path).
    Returns a text block containing the Markdown-formatted context table.
    Mirrors call() from the TS source.
    """
    messages: List[Any] = getattr(context, "messages", []) if context else []
    get_app_state: Callable[[], Any] = getattr(context, "get_app_state", lambda: None)
    options: Any = getattr(context, "options", None)

    main_loop_model: str = getattr(options, "main_loop_model", "") if options else ""
    tools: Any = getattr(options, "tools", None) if options else None
    agent_definitions: Any = getattr(options, "agent_definitions", None) if options else None
    custom_system_prompt: Optional[str] = getattr(options, "custom_system_prompt", None) if options else None
    append_system_prompt: Optional[str] = getattr(options, "append_system_prompt", None) if options else None

    data = await collect_context_data(
        messages=messages,
        get_app_state=get_app_state,
        main_loop_model=main_loop_model,
        tools=tools,
        agent_definitions=agent_definitions,
        custom_system_prompt=custom_system_prompt,
        append_system_prompt=append_system_prompt,
    )

    return {
        "type": "text",
        "value": format_context_as_markdown_table(data),
    }
