"""
Analyze context usage.
Ported from utils/analyzeContext.ts (1382 lines).

Provides token counting, context window analysis, and grid visualization
of the Claude context window usage.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RESERVED_CATEGORY_NAME = "Autocompact buffer"
MANUAL_COMPACT_BUFFER_NAME = "Compact buffer"

# Fixed token overhead added by the API when tools are present.
# The API adds a tool prompt preamble (~500 tokens) once per API call when tools
# are present. When we count tools individually via the token counting API, each
# call includes this overhead, leading to N × overhead instead of 1 × overhead
# for N tools. We subtract this overhead from per-tool counts to show accurate
# tool content sizes.
TOOL_TOKEN_COUNT_OVERHEAD = 500


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ContextCategory:
    """A named category contributing to context token usage."""
    name: str
    tokens: int
    color: str  # keyof Theme
    is_deferred: bool = False
    """When True, these tokens are deferred and don't count toward context usage."""


@dataclass
class GridSquare:
    """A single square in the context visualization grid."""
    color: str
    is_filled: bool
    category_name: str
    tokens: int
    percentage: int
    square_fullness: float  # 0-1 representing how full this individual square is


@dataclass
class MemoryFile:
    """A memory file and its token count."""
    path: str
    type: str
    tokens: int


@dataclass
class McpTool:
    """An MCP tool and its token count."""
    name: str
    server_name: str
    tokens: int
    is_loaded: Optional[bool] = None


@dataclass
class DeferredBuiltinTool:
    """A deferred built-in tool detail (ant-only)."""
    name: str
    tokens: int
    is_loaded: bool


@dataclass
class SystemToolDetail:
    """A system tool and its token count (ant-only)."""
    name: str
    tokens: int


@dataclass
class SystemPromptSectionDetail:
    """A system prompt section and its token count (ant-only)."""
    name: str
    tokens: int


@dataclass
class Agent:
    """A custom agent and its token count."""
    agent_type: str
    source: str  # SettingSource | 'built-in' | 'plugin'
    tokens: int


@dataclass
class SlashCommandInfo:
    """Information about slash commands in context."""
    total_commands: int
    included_commands: int
    tokens: int


@dataclass
class SkillFrontmatter:
    """Individual skill detail for context display."""
    name: str
    source: str  # SettingSource | 'plugin'
    tokens: int


@dataclass
class SkillInfo:
    """Information about skills included in the context window."""
    total_skills: int
    included_skills: int
    tokens: int
    skill_frontmatter: List[SkillFrontmatter] = field(default_factory=list)


@dataclass
class MessageBreakdownToolEntry:
    """Per-tool token breakdown."""
    name: str
    call_tokens: int
    result_tokens: int


@dataclass
class MessageBreakdownAttachmentEntry:
    """Per-attachment-type token breakdown."""
    name: str
    tokens: int


@dataclass
class MessageBreakdown:
    """Detailed breakdown of message token usage."""
    tool_call_tokens: int
    tool_result_tokens: int
    attachment_tokens: int
    assistant_message_tokens: int
    user_message_tokens: int
    tool_calls_by_type: List[MessageBreakdownToolEntry]
    attachments_by_type: List[MessageBreakdownAttachmentEntry]


@dataclass
class ApiUsage:
    """Actual token usage from last API response."""
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int


@dataclass
class ContextData:
    """Complete context window usage data."""
    categories: List[ContextCategory]
    total_tokens: int
    max_tokens: int
    raw_max_tokens: int
    percentage: int
    grid_rows: List[List[GridSquare]]
    model: str
    memory_files: List[MemoryFile]
    mcp_tools: List[McpTool]
    agents: List[Agent]
    is_auto_compact_enabled: bool
    api_usage: Optional[ApiUsage] = None
    deferred_builtin_tools: Optional[List[DeferredBuiltinTool]] = None
    """Ant-only: per-tool breakdown of deferred built-in tools."""
    system_tools: Optional[List[SystemToolDetail]] = None
    """Ant-only: per-tool breakdown of always-loaded built-in tools."""
    system_prompt_sections: Optional[List[SystemPromptSectionDetail]] = None
    """Ant-only: per-section breakdown of system prompt."""
    slash_commands: Optional[SlashCommandInfo] = None
    skills: Optional[SkillInfo] = None
    auto_compact_threshold: Optional[int] = None
    message_breakdown: Optional[MessageBreakdown] = None


# ---------------------------------------------------------------------------
# Token counting helpers
# ---------------------------------------------------------------------------

def rough_token_count_estimation(text: str) -> int:
    """
    Rough estimate of token count for a text string.
    Uses ~4 chars per token as a conservative estimate.
    """
    # Approximate: 1 token ≈ 4 characters
    return max(1, len(text) // 4)


async def count_tokens_with_fallback(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
) -> Optional[int]:
    """
    Count tokens using the API with fallback to haiku model.
    Returns None if all counting methods fail.
    
    In Python port: returns rough estimation since we don't have the SDK.
    """
    try:
        from claude_code.services.token_estimation import (
            count_messages_tokens_with_api,
            count_tokens_via_haiku_fallback,
        )
        result = await count_messages_tokens_with_api(messages, tools)
        if result is not None:
            return result
    except (ImportError, Exception):
        pass

    try:
        from claude_code.services.token_estimation import (
            count_tokens_via_haiku_fallback,
        )
        fallback = await count_tokens_via_haiku_fallback(messages, tools)
        return fallback
    except (ImportError, Exception):
        pass

    return None


async def count_tool_definition_tokens(
    tools: Any,
    get_tool_permission_context: Any,
    agent_info: Any,
    model: Optional[str] = None,
) -> int:
    """
    Count tokens used by tool definitions.
    Returns 0 if counting fails.
    """
    try:
        from claude_code.utils.api import tool_to_api_schema
        tool_schemas = []
        for tool in tools:
            try:
                schema = await tool_to_api_schema(tool, {
                    "get_tool_permission_context": get_tool_permission_context,
                    "tools": tools,
                    "agents": (agent_info.active_agents if agent_info else []),
                    "model": model,
                })
                tool_schemas.append(schema)
            except Exception:
                pass
        result = await count_tokens_with_fallback([], tool_schemas)
        return result or 0
    except (ImportError, Exception):
        # Fallback: rough estimation based on schema sizes
        try:
            total = 0
            for tool in tools:
                schema_str = json.dumps(getattr(tool, 'input_schema', {}) or {})
                name_str = getattr(tool, 'name', '') or ''
                total += rough_token_count_estimation(schema_str + name_str)
            return max(0, total - TOOL_TOKEN_COUNT_OVERHEAD) if total > 0 else 0
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# Section token counting
# ---------------------------------------------------------------------------

def _extract_section_name(content: str) -> str:
    """Extract a human-readable name from a system prompt section's content."""
    import re
    # Try to find first markdown heading
    match = re.search(r'^#+\s+(.+)$', content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    # Fall back to a truncated preview of the first non-empty line
    for line in content.split('\n'):
        line = line.strip()
        if line:
            return line[:40] + '…' if len(line) > 40 else line
    return ''


async def _count_system_tokens(
    effective_system_prompt: Sequence[str],
) -> Tuple[int, List[SystemPromptSectionDetail]]:
    """
    Count tokens in the system prompt sections.
    Returns (total_tokens, sections_detail).
    """
    try:
        from claude_code.utils.context import get_system_context
        from claude_code.constants.prompts import SYSTEM_PROMPT_DYNAMIC_BOUNDARY
    except ImportError:
        return 0, []

    try:
        system_context = await get_system_context()
    except Exception:
        system_context = {}

    named_entries: List[Dict[str, str]] = []

    for content in effective_system_prompt:
        try:
            if content and content != SYSTEM_PROMPT_DYNAMIC_BOUNDARY:
                named_entries.append({
                    'name': _extract_section_name(content),
                    'content': content,
                })
        except Exception:
            pass

    for name, content in (system_context or {}).items():
        if content:
            named_entries.append({'name': name, 'content': content})

    if not named_entries:
        return 0, []

    counts = await asyncio.gather(*[
        count_tokens_with_fallback([{'role': 'user', 'content': e['content']}], [])
        for e in named_entries
    ])

    sections = [
        SystemPromptSectionDetail(name=e['name'], tokens=c or 0)
        for e, c in zip(named_entries, counts)
    ]
    total = sum(c or 0 for c in counts)
    return total, sections


async def _count_memory_file_tokens() -> Tuple[int, List[MemoryFile]]:
    """
    Count tokens in CLAUDE.md memory files.
    Returns (total_tokens, memory_file_details).
    """
    # Simple mode disables CLAUDE.md loading
    if os.environ.get('CLAUDE_CODE_SIMPLE'):
        return 0, []

    try:
        from claude_code.utils.claudemd import filter_injected_memory_files, get_memory_files
        memory_files_data = filter_injected_memory_files(await get_memory_files())
    except (ImportError, Exception):
        return 0, []

    if not memory_files_data:
        return 0, []

    async def count_file(f: Any) -> Tuple[Any, int]:
        tokens = await count_tokens_with_fallback(
            [{'role': 'user', 'content': f.content}], []
        )
        return f, tokens or 0

    results = await asyncio.gather(*[count_file(f) for f in memory_files_data])

    details: List[MemoryFile] = []
    total = 0
    for f, tokens in results:
        total += tokens
        details.append(MemoryFile(
            path=f.path,
            type=f.type,
            tokens=tokens,
        ))
    return total, details


# ---------------------------------------------------------------------------
# MCP / built-in tool token counting
# ---------------------------------------------------------------------------

async def count_mcp_tool_tokens(
    tools: Any,
    get_tool_permission_context: Any,
    agent_info: Any,
    model: str,
    messages: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """
    Count tokens used by MCP tools.
    Returns dict with mcpToolTokens, mcpToolDetails, deferredToolTokens, loadedMcpToolNames.
    """
    try:
        mcp_tools = [t for t in tools if getattr(t, 'is_mcp', False)]
    except Exception:
        mcp_tools = []

    if not mcp_tools:
        return {
            'mcp_tool_tokens': 0,
            'mcp_tool_details': [],
            'deferred_tool_tokens': 0,
            'loaded_mcp_tool_names': set(),
        }

    # Bulk token count
    total_tokens_raw = await count_tool_definition_tokens(
        mcp_tools, get_tool_permission_context, agent_info, model
    )
    total_tokens = max(0, total_tokens_raw - TOOL_TOKEN_COUNT_OVERHEAD)

    # Estimate per-tool proportions
    estimates: List[int] = []
    for t in mcp_tools:
        try:
            schema_str = json.dumps({
                'name': t.name,
                'input_schema': getattr(t, 'input_json_schema', {}) or {},
            })
            estimates.append(rough_token_count_estimation(schema_str))
        except Exception:
            estimates.append(1)

    estimate_total = sum(estimates) or 1
    tokens_by_tool = [
        round((e / estimate_total) * total_tokens) for e in estimates
    ]

    # Check tool search / deferred tools
    is_deferred = False
    try:
        from claude_code.utils.tool_search import is_tool_search_enabled
        from claude_code.tools.tool_search_tool.prompt import is_deferred_tool
        is_deferred = await is_tool_search_enabled(
            model, tools, get_tool_permission_context,
            agent_info.active_agents if agent_info else [],
            'analyzeMcp',
        )
    except (ImportError, Exception):
        pass

    # Find loaded MCP tools from messages
    loaded_mcp_tool_names: set = set()
    if is_deferred and messages:
        mcp_tool_name_set = {getattr(t, 'name', '') for t in mcp_tools}
        for msg in messages:
            if getattr(msg, 'type', None) == 'assistant':
                for block in msg.message.content:
                    if (
                        getattr(block, 'type', None) == 'tool_use'
                        and getattr(block, 'name', None) in mcp_tool_name_set
                    ):
                        loaded_mcp_tool_names.add(block.name)

    # Build tool details
    mcp_tool_details: List[McpTool] = []
    for i, tool in enumerate(mcp_tools):
        name = getattr(tool, 'name', '')
        server_name = name.split('__')[1] if '__' in name else 'unknown'

        try:
            deferred = is_deferred_tool(tool)  # type: ignore[name-defined]  # noqa: F821
        except Exception:
            deferred = False

        is_loaded = name in loaded_mcp_tool_names or not deferred
        mcp_tool_details.append(McpTool(
            name=name,
            server_name=server_name,
            tokens=tokens_by_tool[i],
            is_loaded=is_loaded,
        ))

    # Calculate loaded vs deferred totals
    loaded_tokens = 0
    deferred_tokens = 0
    for detail in mcp_tool_details:
        if detail.is_loaded:
            loaded_tokens += detail.tokens
        elif is_deferred:
            deferred_tokens += detail.tokens

    return {
        'mcp_tool_tokens': loaded_tokens if is_deferred else total_tokens,
        'mcp_tool_details': mcp_tool_details,
        'deferred_tool_tokens': deferred_tokens,
        'loaded_mcp_tool_names': loaded_mcp_tool_names,
    }


# ---------------------------------------------------------------------------
# Message token breakdown
# ---------------------------------------------------------------------------

def _process_assistant_message_breakdown(
    msg: Any,
    breakdown: Dict[str, Any],
) -> None:
    """Process an assistant message and accumulate token breakdown."""
    for block in msg.message.content:
        block_str = json.dumps(block if isinstance(block, dict) else vars(block), default=str)
        block_tokens = rough_token_count_estimation(block_str)

        block_type = getattr(block, 'type', block.get('type') if isinstance(block, dict) else None)
        if block_type == 'tool_use':
            breakdown['tool_call_tokens'] += block_tokens
            tool_name = (
                block.get('name') if isinstance(block, dict)
                else getattr(block, 'name', 'unknown')
            ) or 'unknown'
            breakdown['tool_calls_by_type'][tool_name] = (
                breakdown['tool_calls_by_type'].get(tool_name, 0) + block_tokens
            )
        else:
            breakdown['assistant_message_tokens'] += block_tokens


def _process_user_message_breakdown(
    msg: Any,
    breakdown: Dict[str, Any],
    tool_use_id_to_name: Dict[str, str],
) -> None:
    """Process a user message and accumulate token breakdown."""
    content = msg.message.content
    if isinstance(content, str):
        breakdown['user_message_tokens'] += rough_token_count_estimation(content)
        return

    for block in content:
        block_str = json.dumps(block if isinstance(block, dict) else vars(block), default=str)
        block_tokens = rough_token_count_estimation(block_str)

        block_type = (
            block.get('type') if isinstance(block, dict)
            else getattr(block, 'type', None)
        )
        if block_type == 'tool_result':
            breakdown['tool_result_tokens'] += block_tokens
            tool_use_id = (
                block.get('tool_use_id') if isinstance(block, dict)
                else getattr(block, 'tool_use_id', None)
            )
            tool_name = (tool_use_id_to_name.get(tool_use_id) if tool_use_id else None) or 'unknown'
            breakdown['tool_results_by_type'][tool_name] = (
                breakdown['tool_results_by_type'].get(tool_name, 0) + block_tokens
            )
        else:
            breakdown['user_message_tokens'] += block_tokens


def _process_attachment_breakdown(
    msg: Any,
    breakdown: Dict[str, Any],
) -> None:
    """Process an attachment message and accumulate token breakdown."""
    content_str = json.dumps(
        msg.attachment if isinstance(msg.attachment, dict) else vars(msg.attachment),
        default=str,
    )
    tokens = rough_token_count_estimation(content_str)
    breakdown['attachment_tokens'] += tokens
    attach_type = (
        msg.attachment.get('type') if isinstance(msg.attachment, dict)
        else getattr(msg.attachment, 'type', 'unknown')
    ) or 'unknown'
    breakdown['attachments_by_type'][attach_type] = (
        breakdown['attachments_by_type'].get(attach_type, 0) + tokens
    )


async def _approximate_message_tokens(messages: List[Any]) -> Dict[str, Any]:
    """
    Approximate message token breakdown.
    Returns a dict with total_tokens, per-category counts, etc.
    """
    # Try microcompact first
    try:
        from claude_code.services.compact.micro_compact import microcompact_messages
        microcompact_result = await microcompact_messages(messages)
        compact_messages = microcompact_result.messages
    except (ImportError, Exception):
        compact_messages = messages

    breakdown: Dict[str, Any] = {
        'total_tokens': 0,
        'tool_call_tokens': 0,
        'tool_result_tokens': 0,
        'attachment_tokens': 0,
        'assistant_message_tokens': 0,
        'user_message_tokens': 0,
        'tool_calls_by_type': {},
        'tool_results_by_type': {},
        'attachments_by_type': {},
    }

    # Build tool_use_id → name map
    tool_use_id_to_name: Dict[str, str] = {}
    for msg in compact_messages:
        if getattr(msg, 'type', None) == 'assistant':
            for block in msg.message.content:
                if getattr(block, 'type', None) == 'tool_use':
                    tool_use_id = getattr(block, 'id', None)
                    tool_name = getattr(block, 'name', 'unknown') or 'unknown'
                    if tool_use_id:
                        tool_use_id_to_name[tool_use_id] = tool_name

    for msg in compact_messages:
        msg_type = getattr(msg, 'type', None)
        if msg_type == 'assistant':
            _process_assistant_message_breakdown(msg, breakdown)
        elif msg_type == 'user':
            _process_user_message_breakdown(msg, breakdown, tool_use_id_to_name)
        elif msg_type == 'attachment':
            _process_attachment_breakdown(msg, breakdown)

    # Try to get accurate total via API
    try:
        from claude_code.utils.messages import normalize_messages_for_api
        normalized = normalize_messages_for_api(compact_messages)
        api_messages = []
        for n in normalized:
            if getattr(n, 'type', None) == 'assistant':
                api_messages.append({
                    'role': 'assistant',
                    'content': n.message.content,
                })
            else:
                api_messages.append(n.message)
        total = await count_tokens_with_fallback(api_messages, [])
        breakdown['total_tokens'] = total or 0
    except (ImportError, Exception):
        # Sum up rough estimates
        breakdown['total_tokens'] = (
            breakdown['tool_call_tokens']
            + breakdown['tool_result_tokens']
            + breakdown['attachment_tokens']
            + breakdown['assistant_message_tokens']
            + breakdown['user_message_tokens']
        )

    return breakdown


# ---------------------------------------------------------------------------
# Grid generation
# ---------------------------------------------------------------------------

def _build_context_grid(
    categories: List[ContextCategory],
    context_window: int,
    terminal_width: Optional[int],
) -> List[List[GridSquare]]:
    """
    Build the context usage grid.
    Returns rows × cols of GridSquare objects.
    """
    is_narrow = terminal_width is not None and terminal_width < 80
    if context_window >= 1_000_000:
        grid_width = 5 if is_narrow else 20
        grid_height = 10
    else:
        grid_width = 5 if is_narrow else 10
        grid_height = 5 if is_narrow else 10
    total_squares = grid_width * grid_height

    # Filter out deferred categories
    non_deferred = [c for c in categories if not c.is_deferred]

    # Compute squares per category
    cat_with_squares = []
    for cat in non_deferred:
        if cat.name == 'Free space':
            sq = round((cat.tokens / context_window) * total_squares)
        else:
            sq = max(1, round((cat.tokens / context_window) * total_squares))
        cat_with_squares.append({
            **cat.__dict__,
            'squares': sq,
            'percentage_of_total': round((cat.tokens / context_window) * 100),
        })

    def create_squares(cat_dict: Dict[str, Any]) -> List[GridSquare]:
        squares: List[GridSquare] = []
        exact = (cat_dict['tokens'] / context_window) * total_squares
        whole = math.floor(exact)
        frac = exact - whole
        for i in range(cat_dict['squares']):
            fullness = 1.0
            if i == whole and frac > 0:
                fullness = frac
            squares.append(GridSquare(
                color=cat_dict['color'],
                is_filled=True,
                category_name=cat_dict['name'],
                tokens=cat_dict['tokens'],
                percentage=cat_dict['percentage_of_total'],
                square_fullness=fullness,
            ))
        return squares

    # Separate reserved / free / others
    reserved = next(
        (c for c in cat_with_squares
         if c['name'] in (RESERVED_CATEGORY_NAME, MANUAL_COMPACT_BUFFER_NAME)),
        None,
    )
    non_reserved = [
        c for c in cat_with_squares
        if c['name'] not in (
            RESERVED_CATEGORY_NAME, MANUAL_COMPACT_BUFFER_NAME, 'Free space',
        )
    ]
    free_cat = next(
        (c for c in cat_with_squares if c['name'] == 'Free space'),
        None,
    )

    grid_squares: List[GridSquare] = []

    for cat in non_reserved:
        for sq in create_squares(cat):
            if len(grid_squares) < total_squares:
                grid_squares.append(sq)

    reserved_count = reserved['squares'] if reserved else 0
    free_target = total_squares - reserved_count
    free_tokens = free_cat['tokens'] if free_cat else 0
    free_pct = round((free_tokens / context_window) * 100) if context_window else 0

    while len(grid_squares) < free_target:
        grid_squares.append(GridSquare(
            color='promptBorder',
            is_filled=True,
            category_name='Free space',
            tokens=free_tokens,
            percentage=free_pct,
            square_fullness=1.0,
        ))

    if reserved:
        for sq in create_squares(reserved):
            if len(grid_squares) < total_squares:
                grid_squares.append(sq)

    # Convert to rows
    rows: List[List[GridSquare]] = []
    for i in range(grid_height):
        rows.append(grid_squares[i * grid_width:(i + 1) * grid_width])

    return rows


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def analyze_context_usage(
    messages: List[Any],
    model: str,
    get_tool_permission_context: Any,
    tools: Any,
    agent_definitions: Any,
    terminal_width: Optional[int] = None,
    tool_use_context: Optional[Any] = None,
    main_thread_agent_definition: Optional[Any] = None,
    original_messages: Optional[List[Any]] = None,
) -> ContextData:
    """
    Analyze the context window usage and return detailed breakdown.
    
    Ported from analyzeContextUsage() in analyzeContext.ts.
    """
    # Get runtime model
    try:
        from claude_code.utils.model.model import get_runtime_main_loop_model
        ctx = await get_tool_permission_context()
        runtime_model = get_runtime_main_loop_model(
            permission_mode=ctx.mode,
            main_loop_model=model,
        )
    except (ImportError, Exception):
        runtime_model = model

    # Get context window
    try:
        from claude_code.utils.context import get_context_window_for_model
        from claude_code.bootstrap.state import get_sdk_betas
        context_window = get_context_window_for_model(runtime_model, get_sdk_betas())
    except (ImportError, Exception):
        context_window = 200_000  # Default

    # Build effective system prompt
    try:
        from claude_code.constants.prompts import get_system_prompt
        from claude_code.utils.system_prompt import build_effective_system_prompt
        default_system = await get_system_prompt(tools, runtime_model)
        effective_system = build_effective_system_prompt(
            main_thread_agent_definition=main_thread_agent_definition,
            tool_use_context=tool_use_context or {},
            custom_system_prompt=(
                tool_use_context.options.get('custom_system_prompt')
                if tool_use_context else None
            ),
            default_system_prompt=default_system,
            append_system_prompt=(
                tool_use_context.options.get('append_system_prompt')
                if tool_use_context else None
            ),
        )
    except (ImportError, Exception):
        effective_system = []

    # Parallel token counting
    tasks = [
        _count_system_tokens(effective_system),
        _count_memory_file_tokens(),
        _count_builtin_tool_tokens(tools, get_tool_permission_context, agent_definitions, runtime_model, messages),
        count_mcp_tool_tokens(tools, get_tool_permission_context, agent_definitions, runtime_model, messages),
        _count_custom_agent_tokens(agent_definitions),
        _count_slash_command_tokens(tools, get_tool_permission_context, agent_definitions),
        _approximate_message_tokens(messages),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Unpack results safely
    def safe_get(result: Any, default: Any) -> Any:
        if isinstance(result, Exception):
            return default
        return result

    system_result = safe_get(results[0], (0, []))
    memory_result = safe_get(results[1], (0, []))
    builtin_result = safe_get(results[2], {
        'built_in_tool_tokens': 0,
        'deferred_builtin_details': [],
        'deferred_builtin_tokens': 0,
        'system_tool_details': [],
    })
    mcp_result = safe_get(results[3], {
        'mcp_tool_tokens': 0,
        'mcp_tool_details': [],
        'deferred_tool_tokens': 0,
        'loaded_mcp_tool_names': set(),
    })
    agent_result = safe_get(results[4], {'agent_tokens': 0, 'agent_details': []})
    slash_result = safe_get(results[5], {
        'slash_command_tokens': 0,
        'command_info': {'total_commands': 0, 'included_commands': 0},
    })
    msg_breakdown = safe_get(results[6], {
        'total_tokens': 0,
        'tool_call_tokens': 0,
        'tool_result_tokens': 0,
        'attachment_tokens': 0,
        'assistant_message_tokens': 0,
        'user_message_tokens': 0,
        'tool_calls_by_type': {},
        'tool_results_by_type': {},
        'attachments_by_type': {},
    })

    system_prompt_tokens, system_prompt_sections = system_result
    claude_md_tokens, memory_file_details = memory_result
    built_in_tool_tokens = builtin_result.get('built_in_tool_tokens', 0)
    deferred_builtin_details = builtin_result.get('deferred_builtin_details', [])
    deferred_builtin_tokens = builtin_result.get('deferred_builtin_tokens', 0)
    system_tool_details = builtin_result.get('system_tool_details', [])
    mcp_tool_tokens = mcp_result.get('mcp_tool_tokens', 0)
    mcp_tool_details = mcp_result.get('mcp_tool_details', [])
    deferred_tool_tokens = mcp_result.get('deferred_tool_tokens', 0)
    agent_tokens = agent_result.get('agent_tokens', 0)
    agent_details = agent_result.get('agent_details', [])
    slash_command_tokens = slash_result.get('slash_command_tokens', 0)
    command_info = slash_result.get('command_info', {})
    message_tokens = msg_breakdown.get('total_tokens', 0)

    # Skills
    skill_frontmatter_tokens = 0
    skill_info = None
    try:
        skill_result = await _count_skill_tokens(tools, get_tool_permission_context, agent_definitions)
        skill_info = skill_result.get('skill_info')
        if skill_info:
            skill_frontmatter_tokens = sum(
                s.tokens for s in (skill_info.get('skill_frontmatter', []) or [])
            )
    except Exception:
        pass

    # Build categories
    cats: List[ContextCategory] = []

    if system_prompt_tokens > 0:
        cats.append(ContextCategory(
            name='System prompt',
            tokens=system_prompt_tokens,
            color='promptBorder',
        ))

    system_tools_tokens = built_in_tool_tokens - skill_frontmatter_tokens
    if system_tools_tokens > 0:
        name = '[ANT-ONLY] System tools' if os.environ.get('USER_TYPE') == 'ant' else 'System tools'
        cats.append(ContextCategory(name=name, tokens=system_tools_tokens, color='inactive'))

    if mcp_tool_tokens > 0:
        cats.append(ContextCategory(name='MCP tools', tokens=mcp_tool_tokens, color='cyan_FOR_SUBAGENTS_ONLY'))

    if deferred_tool_tokens > 0:
        cats.append(ContextCategory(
            name='MCP tools (deferred)', tokens=deferred_tool_tokens,
            color='inactive', is_deferred=True,
        ))

    if deferred_builtin_tokens > 0:
        cats.append(ContextCategory(
            name='System tools (deferred)', tokens=deferred_builtin_tokens,
            color='inactive', is_deferred=True,
        ))

    if agent_tokens > 0:
        cats.append(ContextCategory(name='Custom agents', tokens=agent_tokens, color='permission'))

    if claude_md_tokens > 0:
        cats.append(ContextCategory(name='Memory files', tokens=claude_md_tokens, color='claude'))

    if skill_frontmatter_tokens > 0:
        cats.append(ContextCategory(name='Skills', tokens=skill_frontmatter_tokens, color='warning'))

    if message_tokens > 0:
        cats.append(ContextCategory(
            name='Messages', tokens=message_tokens, color='purple_FOR_SUBAGENTS_ONLY'
        ))

    # Actual usage (non-deferred)
    actual_usage = sum(c.tokens for c in cats if not c.is_deferred)

    # Reserved buffer
    reserved_tokens = 0
    skip_reserved = False
    try:
        from claude_code.services.compact.auto_compact import (
            is_auto_compact_enabled,
            get_effective_context_window_size,
            AUTOCOMPACT_BUFFER_TOKENS,
            MANUAL_COMPACT_BUFFER_TOKENS,
        )
        is_auto_compact = is_auto_compact_enabled()
        auto_compact_threshold = (
            get_effective_context_window_size(model) - AUTOCOMPACT_BUFFER_TOKENS
            if is_auto_compact else None
        )
    except (ImportError, Exception):
        is_auto_compact = False
        auto_compact_threshold = None

    # Feature flags
    try:
        from claude_code.services.context_collapse import is_context_collapse_enabled
        if is_context_collapse_enabled():
            skip_reserved = True
    except (ImportError, Exception):
        pass

    if not skip_reserved:
        try:
            if is_auto_compact and auto_compact_threshold is not None:
                from claude_code.services.compact.auto_compact import AUTOCOMPACT_BUFFER_TOKENS  # noqa
                reserved_tokens = context_window - auto_compact_threshold
                cats.append(ContextCategory(
                    name=RESERVED_CATEGORY_NAME,
                    tokens=reserved_tokens,
                    color='inactive',
                ))
            elif not is_auto_compact:
                from claude_code.services.compact.auto_compact import MANUAL_COMPACT_BUFFER_TOKENS  # noqa
                reserved_tokens = MANUAL_COMPACT_BUFFER_TOKENS
                cats.append(ContextCategory(
                    name=MANUAL_COMPACT_BUFFER_NAME,
                    tokens=reserved_tokens,
                    color='inactive',
                ))
        except (ImportError, Exception):
            pass

    free_tokens = max(0, context_window - actual_usage - reserved_tokens)
    cats.append(ContextCategory(name='Free space', tokens=free_tokens, color='promptBorder'))

    total_for_display = actual_usage

    # API usage from messages
    api_usage = None
    try:
        from claude_code.utils.tokens import get_current_usage
        raw_usage = get_current_usage(original_messages or messages)
        if raw_usage:
            api_usage = ApiUsage(
                input_tokens=raw_usage.get('input_tokens', 0),
                output_tokens=raw_usage.get('output_tokens', 0),
                cache_creation_input_tokens=raw_usage.get('cache_creation_input_tokens', 0),
                cache_read_input_tokens=raw_usage.get('cache_read_input_tokens', 0),
            )
    except (ImportError, Exception):
        pass

    total_from_api = None
    if api_usage:
        total_from_api = (
            api_usage.input_tokens
            + api_usage.cache_creation_input_tokens
            + api_usage.cache_read_input_tokens
        )

    final_total = total_from_api if total_from_api is not None else total_for_display

    # Build grid
    grid_rows = _build_context_grid(cats, context_window, terminal_width)

    # Format message breakdown
    tools_map: Dict[str, Dict[str, int]] = {}
    for name, tokens in msg_breakdown.get('tool_calls_by_type', {}).items():
        existing = tools_map.get(name, {'call_tokens': 0, 'result_tokens': 0})
        tools_map[name] = {**existing, 'call_tokens': tokens}
    for name, tokens in msg_breakdown.get('tool_results_by_type', {}).items():
        existing = tools_map.get(name, {'call_tokens': 0, 'result_tokens': 0})
        tools_map[name] = {**existing, 'result_tokens': tokens}

    tools_by_type = sorted(
        [
            MessageBreakdownToolEntry(
                name=n, call_tokens=v['call_tokens'], result_tokens=v['result_tokens']
            )
            for n, v in tools_map.items()
        ],
        key=lambda x: -(x.call_tokens + x.result_tokens),
    )

    attachments_by_type = sorted(
        [
            MessageBreakdownAttachmentEntry(name=n, tokens=t)
            for n, t in msg_breakdown.get('attachments_by_type', {}).items()
        ],
        key=lambda x: -x.tokens,
    )

    formatted_breakdown = MessageBreakdown(
        tool_call_tokens=msg_breakdown.get('tool_call_tokens', 0),
        tool_result_tokens=msg_breakdown.get('tool_result_tokens', 0),
        attachment_tokens=msg_breakdown.get('attachment_tokens', 0),
        assistant_message_tokens=msg_breakdown.get('assistant_message_tokens', 0),
        user_message_tokens=msg_breakdown.get('user_message_tokens', 0),
        tool_calls_by_type=tools_by_type,
        attachments_by_type=attachments_by_type,
    )

    # Build slash commands info
    slash_commands_info: Optional[SlashCommandInfo] = None
    if slash_command_tokens > 0:
        slash_commands_info = SlashCommandInfo(
            total_commands=command_info.get('total_commands', 0),
            included_commands=command_info.get('included_commands', 0),
            tokens=slash_command_tokens,
        )

    # Build skills info
    skills_data: Optional[SkillInfo] = None
    if skill_frontmatter_tokens > 0 and skill_info:
        skills_data = SkillInfo(
            total_skills=skill_info.get('total_skills', 0),
            included_skills=skill_info.get('included_skills', 0),
            tokens=skill_frontmatter_tokens,
            skill_frontmatter=[
                SkillFrontmatter(name=s.get('name', ''), source=s.get('source', ''), tokens=s.get('tokens', 0))
                if isinstance(s, dict) else s
                for s in skill_info.get('skill_frontmatter', [])
            ],
        )

    return ContextData(
        categories=cats,
        total_tokens=final_total,
        max_tokens=context_window,
        raw_max_tokens=context_window,
        percentage=round((final_total / context_window) * 100) if context_window else 0,
        grid_rows=grid_rows,
        model=runtime_model,
        memory_files=memory_file_details,
        mcp_tools=mcp_tool_details,
        agents=agent_details,
        is_auto_compact_enabled=is_auto_compact,
        api_usage=api_usage,
        deferred_builtin_tools=(
            deferred_builtin_details
            if os.environ.get('USER_TYPE') == 'ant' else None
        ),
        system_tools=(
            system_tool_details
            if os.environ.get('USER_TYPE') == 'ant' else None
        ),
        system_prompt_sections=(
            system_prompt_sections
            if os.environ.get('USER_TYPE') == 'ant' else None
        ),
        slash_commands=slash_commands_info,
        skills=skills_data,
        auto_compact_threshold=auto_compact_threshold,
        message_breakdown=formatted_breakdown,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _find_skill_tool(tools: Any) -> Optional[Any]:
    """Find the SkillTool in the tools list."""
    try:
        from claude_code.tools.skill_tool.constants import SKILL_TOOL_NAME
        from claude_code.utils.tool import find_tool_by_name
        return find_tool_by_name(tools, SKILL_TOOL_NAME)
    except (ImportError, Exception):
        return None


async def _count_slash_command_tokens(
    tools: Any,
    get_tool_permission_context: Any,
    agent_info: Any,
) -> Dict[str, Any]:
    """Count tokens used by slash commands."""
    try:
        from claude_code.tools.skill_tool.prompt import get_slash_command_info
        from claude_code.utils.cwd import get_cwd
        info = await get_slash_command_info(get_cwd())
    except (ImportError, Exception):
        return {
            'slash_command_tokens': 0,
            'command_info': {'total_commands': 0, 'included_commands': 0},
        }

    skill_tool = _find_skill_tool(tools)
    if not skill_tool:
        return {
            'slash_command_tokens': 0,
            'command_info': {'total_commands': 0, 'included_commands': 0},
        }

    tokens = await count_tool_definition_tokens(
        [skill_tool], get_tool_permission_context, agent_info
    )
    return {
        'slash_command_tokens': tokens,
        'command_info': {
            'total_commands': getattr(info, 'total_commands', 0),
            'included_commands': getattr(info, 'included_commands', 0),
        },
    }


async def _count_skill_tokens(
    tools: Any,
    get_tool_permission_context: Any,
    agent_info: Any,
) -> Dict[str, Any]:
    """Count tokens used by skills."""
    try:
        from claude_code.tools.skill_tool.prompt import get_limited_skill_tool_commands
        from claude_code.utils.cwd import get_cwd
        from claude_code.utils.commands import get_command_name
        from claude_code.skills.load_skills_dir import estimate_skill_frontmatter_tokens
        skills = await get_limited_skill_tool_commands(get_cwd())
    except (ImportError, Exception):
        return {
            'skill_tokens': 0,
            'skill_info': {'total_skills': 0, 'included_skills': 0, 'skill_frontmatter': []},
        }

    skill_tool = _find_skill_tool(tools)
    if not skill_tool:
        return {
            'skill_tokens': 0,
            'skill_info': {'total_skills': 0, 'included_skills': 0, 'skill_frontmatter': []},
        }

    try:
        skill_tokens = await count_tool_definition_tokens(
            [skill_tool], get_tool_permission_context, agent_info
        )
        skill_frontmatter = []
        for skill in skills:
            try:
                name = get_command_name(skill)  # type: ignore
                source = getattr(skill, 'source', 'plugin')
                tokens = estimate_skill_frontmatter_tokens(skill)  # type: ignore
                skill_frontmatter.append(
                    SkillFrontmatter(name=name, source=source, tokens=tokens)
                )
            except Exception:
                pass

        return {
            'skill_tokens': skill_tokens,
            'skill_info': {
                'total_skills': len(skills),
                'included_skills': len(skills),
                'skill_frontmatter': skill_frontmatter,
            },
        }
    except Exception:
        return {
            'skill_tokens': 0,
            'skill_info': {'total_skills': 0, 'included_skills': 0, 'skill_frontmatter': []},
        }


async def _count_builtin_tool_tokens(
    tools: Any,
    get_tool_permission_context: Any,
    agent_info: Any,
    model: Optional[str] = None,
    messages: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """
    Count tokens used by built-in tools.
    Returns dict with builtInToolTokens, deferredBuiltinDetails, etc.
    """
    try:
        builtin_tools = [t for t in tools if not getattr(t, 'is_mcp', False)]
    except Exception:
        return {
            'built_in_tool_tokens': 0,
            'deferred_builtin_details': [],
            'deferred_builtin_tokens': 0,
            'system_tool_details': [],
        }

    if not builtin_tools:
        return {
            'built_in_tool_tokens': 0,
            'deferred_builtin_details': [],
            'deferred_builtin_tokens': 0,
            'system_tool_details': [],
        }

    is_deferred = False
    is_deferred_tool_fn = None
    try:
        from claude_code.utils.tool_search import is_tool_search_enabled
        from claude_code.tools.tool_search_tool.prompt import is_deferred_tool as _is_deferred
        is_deferred_tool_fn = _is_deferred
        is_deferred = await is_tool_search_enabled(
            model or '',
            tools,
            get_tool_permission_context,
            agent_info.active_agents if agent_info else [],
            'analyzeBuiltIn',
        )
    except (ImportError, Exception):
        pass

    if is_deferred_tool_fn:
        always_loaded = [t for t in builtin_tools if not is_deferred_tool_fn(t)]
        deferred_tools = [t for t in builtin_tools if is_deferred_tool_fn(t)]
    else:
        always_loaded = builtin_tools
        deferred_tools = []

    always_loaded_tokens = await count_tool_definition_tokens(
        always_loaded, get_tool_permission_context, agent_info, model
    ) if always_loaded else 0

    # ANT-only: per-tool breakdown
    system_tool_details: List[SystemToolDetail] = []
    if os.environ.get('USER_TYPE') == 'ant':
        try:
            from claude_code.tools.skill_tool.constants import SKILL_TOOL_NAME
            from claude_code.utils.tool import tool_matches_name
            tools_for_breakdown = [
                t for t in always_loaded
                if not tool_matches_name(t, SKILL_TOOL_NAME)
            ]
            if tools_for_breakdown:
                estimates = [
                    rough_token_count_estimation(json.dumps(
                        getattr(t, 'input_schema', {}) or {}
                    ))
                    for t in tools_for_breakdown
                ]
                est_total = sum(estimates) or 1
                distributable = max(0, always_loaded_tokens - TOOL_TOKEN_COUNT_OVERHEAD)
                system_tool_details = sorted(
                    [
                        SystemToolDetail(
                            name=getattr(t, 'name', ''),
                            tokens=round((estimates[i] / est_total) * distributable),
                        )
                        for i, t in enumerate(tools_for_breakdown)
                    ],
                    key=lambda x: -x.tokens,
                )
        except (ImportError, Exception):
            pass

    # Deferred tools
    deferred_builtin_details: List[DeferredBuiltinTool] = []
    loaded_deferred_tokens = 0
    total_deferred_tokens = 0

    if deferred_tools and is_deferred:
        # Find which deferred tools have been used in messages
        loaded_tool_names: set = set()
        if messages:
            deferred_name_set = {getattr(t, 'name', '') for t in deferred_tools}
            for msg in messages:
                if getattr(msg, 'type', None) == 'assistant':
                    for block in msg.message.content:
                        if (
                            getattr(block, 'type', None) == 'tool_use'
                            and getattr(block, 'name', None) in deferred_name_set
                        ):
                            loaded_tool_names.add(block.name)

        tokens_by_tool = await asyncio.gather(*[
            count_tool_definition_tokens([t], get_tool_permission_context, agent_info, model)
            for t in deferred_tools
        ])

        for i, tool in enumerate(deferred_tools):
            tokens = max(0, (tokens_by_tool[i] or 0) - TOOL_TOKEN_COUNT_OVERHEAD)
            is_loaded = getattr(tool, 'name', '') in loaded_tool_names
            deferred_builtin_details.append(DeferredBuiltinTool(
                name=getattr(tool, 'name', ''),
                tokens=tokens,
                is_loaded=is_loaded,
            ))
            total_deferred_tokens += tokens
            if is_loaded:
                loaded_deferred_tokens += tokens

    elif deferred_tools:
        # Tool search not enabled — count deferred as regular
        deferred_extra = await count_tool_definition_tokens(
            deferred_tools, get_tool_permission_context, agent_info, model
        )
        return {
            'built_in_tool_tokens': always_loaded_tokens + deferred_extra,
            'deferred_builtin_details': [],
            'deferred_builtin_tokens': 0,
            'system_tool_details': system_tool_details,
        }

    return {
        'built_in_tool_tokens': always_loaded_tokens + loaded_deferred_tokens,
        'deferred_builtin_details': deferred_builtin_details,
        'deferred_builtin_tokens': total_deferred_tokens - loaded_deferred_tokens,
        'system_tool_details': system_tool_details,
    }


async def _count_custom_agent_tokens(
    agent_definitions: Any,
) -> Dict[str, Any]:
    """Count tokens used by custom agent definitions."""
    try:
        active_agents = agent_definitions.active_agents
        custom_agents = [a for a in active_agents if getattr(a, 'source', None) != 'built-in']
    except (AttributeError, Exception):
        return {'agent_tokens': 0, 'agent_details': []}

    if not custom_agents:
        return {'agent_tokens': 0, 'agent_details': []}

    counts = await asyncio.gather(*[
        count_tokens_with_fallback(
            [{'role': 'user', 'content': f"{a.agent_type} {a.when_to_use}"}],
            [],
        )
        for a in custom_agents
    ])

    agent_details: List[Agent] = []
    total = 0
    for a, c in zip(custom_agents, counts):
        tokens = c or 0
        total += tokens
        agent_details.append(Agent(
            agent_type=getattr(a, 'agent_type', ''),
            source=getattr(a, 'source', ''),
            tokens=tokens,
        ))

    return {'agent_tokens': total, 'agent_details': agent_details}
