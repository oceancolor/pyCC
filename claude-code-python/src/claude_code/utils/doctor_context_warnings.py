"""
doctor_context_warnings.py - Diagnose context window usage warnings.

Ported from doctorContextWarnings.ts.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Optional

MAX_MEMORY_CHARACTER_COUNT = 40_000
MCP_TOOLS_THRESHOLD = 25_000
AGENT_DESCRIPTIONS_THRESHOLD = 10_000


@dataclass
class MemoryFile:
    path: str
    content: str
    scope: str = "local"

    @property
    def is_large(self) -> bool:
        return len(self.content) > MAX_MEMORY_CHARACTER_COUNT


@dataclass
class ContextWarning:
    type: str  # 'claudemd_files'|'agent_descriptions'|'mcp_tools'|'unreachable_rules'
    severity: str  # 'warning'|'error'
    message: str
    details: list[str] = field(default_factory=list)
    current_value: int = 0
    threshold: int = 0


@dataclass
class ContextWarnings:
    claude_md_warning: Optional[ContextWarning] = None
    agent_warning: Optional[ContextWarning] = None
    mcp_warning: Optional[ContextWarning] = None
    unreachable_rules_warning: Optional[ContextWarning] = None

    @property
    def all_warnings(self) -> list[ContextWarning]:
        return [w for w in [
            self.claude_md_warning, self.agent_warning,
            self.mcp_warning, self.unreachable_rules_warning,
        ] if w is not None]

    def has_warnings(self) -> bool:
        return bool(self.all_warnings)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

async def check_claude_md_files(
    memory_files: Optional[list[MemoryFile]] = None,
) -> Optional[ContextWarning]:
    """Check for CLAUDE.md files exceeding MAX_MEMORY_CHARACTER_COUNT chars."""
    if memory_files is None:
        memory_files = await _load_memory_files()
    large = sorted(
        [f for f in memory_files if f.is_large],
        key=lambda f: len(f.content), reverse=True,
    )
    if not large:
        return None
    details = [f"{f.path}: {len(f.content):,} chars" for f in large]
    if len(large) == 1:
        msg = (f"Large CLAUDE.md file detected "
               f"({len(large[0].content):,} chars > {MAX_MEMORY_CHARACTER_COUNT:,})")
    else:
        msg = (f"{len(large)} large CLAUDE.md files detected "
               f"(each > {MAX_MEMORY_CHARACTER_COUNT:,} chars)")
    return ContextWarning(
        type="claudemd_files", severity="warning", message=msg,
        details=details, current_value=len(large),
        threshold=MAX_MEMORY_CHARACTER_COUNT,
    )


async def check_agent_descriptions(
    agent_token_counts: Optional[list[dict[str, Any]]] = None,
    total_tokens: int = 0,
) -> Optional[ContextWarning]:
    """Check agent description token counts against AGENT_DESCRIPTIONS_THRESHOLD."""
    if not agent_token_counts:
        return None
    if total_tokens == 0:
        total_tokens = sum(a.get("tokens", 0) for a in agent_token_counts)
    if total_tokens <= AGENT_DESCRIPTIONS_THRESHOLD:
        return None
    sorted_agents = sorted(agent_token_counts, key=lambda a: a.get("tokens", 0), reverse=True)
    details = [f"{a['name']}: ~{a['tokens']:,} tokens" for a in sorted_agents[:5]]
    if len(sorted_agents) > 5:
        details.append(f"({len(sorted_agents) - 5} more custom agents)")
    return ContextWarning(
        type="agent_descriptions", severity="warning",
        message=(f"Large agent descriptions "
                 f"(~{total_tokens:,} tokens > {AGENT_DESCRIPTIONS_THRESHOLD:,})"),
        details=details, current_value=total_tokens,
        threshold=AGENT_DESCRIPTIONS_THRESHOLD,
    )


async def check_mcp_tools(
    tool_details: Optional[list[dict[str, Any]]] = None,
    total_tokens: int = 0,
) -> Optional[ContextWarning]:
    """Check MCP tool token counts against MCP_TOOLS_THRESHOLD."""
    if not tool_details:
        return None
    if total_tokens == 0:
        total_tokens = sum(t.get("tokens", 0) for t in tool_details)
    if total_tokens <= MCP_TOOLS_THRESHOLD:
        return None
    by_server: dict[str, dict[str, int]] = {}
    for tool in tool_details:
        parts = tool.get("name", "").split("__")
        srv = parts[1] if len(parts) > 1 else "unknown"
        entry = by_server.setdefault(srv, {"count": 0, "tokens": 0})
        entry["count"] += 1
        entry["tokens"] += tool.get("tokens", 0)
    sorted_servers = sorted(by_server.items(), key=lambda kv: kv[1]["tokens"], reverse=True)
    details = [f"{n}: {i['count']} tools (~{i['tokens']:,} tokens)" for n, i in sorted_servers[:5]]
    if len(sorted_servers) > 5:
        details.append(f"({len(sorted_servers) - 5} more servers)")
    return ContextWarning(
        type="mcp_tools", severity="warning",
        message=(f"Large MCP tools context "
                 f"(~{total_tokens:,} tokens > {MCP_TOOLS_THRESHOLD:,})"),
        details=details, current_value=total_tokens, threshold=MCP_TOOLS_THRESHOLD,
    )


async def check_unreachable_rules(
    unreachable: Optional[list[dict[str, str]]] = None,
) -> Optional[ContextWarning]:
    """Check for unreachable / shadowed permission rules."""
    if not unreachable:
        return None
    details: list[str] = []
    for r in unreachable:
        details.append(f"{r.get('rule', '')}: {r.get('reason', '')}")
        details.append(f"  Fix: {r.get('fix', '')}")
    count = len(unreachable)
    plural = "rule" if count == 1 else "rules"
    return ContextWarning(
        type="unreachable_rules", severity="warning",
        message=f"{count} unreachable permission {plural} detected",
        details=details, current_value=count, threshold=0,
    )


# ---------------------------------------------------------------------------
# Aggregate check
# ---------------------------------------------------------------------------

async def check_context_warnings(
    memory_files: Optional[list[MemoryFile]] = None,
    agent_token_counts: Optional[list[dict[str, Any]]] = None,
    agent_total_tokens: int = 0,
    mcp_tool_details: Optional[list[dict[str, Any]]] = None,
    mcp_total_tokens: int = 0,
    unreachable_rules: Optional[list[dict[str, str]]] = None,
) -> ContextWarnings:
    """Run all context checks concurrently and return aggregated warnings."""
    (cm, ag, mcp, ur) = await asyncio.gather(
        check_claude_md_files(memory_files),
        check_agent_descriptions(agent_token_counts, agent_total_tokens),
        check_mcp_tools(mcp_tool_details, mcp_total_tokens),
        check_unreachable_rules(unreachable_rules),
    )
    return ContextWarnings(
        claude_md_warning=cm, agent_warning=ag,
        mcp_warning=mcp, unreachable_rules_warning=ur,
    )


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

async def _load_memory_files() -> list[MemoryFile]:
    """Scan cwd upward to home for CLAUDE.md files."""
    files: list[MemoryFile] = []
    cwd = os.getcwd()
    home = os.path.expanduser("~")
    current = cwd
    while True:
        candidate = os.path.join(current, "CLAUDE.md")
        if os.path.isfile(candidate):
            try:
                with open(candidate, encoding="utf-8", errors="replace") as fh:
                    files.append(MemoryFile(path=candidate, content=fh.read()))
            except OSError:
                pass
        if current == home or not current or current == os.path.dirname(current):
            break
        current = os.path.dirname(current)
    return files
