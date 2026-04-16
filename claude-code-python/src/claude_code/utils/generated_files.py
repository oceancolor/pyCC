"""
Detect generated/vendored files that should not be manually edited.

Mirrors TypeScript generatedFiles.ts using GitHub Linguist-style rules.

Key function: is_generated_file(path) -> bool
"""

import os
import re
from typing import Sequence

# ---------------------------------------------------------------------------
# Rule tables
# ---------------------------------------------------------------------------

_EXCLUDED_FILENAMES: frozenset[str] = frozenset({
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "bun.lock",
    "composer.lock",
    "gemfile.lock",
    "cargo.lock",
    "poetry.lock",
    "pipfile.lock",
    "shrinkwrap.json",
    "npm-shrinkwrap.json",
})

_EXCLUDED_EXTENSIONS: frozenset[str] = frozenset({
    ".lock",
    ".min.js",
    ".min.css",
    ".min.html",
    ".bundle.js",
    ".bundle.css",
    ".generated.ts",
    ".generated.js",
    ".d.ts",
})

_EXCLUDED_DIRECTORIES: tuple[str, ...] = (
    "/dist/",
    "/build/",
    "/out/",
    "/output/",
    "/node_modules/",
    "/vendor/",
    "/vendored/",
    "/third_party/",
    "/third-party/",
    "/external/",
    "/.next/",
    "/.nuxt/",
    "/.svelte-kit/",
    "/coverage/",
    "/__pycache__/",
    "/.tox/",
    "/venv/",
    "/.venv/",
    "/target/release/",
    "/target/debug/",
)

_EXCLUDED_FILENAME_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"^.*\.min\.[a-z]+$", re.IGNORECASE),
    re.compile(r"^.*-min\.[a-z]+$", re.IGNORECASE),
    re.compile(r"^.*\.bundle\.[a-z]+$", re.IGNORECASE),
    re.compile(r"^.*\.generated\.[a-z]+$", re.IGNORECASE),
    re.compile(r"^.*\.gen\.[a-z]+$", re.IGNORECASE),
    re.compile(r"^.*\.auto\.[a-z]+$", re.IGNORECASE),
    re.compile(r"^.*_generated\.[a-z]+$", re.IGNORECASE),
    re.compile(r"^.*_gen\.[a-z]+$", re.IGNORECASE),
    re.compile(r"^.*\.pb\.(go|js|ts|py|rb)$", re.IGNORECASE),
    re.compile(r"^.*_pb2?\.py$", re.IGNORECASE),
    re.compile(r"^.*\.pb\.h$", re.IGNORECASE),
    re.compile(r"^.*\.grpc\.[a-z]+$", re.IGNORECASE),
    re.compile(r"^.*\.swagger\.[a-z]+$", re.IGNORECASE),
    re.compile(r"^.*\.openapi\.[a-z]+$", re.IGNORECASE),
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_generated_file(file_path: str) -> bool:
    """
    Return True if *file_path* looks like a generated or vendored file
    that should not be manually edited.

    Args:
        file_path: Relative (or absolute) file path.

    Returns:
        True if the file is considered generated/vendored.
    """
    # Normalize to forward-slash and ensure leading /
    normalized = "/" + file_path.replace(os.sep, "/").lstrip("/")
    file_name = os.path.basename(file_path).lower()
    _, ext = os.path.splitext(file_name)

    # 1. Exact filename match
    if file_name in _EXCLUDED_FILENAMES:
        return True

    # 2. Simple extension match
    if ext in _EXCLUDED_EXTENSIONS:
        return True

    # 3. Compound extension (e.g. ".min.js" from "foo.min.js")
    parts = file_name.split(".")
    if len(parts) > 2:
        compound = "." + ".".join(parts[-2:])
        if compound in _EXCLUDED_EXTENSIONS:
            return True

    # 4. Directory path match
    for directory in _EXCLUDED_DIRECTORIES:
        if directory in normalized:
            return True

    # 5. Filename regex patterns
    for pattern in _EXCLUDED_FILENAME_PATTERNS:
        if pattern.match(file_name):
            return True

    return False


def filter_generated_files(files: Sequence[str]) -> list[str]:
    """
    Return *files* with generated/vendored paths removed.

    Args:
        files: Sequence of file paths.

    Returns:
        List containing only non-generated files.
    """
    return [f for f in files if not is_generated_file(f)]
