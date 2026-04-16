# 原始 TS: utils/betas.ts
"""Beta 功能开关"""
from __future__ import annotations
import os
from typing import Set

KNOWN_BETAS: Set[str] = {
    "computer-use-2024-10-22",
    "interleaved-thinking-2025-05-14",
    "token-efficient-tools-2025-02-19",
    "web-search-2025-03-05",
    "files-api-2025-04-14",
}


def get_enabled_betas() -> Set[str]:
    raw = os.environ.get("ANTHROPIC_BETAS", "")
    if not raw:
        return set()
    return {b.strip() for b in raw.split(",") if b.strip()}


def is_beta_enabled(beta: str) -> bool:
    return beta in get_enabled_betas()


def build_betas_header(extra: Set[str] | None = None) -> list[str]:
    betas = get_enabled_betas()
    if extra:
        betas |= extra
    return sorted(betas)
