"""
Walk plugin markdown - walks and parses markdown files in plugin directories.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Generator, Iterator, List, Optional, Tuple


def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """Parse YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}, content

    end_idx = content.find("---", 3)
    if end_idx == -1:
        return {}, content

    frontmatter_str = content[3:end_idx].strip()
    body = content[end_idx + 3:].lstrip("\n")

    frontmatter: Dict[str, Any] = {}
    for line in frontmatter_str.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            frontmatter[key.strip()] = value.strip()

    return frontmatter, body


def walk_plugin_markdown(
    plugin_dir: str,
    subdirectory: str = "",
) -> Iterator[Dict[str, Any]]:
    """
    Walk a plugin directory and yield parsed markdown file info.
    Yields dicts with 'path', 'frontmatter', 'content', 'filename'.
    """
    search_dir = os.path.join(plugin_dir, subdirectory) if subdirectory else plugin_dir
    if not os.path.isdir(search_dir):
        return

    for filename in sorted(os.listdir(search_dir)):
        if not filename.endswith(".md"):
            continue
        path = os.path.join(search_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            frontmatter, body = parse_frontmatter(content)
            yield {
                "path": path,
                "filename": filename,
                "frontmatter": frontmatter,
                "content": body,
                "rawContent": content,
            }
        except Exception:
            continue


def collect_plugin_markdown_files(
    plugin_dir: str,
    subdirectory: str = "",
) -> List[Dict[str, Any]]:
    """Collect all markdown files from a plugin directory."""
    return list(walk_plugin_markdown(plugin_dir, subdirectory))
