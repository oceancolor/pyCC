"""Example commands for new-user onboarding. Ported from exampleCommands.ts.

Provides a curated list of example prompts shown to new users, plus helpers
to pick diverse examples from a project's git history.
"""
from __future__ import annotations

import os
import random
import re
from pathlib import Path
from typing import Dict, List, Optional

__all__ = [
    "EXAMPLE_COMMANDS",
    "get_example_commands",
    "format_examples",
    "count_and_sort_items",
    "pick_diverse_core_files",
]

# Non-core file patterns (auto-generated, dependency, or config artefacts)
_NON_CORE_PATTERNS: List[re.Pattern] = [
    re.compile(
        r"(?:^|\/)(?:package-lock\.json|yarn\.lock|bun\.lock(?:b)?|pnpm-lock\.yaml"
        r"|Pipfile\.lock|poetry\.lock|Cargo\.lock|Gemfile\.lock|go\.sum"
        r"|composer\.lock|uv\.lock)$"
    ),
    re.compile(r"\.generated\."),
    re.compile(r"(?:^|\/)(?:dist|build|out|target|node_modules|\.next|__pycache__)\/"),
    re.compile(r"\.(?:min\.js|min\.css|map|pyc|pyo)$"),
    re.compile(r"\.(?:json|ya?ml|toml|xml|ini|cfg|conf|env|lock|txt|md|mdx|rst|csv|log|svg)$", re.I),
    re.compile(r"(?:^|\/)\.?(?:eslintrc|prettierrc|babelrc|editorconfig|gitignore|gitattributes|dockerignore|npmrc)"),
    re.compile(r"(?:^|\/)(?:tsconfig|jsconfig|biome|vitest\.config|jest\.config|webpack\.config|vite\.config|rollup\.config)\.[a-z]+$"),
    re.compile(r"(?:^|\/)\.(?:github|vscode|idea|claude)\/"),
    re.compile(r"(?:^|\/)(?:CHANGELOG|LICENSE|CONTRIBUTING|CODEOWNERS|README)(?:\.[a-z]+)?$", re.I),
]

EXAMPLE_COMMANDS: List[dict] = [
    {"label": "Explain code", "prompt": "Explain how this project is structured"},
    {"label": "Fix bugs", "prompt": "Find and fix the bug in main.py"},
    {"label": "Write tests", "prompt": "Write unit tests for utils.py"},
    {"label": "Code review", "prompt": "Review recent changes and suggest improvements"},
    {"label": "Create file", "prompt": "Create a README.md file"},
    {"label": "Search code", "prompt": "Find all places that call the login function"},
    {"label": "Run tests", "prompt": "Run tests and fix any failures"},
    {"label": "Refactor", "prompt": "Refactor this file to improve readability"},
]


def _is_core_file(path: str) -> bool:
    """Return True if *path* is a core source file (not generated/dep/config)."""
    return not any(p.search(path) for p in _NON_CORE_PATTERNS)


def count_and_sort_items(items: List[str], top_n: int = 20) -> str:
    """Count occurrences and return the top *top_n* items sorted by frequency."""
    counts: Dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    sorted_items = sorted(counts.items(), key=lambda kv: -kv[1])[:top_n]
    return "\n".join(f"{count:6d} {item}" for item, count in sorted_items)


def pick_diverse_core_files(sorted_paths: List[str], want: int) -> List[str]:
    """Pick up to *want* diverse core files from a frequency-sorted list."""
    picked: List[str] = []
    seen_basenames: set = set()
    dir_tally: Dict[str, int] = {}

    for cap in range(1, want + 1):
        for p in sorted_paths:
            if len(picked) >= want:
                break
            if not _is_core_file(p):
                continue
            last_sep = max(p.rfind("/"), p.rfind("\\"))
            base = p[last_sep + 1:] if last_sep >= 0 else p
            if not base or base in seen_basenames:
                continue
            directory = p[:last_sep] if last_sep >= 0 else "."
            if dir_tally.get(directory, 0) >= cap:
                continue
            picked.append(base)
            seen_basenames.add(base)
            dir_tally[directory] = dir_tally.get(directory, 0) + 1

    return picked if len(picked) >= want else []


def get_example_commands(n: int = 4) -> List[dict]:
    """Return up to *n* example command dicts."""
    return EXAMPLE_COMMANDS[:n]


def get_random_example() -> Optional[str]:
    """Return a random formatted example prompt string."""
    if not EXAMPLE_COMMANDS:
        return None
    cmd = random.choice(EXAMPLE_COMMANDS)
    return f'Try "{cmd["prompt"]}"'


def format_examples(n: int = 4) -> str:
    """Return a formatted multi-line string of example prompts."""
    lines = ["Examples:"]
    for cmd in get_example_commands(n):
        lines.append(f'  claude "{cmd["prompt"]}"')
    return "\n".join(lines)
