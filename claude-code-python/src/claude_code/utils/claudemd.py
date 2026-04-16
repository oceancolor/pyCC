"""
Python port of utils/claudemd.ts (1479 lines)

Manages CLAUDE.md / CLAUDE.local.md memory-file discovery, parsing, and
@include-directive resolution for the claude-code Python runtime.

Key public API:
  - get_memory_files(force_include_external=False) -> list[MemoryFileInfo]
  - get_claude_mds(memory_files, filter_fn)         -> str
  - get_claude_md_content(cwd, user_home)            -> str
  - process_memory_file(file_path, type, ...)        -> list[MemoryFileInfo]
  - clear_memory_file_caches()
  - reset_get_memory_files_cache(reason)

Compared to the TS original:
  - Bun feature-flags (TEAMMEM, REACTIVE_COMPACT, …) are stubbed to False.
  - Analytics / growthbook calls are no-ops.
  - The memoize pattern is implemented with a simple module-level cache dict.
  - Lexer-based HTML-comment stripping uses regex (no `marked` dependency).
  - @include depth is capped at MAX_INCLUDE_DEPTH = 5.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_INCLUDE_DEPTH = 5
MAX_MEMORY_CHARACTER_COUNT = 40_000
MEMORY_INSTRUCTION_PROMPT = (
    "Codebase and user instructions are shown below. Be sure to adhere to these "
    "instructions. IMPORTANT: These instructions OVERRIDE any default behavior and "
    "you MUST follow them exactly as written."
)

# Text file extensions allowed in @include directives (prevents loading binary data).
TEXT_FILE_EXTENSIONS: set[str] = {
    # Markdown / text
    ".md", ".txt", ".text",
    # Data formats
    ".json", ".yaml", ".yml", ".toml", ".xml", ".csv",
    # Web
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    # JS/TS
    ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".mts", ".cts",
    # Python
    ".py", ".pyi", ".pyw",
    # Ruby
    ".rb", ".erb", ".rake",
    # Go / Rust / Java / Kotlin / Scala / C / C++ / C# / Swift
    ".go", ".rs", ".java", ".kt", ".kts", ".scala",
    ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx", ".cs", ".swift",
    # Shell
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
    # Config
    ".env", ".ini", ".cfg", ".conf", ".config", ".properties",
    # Database / API
    ".sql", ".graphql", ".gql", ".proto",
    # Frontend frameworks
    ".vue", ".svelte", ".astro",
    # Templating
    ".ejs", ".hbs", ".pug", ".jade",
    # Other languages
    ".php", ".pl", ".pm", ".lua", ".r", ".R", ".dart",
    ".ex", ".exs", ".erl", ".hrl",
    ".clj", ".cljs", ".cljc", ".edn",
    ".hs", ".lhs", ".elm", ".ml", ".mli",
    ".f", ".f90", ".f95", ".for",
    # Build files
    ".cmake", ".make", ".makefile", ".gradle", ".sbt",
    # Documentation
    ".rst", ".adoc", ".asciidoc", ".org", ".tex", ".latex",
    # Misc
    ".lock", ".log", ".diff", ".patch",
}

# ---------------------------------------------------------------------------
# MemoryType  (mirrors TS MemoryType union)
# ---------------------------------------------------------------------------

MemoryType = Literal["Managed", "User", "Project", "Local", "AutoMem", "TeamMem"]

# ---------------------------------------------------------------------------
# MemoryFileInfo dataclass
# ---------------------------------------------------------------------------


@dataclass
class MemoryFileInfo:
    """Represents a resolved CLAUDE.md / rules *.md file with its content."""

    path: str
    type: MemoryType
    content: str
    parent: Optional[str] = None          # path of the file that @included this one
    globs: Optional[List[str]] = None     # frontmatter paths patterns
    content_differs_from_disk: bool = False
    raw_content: Optional[str] = None


# ---------------------------------------------------------------------------
# Frontmatter helpers
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_FRONTMATTER_PATHS_RE = re.compile(r"^paths\s*:\s*(.*?)$", re.MULTILINE | re.IGNORECASE)


def _parse_frontmatter(raw: str) -> Tuple[Dict[str, Any], str]:
    """Extract YAML-ish frontmatter dict and remaining content.

    Only parses the ``paths`` key; other frontmatter entries are ignored.
    """
    m = _FRONTMATTER_RE.match(raw)
    if not m:
        return {}, raw

    fm_text = m.group(1)
    content_after = raw[m.end():]

    fm: Dict[str, Any] = {}
    paths_m = _FRONTMATTER_PATHS_RE.search(fm_text)
    if paths_m:
        raw_val = paths_m.group(1).strip()
        # Support inline list ``[a, b, c]`` or block list items (``- item``).
        if raw_val.startswith("["):
            fm["paths"] = [
                p.strip().strip('"').strip("'")
                for p in raw_val.strip("[]").split(",")
                if p.strip()
            ]
        else:
            # Try block-list style lines.
            block_items = re.findall(r"^\s*-\s*(.+)$", fm_text, re.MULTILINE)
            if block_items:
                fm["paths"] = [p.strip() for p in block_items if p.strip()]
            else:
                fm["paths"] = [raw_val] if raw_val else []

    return fm, content_after


def _parse_frontmatter_paths(raw_content: str) -> Tuple[str, Optional[List[str]]]:
    """Return (content_without_frontmatter, paths_or_None).

    If no ``paths`` frontmatter key, or all patterns are ``**``, returns None.
    """
    fm, content = _parse_frontmatter(raw_content)
    raw_paths: List[str] = fm.get("paths") or []

    patterns: List[str] = []
    for p in raw_paths:
        # Strip trailing /** suffix (ignore lib treats 'path' as matching path and descendants)
        if p.endswith("/**"):
            p = p[:-3]
        if p:
            patterns.append(p)

    if not patterns or all(p == "**" for p in patterns):
        return content, None
    return content, patterns


# ---------------------------------------------------------------------------
# HTML comment stripping (regex-based, mirrors TS stripHtmlComments)
# ---------------------------------------------------------------------------

_HTML_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->", re.DOTALL)
_CODE_FENCE_RE = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def strip_html_comments(content: str) -> Tuple[str, bool]:
    """Strip block-level HTML comments from markdown, preserving code blocks.

    Returns (stripped_content, was_something_stripped).
    """
    if "<!--" not in content:
        return content, False

    # Protect fenced code blocks by replacing with placeholders.
    placeholders: Dict[str, str] = {}
    counter = [0]

    def _protect(m: re.Match) -> str:
        key = f"\x00CODEBLOCK{counter[0]}\x00"
        counter[0] += 1
        placeholders[key] = m.group(0)
        return key

    protected = _CODE_FENCE_RE.sub(_protect, content)

    new_content = _HTML_COMMENT_RE.sub("", protected)
    stripped = new_content != protected

    # Restore protected blocks.
    for key, original in placeholders.items():
        new_content = new_content.replace(key, original)

    return new_content, stripped


# ---------------------------------------------------------------------------
# @include path extraction
# ---------------------------------------------------------------------------

_INCLUDE_RE = re.compile(r"(?:^|\s)@((?:[^\s\\]|\\ )+)", re.MULTILINE)


def _expand_path(path: str, base_dir: str) -> str:
    """Resolve @path to absolute path.

    Handles:
      - ``@./relative`` → relative to *base_dir*
      - ``@~/home`` → relative to user home
      - ``@/absolute`` → as-is
      - ``@plain`` → treated as relative to *base_dir*
    """
    path = path.replace("\\ ", " ")  # unescape spaces
    if path.startswith("~/"):
        return str(Path.home() / path[2:])
    if os.path.isabs(path):
        return path
    return str(Path(base_dir) / path)


def _extract_include_paths(content: str, file_path: str) -> List[str]:
    """Extract resolved @include paths from *content*.

    Ignores ``@path`` references inside fenced code blocks or inline code.
    """
    base_dir = str(Path(file_path).parent)
    # Remove fenced code blocks before searching.
    cleaned = _CODE_FENCE_RE.sub("", content)
    cleaned = _INLINE_CODE_RE.sub("", cleaned)
    # Remove HTML comments.
    cleaned = _HTML_COMMENT_RE.sub("", cleaned)

    paths: list[str] = []
    seen: set[str] = set()

    for m in _INCLUDE_RE.finditer(cleaned):
        raw = m.group(1)
        # Strip fragment identifier.
        if "#" in raw:
            raw = raw[:raw.index("#")]
        if not raw:
            continue

        # Validate: must start with ./ ../ ~/ / or alphanum/underscore/dot/dash.
        valid = (
            raw.startswith("./")
            or raw.startswith("../")
            or raw.startswith("~/")
            or (raw.startswith("/") and raw != "/")
            or bool(re.match(r"^[a-zA-Z0-9._-]", raw))
        )
        if not valid:
            continue

        resolved = _expand_path(raw, base_dir)
        if resolved not in seen:
            seen.add(resolved)
            paths.append(resolved)

    return paths


# ---------------------------------------------------------------------------
# parseMemoryFileContent  (pure, no I/O)
# ---------------------------------------------------------------------------

def _parse_memory_file_content(
    raw_content: str,
    file_path: str,
    mem_type: MemoryType,
    include_base_path: Optional[str] = None,
) -> Tuple[Optional[MemoryFileInfo], List[str]]:
    """Parse raw file bytes into a MemoryFileInfo plus resolved @include paths.

    Returns (info_or_None, include_paths).
    """
    ext = Path(file_path).suffix.lower()
    if ext and ext not in TEXT_FILE_EXTENSIONS:
        logger.debug("Skipping non-text file in @include: %s", file_path)
        return None, []

    content_without_fm, paths = _parse_frontmatter_paths(raw_content)

    # Strip HTML comments.
    stripped_content, _ = strip_html_comments(content_without_fm)

    # Truncate AutoMem / TeamMem entrypoints (stub: no-op in Python port).
    final_content = stripped_content

    # @include extraction.
    include_paths: List[str] = []
    if include_base_path is not None:
        include_paths = _extract_include_paths(stripped_content, include_base_path)

    content_differs = final_content != raw_content
    info = MemoryFileInfo(
        path=file_path,
        type=mem_type,
        content=final_content,
        globs=paths,
        content_differs_from_disk=content_differs,
        raw_content=raw_content if content_differs else None,
    )
    return info, include_paths


# ---------------------------------------------------------------------------
# safelyReadMemoryFileAsync
# ---------------------------------------------------------------------------

async def _safely_read_memory_file_async(
    file_path: str,
    mem_type: MemoryType,
    include_base_path: Optional[str] = None,
) -> Tuple[Optional[MemoryFileInfo], List[str]]:
    """Async wrapper around _parse_memory_file_content that handles I/O errors."""
    try:
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(
            None, lambda: Path(file_path).read_text(encoding="utf-8")
        )
        return _parse_memory_file_content(raw, file_path, mem_type, include_base_path)
    except (OSError, PermissionError, UnicodeDecodeError) as exc:
        code = getattr(exc, "errno", None)
        # ENOENT (2), EISDIR (21) → expected; EACCES (13) → log.
        if code not in (2, 21):
            logger.debug("Could not read memory file %s: %s", file_path, exc)
        return None, []


# ---------------------------------------------------------------------------
# processMemoryFile (public)
# ---------------------------------------------------------------------------

def _normalize_path(p: str) -> str:
    """Normalise a path string for comparison (lowercased on Windows)."""
    normalized = str(Path(p).resolve())
    if os.name == "nt":
        normalized = normalized.lower()
    return normalized


async def process_memory_file(
    file_path: str,
    mem_type: MemoryType,
    processed_paths: Set[str],
    include_external: bool,
    depth: int = 0,
    parent: Optional[str] = None,
    original_cwd: Optional[str] = None,
) -> List[MemoryFileInfo]:
    """Recursively process a memory file and its @include dependencies.

    Returns a list with the main file first, followed by @include'd files.
    """
    norm = _normalize_path(file_path)
    if norm in processed_paths or depth >= MAX_INCLUDE_DEPTH:
        return []

    processed_paths.add(norm)

    info, include_paths = await _safely_read_memory_file_async(
        file_path, mem_type, file_path
    )
    if not info or not info.content.strip():
        return []

    if parent:
        info.parent = parent

    result: List[MemoryFileInfo] = [info]

    _cwd = original_cwd or os.getcwd()

    for inc_path in include_paths:
        is_external = not _path_in_working_path(inc_path, _cwd)
        if is_external and not include_external:
            continue

        sub_files = await process_memory_file(
            inc_path,
            mem_type,
            processed_paths,
            include_external,
            depth + 1,
            file_path,
            original_cwd,
        )
        result.extend(sub_files)

    return result


def _path_in_working_path(path: str, working: str) -> bool:
    """Return True if *path* is under *working* (prefix check)."""
    try:
        Path(path).relative_to(working)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# processMdRules
# ---------------------------------------------------------------------------

async def process_md_rules(
    rules_dir: str,
    mem_type: MemoryType,
    processed_paths: Set[str],
    include_external: bool,
    conditional_rule: bool,
    original_cwd: Optional[str] = None,
    visited_dirs: Optional[Set[str]] = None,
) -> List[MemoryFileInfo]:
    """Process all .md files in a .claude/rules/ directory (and subdirectories).

    When *conditional_rule* is True only files WITH frontmatter ``paths`` are
    returned; when False, only files WITHOUT.
    """
    if visited_dirs is None:
        visited_dirs = set()

    if rules_dir in visited_dirs:
        return []
    visited_dirs.add(rules_dir)

    rules_path = Path(rules_dir)
    try:
        if not rules_path.is_dir():
            return []
        entries = sorted(rules_path.iterdir())
    except (OSError, PermissionError):
        return []

    result: List[MemoryFileInfo] = []
    for entry in entries:
        if entry.is_dir():
            sub = await process_md_rules(
                str(entry),
                mem_type,
                processed_paths,
                include_external,
                conditional_rule,
                original_cwd,
                visited_dirs,
            )
            result.extend(sub)
        elif entry.is_file() and entry.suffix.lower() == ".md":
            files = await process_memory_file(
                str(entry),
                mem_type,
                processed_paths,
                include_external,
                original_cwd=original_cwd,
            )
            result.extend(
                f for f in files
                if (f.globs is not None) == conditional_rule
            )

    return result


# ---------------------------------------------------------------------------
# Glob / ignore matching helpers (lightweight, no ``ignore`` npm dep)
# ---------------------------------------------------------------------------

def _glob_matches(pattern: str, rel_path: str) -> bool:
    """Very lightweight glob match (uses fnmatch fallback)."""
    import fnmatch
    # Normalise separators.
    rel_path = rel_path.replace(os.sep, "/")
    pattern = pattern.replace(os.sep, "/")
    # Direct match or path-starts-with pattern directory.
    if fnmatch.fnmatch(rel_path, pattern):
        return True
    # Also try matching as prefix of deeper path (like ignore lib behaviour).
    if fnmatch.fnmatch(rel_path + "/x", pattern + "/*"):
        return True
    return False


def _files_match_target(files: List[MemoryFileInfo], target_path: str, base_dir: str) -> List[MemoryFileInfo]:
    """Filter files to those whose glob patterns match *target_path*."""
    matched = []
    for f in files:
        if not f.globs:
            continue
        try:
            rel = str(Path(target_path).relative_to(base_dir)).replace(os.sep, "/")
        except ValueError:
            continue
        if rel.startswith("..") or os.path.isabs(rel):
            continue
        if any(_glob_matches(g, rel) for g in f.globs):
            matched.append(f)
    return matched


# ---------------------------------------------------------------------------
# Module-level memoize cache for get_memory_files
# ---------------------------------------------------------------------------

_memory_files_cache: Dict[bool, List[MemoryFileInfo]] = {}


def clear_memory_file_caches() -> None:
    """Invalidate the get_memory_files cache."""
    _memory_files_cache.clear()


def reset_get_memory_files_cache(reason: str = "session_start") -> None:
    """Invalidate caches; equivalent to TS ``resetGetMemoryFilesCache``."""
    clear_memory_file_caches()


# ---------------------------------------------------------------------------
# get_memory_files  (main entry point, async)
# ---------------------------------------------------------------------------

async def get_memory_files(
    force_include_external: bool = False,
    cwd: Optional[str] = None,
    user_home: Optional[str] = None,
) -> List[MemoryFileInfo]:
    """Discover and parse all CLAUDE.md / rules/*.md memory files.

    File loading order (lowest → highest priority):
      1. Managed:  /etc/claude-code/CLAUDE.md
      2. User:     ~/.claude/CLAUDE.md + ~/.claude/rules/*.md
      3. Project & Local: walk from root down to *cwd*
         - CLAUDE.md, .claude/CLAUDE.md, .claude/rules/*.md
         - CLAUDE.local.md

    Results are memoized by *force_include_external* until
    ``clear_memory_file_caches()`` / ``reset_get_memory_files_cache()`` is called.
    """
    if force_include_external in _memory_files_cache:
        return _memory_files_cache[force_include_external]

    result: List[MemoryFileInfo] = []
    processed: Set[str] = set()
    _cwd = cwd or os.getcwd()
    _home = user_home or str(Path.home())
    include_external = force_include_external

    # ── 1. Managed file ──────────────────────────────────────────────────
    managed_path = os.environ.get(
        "CLAUDE_CODE_MANAGED_CLAUDE_MD",
        "/etc/claude-code/CLAUDE.md",
    )
    result.extend(
        await process_memory_file(managed_path, "Managed", processed, include_external, original_cwd=_cwd)
    )
    managed_rules_dir = os.environ.get(
        "CLAUDE_CODE_MANAGED_RULES_DIR",
        "/etc/claude-code/.claude/rules",
    )
    result.extend(
        await process_md_rules(managed_rules_dir, "Managed", processed, include_external, False, _cwd)
    )

    # ── 2. User file ─────────────────────────────────────────────────────
    user_claude_dir = os.path.join(_home, ".claude")
    user_claude_md = os.path.join(user_claude_dir, "CLAUDE.md")
    result.extend(
        await process_memory_file(user_claude_md, "User", processed, True, original_cwd=_cwd)
    )
    user_rules_dir = os.path.join(user_claude_dir, "rules")
    result.extend(
        await process_md_rules(user_rules_dir, "User", processed, True, False, _cwd)
    )

    # ── 3. Walk from root → cwd ───────────────────────────────────────────
    dirs: List[str] = []
    current = Path(_cwd).resolve()
    while True:
        dirs.append(str(current))
        parent = current.parent
        if parent == current:
            break
        current = parent

    # Reversed: root first → cwd last (higher priority loaded last).
    for directory in reversed(dirs):
        # Project: CLAUDE.md
        project_md = os.path.join(directory, "CLAUDE.md")
        result.extend(
            await process_memory_file(project_md, "Project", processed, include_external, original_cwd=_cwd)
        )
        # Project: .claude/CLAUDE.md
        dot_claude_md = os.path.join(directory, ".claude", "CLAUDE.md")
        result.extend(
            await process_memory_file(dot_claude_md, "Project", processed, include_external, original_cwd=_cwd)
        )
        # Project: .claude/rules/*.md (unconditional only)
        rules_dir = os.path.join(directory, ".claude", "rules")
        result.extend(
            await process_md_rules(rules_dir, "Project", processed, include_external, False, _cwd)
        )
        # Local: CLAUDE.local.md
        local_md = os.path.join(directory, "CLAUDE.local.md")
        result.extend(
            await process_memory_file(local_md, "Local", processed, include_external, original_cwd=_cwd)
        )

    _memory_files_cache[force_include_external] = result
    return result


# ---------------------------------------------------------------------------
# get_claude_mds  (format memory files → single string)
# ---------------------------------------------------------------------------

def get_claude_mds(
    memory_files: List[MemoryFileInfo],
    filter_fn: Optional[Callable[[MemoryType], bool]] = None,
) -> str:
    """Render a list of MemoryFileInfo into a single system-prompt string.

    Mirrors TS ``getClaudeMds``.
    """
    memories: List[str] = []
    for f in memory_files:
        if filter_fn and not filter_fn(f.type):
            continue
        if not f.content:
            continue
        if f.type == "Project":
            desc = " (project instructions, checked into the codebase)"
        elif f.type == "Local":
            desc = " (user's private project instructions, not checked in)"
        elif f.type == "AutoMem":
            desc = " (user's auto-memory, persists across conversations)"
        else:
            desc = " (user's private global instructions for all projects)"

        memories.append(f"Contents of {f.path}{desc}:\n\n{f.content.strip()}")

    if not memories:
        return ""
    return f"{MEMORY_INSTRUCTION_PROMPT}\n\n" + "\n\n".join(memories)


# ---------------------------------------------------------------------------
# get_claude_md_content  (convenience function matching task spec)
# ---------------------------------------------------------------------------

async def get_claude_md_content(
    cwd: Optional[str] = None,
    user_home: Optional[str] = None,
) -> str:
    """Return the combined CLAUDE.md system-prompt string for *cwd*.

    This is the primary function consumed by the Python claude-code runtime to
    inject memory-file contents into the system prompt.
    """
    files = await get_memory_files(cwd=cwd, user_home=user_home)
    return get_claude_mds(files)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def is_memory_file_path(file_path: str) -> bool:
    """Return True if *file_path* looks like a CLAUDE.md / rules *.md file."""
    name = Path(file_path).name
    if name in ("CLAUDE.md", "CLAUDE.local.md"):
        return True
    sep = os.sep
    if name.endswith(".md") and f"{sep}.claude{sep}rules{sep}" in file_path:
        return True
    # Also match forward-slash variant on Windows.
    if name.endswith(".md") and "/.claude/rules/" in file_path:
        return True
    return False


def get_large_memory_files(files: List[MemoryFileInfo]) -> List[MemoryFileInfo]:
    """Return files whose content exceeds MAX_MEMORY_CHARACTER_COUNT."""
    return [f for f in files if len(f.content) > MAX_MEMORY_CHARACTER_COUNT]


async def process_conditioned_md_rules(
    target_path: str,
    rules_dir: str,
    mem_type: MemoryType,
    processed_paths: Set[str],
    include_external: bool,
    original_cwd: Optional[str] = None,
) -> List[MemoryFileInfo]:
    """Return only conditional rules that match *target_path*.

    A conditional rule is a .md file with frontmatter ``paths`` glob patterns.
    """
    files = await process_md_rules(
        rules_dir, mem_type, processed_paths, include_external,
        conditional_rule=True, original_cwd=original_cwd,
    )

    # Determine base dir for relative glob matching.
    if mem_type == "Project":
        # Parent of .claude dir, i.e. parent of parent of rules_dir.
        base_dir = str(Path(rules_dir).parent.parent)
    else:
        base_dir = original_cwd or os.getcwd()

    return _files_match_target(files, target_path, base_dir)
