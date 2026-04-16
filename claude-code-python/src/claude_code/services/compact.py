# 原始 TS: services/compact/compact.ts + autoCompact.ts
"""Compact service - conversation compression to stay within context limits."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Max output tokens for compact summary generation
COMPACT_MAX_OUTPUT_TOKENS = 8192


@dataclass
class CompactResult:
    """Result of a compaction operation."""

    summary: str
    original_message_count: int
    compacted_message_count: int
    tokens_before: int = 0
    tokens_after: int = 0


@dataclass
class CompactOptions:
    """Options controlling compaction behaviour."""

    custom_instructions: str = ""
    max_output_tokens: int = COMPACT_MAX_OUTPUT_TOKENS
    include_memory: bool = True


@dataclass
class AutoCompactConfig:
    """Configuration for automatic compaction triggers."""

    enabled: bool = True
    # Fraction of context window at which auto-compact fires (0–1)
    threshold: float = 0.85
    extra_kwargs: dict[str, Any] = field(default_factory=dict)


async def compact_messages(
    messages: list[dict[str, Any]],
    options: CompactOptions | None = None,
) -> CompactResult:
    """Compress *messages* into a short summary, preserving essential context.

    TODO: Implement actual model-driven summarisation via api.claude.
          For now returns a placeholder summary.
    """
    opts = options or CompactOptions()
    original_count = len(messages)

    if not messages:
        return CompactResult(
            summary="(no conversation to compact)",
            original_message_count=0,
            compacted_message_count=0,
        )

    # TODO: Call model to produce summary
    summary_parts = [
        "Conversation compacted.",
        f"({original_count} messages summarised)",
    ]
    if opts.custom_instructions:
        summary_parts.append(f"Instructions: {opts.custom_instructions}")

    logger.debug("compact_messages: %d → 1 summary", original_count)
    return CompactResult(
        summary=" ".join(summary_parts),
        original_message_count=original_count,
        compacted_message_count=1,
    )


def should_auto_compact(
    used_tokens: int,
    context_window: int,
    config: AutoCompactConfig | None = None,
) -> bool:
    """Return True when token usage exceeds the auto-compact threshold."""
    cfg = config or AutoCompactConfig()
    if not cfg.enabled or context_window <= 0:
        return False
    return (used_tokens / context_window) >= cfg.threshold


async def run_auto_compact_if_needed(
    messages: list[dict[str, Any]],
    used_tokens: int,
    context_window: int,
    config: AutoCompactConfig | None = None,
) -> CompactResult | None:
    """Run compaction when threshold is exceeded, or return None."""
    if not should_auto_compact(used_tokens, context_window, config):
        return None
    logger.info("Auto-compact triggered (%d / %d tokens)", used_tokens, context_window)
    return await compact_messages(messages)
