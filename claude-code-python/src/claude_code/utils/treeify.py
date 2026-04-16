"""
Render a list of file paths as an ASCII directory tree.

Unlike the TS version (which takes a nested dict), this implementation
accepts a flat list of path strings and builds the tree automatically —
a more natural interface for file-system listings.

Example::

    >>> from claude_code.utils.treeify import treeify
    >>> print(treeify(["src/a.py", "src/b.py", "README.md"]))
    ├── README.md
    └── src
        ├── a.py
        └── b.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Tree characters
# ---------------------------------------------------------------------------

BRANCH = "├──"
LAST_BRANCH = "└──"
LINE = "│"
EMPTY = " "


# ---------------------------------------------------------------------------
# Internal data model
# ---------------------------------------------------------------------------

@dataclass
class TreeNode:
    """One node in the in-memory tree.

    Attributes:
        name:     The path segment name (filename or directory name).
        children: Ordered dict of child name → :class:`TreeNode`.
        is_leaf:  True when this node represents an actual file (leaf).
    """

    name: str
    children: dict[str, "TreeNode"] = field(default_factory=dict)
    is_leaf: bool = False

    def __repr__(self) -> str:  # pragma: no cover
        return f"TreeNode({self.name!r}, children={list(self.children)!r})"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def treeify(paths: list[str], sort: bool = True) -> str:
    """Convert a list of slash-separated *paths* into an ASCII tree string.

    Args:
        paths: Relative file paths (forward slashes, e.g. ``"src/utils/foo.py"``).
        sort:  Sort siblings lexicographically.  Defaults to True.

    Returns:
        A multi-line string representing the tree.  Returns ``"(empty)"`` for
        an empty or all-blank input.
    """
    # Strip blank/None entries and normalise separators.
    cleaned = [p.strip().replace("\\", "/").strip("/") for p in paths if p and p.strip()]
    if not cleaned:
        return "(empty)"

    root = _build_tree(cleaned)

    if sort:
        _sort_tree(root)

    lines: list[str] = []
    children = list(root.children.values())
    for idx, child in enumerate(children):
        is_last = idx == len(children) - 1
        _render(child, prefix="", is_last=is_last, lines=lines)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_tree(paths: list[str]) -> TreeNode:
    """Build a virtual root :class:`TreeNode` from *paths*."""
    root = TreeNode(name="")
    for path in paths:
        parts = [p for p in path.split("/") if p]
        if not parts:
            continue
        node = root
        for i, part in enumerate(parts):
            is_last_part = i == len(parts) - 1
            if part not in node.children:
                node.children[part] = TreeNode(name=part)
            node = node.children[part]
            if is_last_part:
                node.is_leaf = True
    return root


def _sort_tree(node: TreeNode) -> None:
    """Recursively sort children: directories first, then files, both alpha."""
    if not node.children:
        return
    sorted_children = sorted(
        node.children.values(),
        key=lambda n: (n.is_leaf and not n.children, n.name.lower()),
    )
    node.children = {n.name: n for n in sorted_children}
    for child in node.children.values():
        _sort_tree(child)


def _render(
    node: TreeNode,
    prefix: str,
    is_last: bool,
    lines: list[str],
) -> None:
    """Recursively render *node* into *lines*."""
    connector = LAST_BRANCH if is_last else BRANCH
    lines.append(f"{prefix}{connector} {node.name}")

    children = list(node.children.values())
    if not children:
        return

    # Continuation prefix for children
    extension = f"{EMPTY}   " if is_last else f"{LINE}   "
    child_prefix = prefix + extension

    for idx, child in enumerate(children):
        child_is_last = idx == len(children) - 1
        _render(child, prefix=child_prefix, is_last=child_is_last, lines=lines)
