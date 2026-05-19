"""Magic docs service.

Fetches and processes MCP "magic documentation" pages — structured
reference pages that MCP servers publish so that agents can discover
their capabilities without calling ``list_tools`` every session.

Ported from: src/services/magicDocs/ (TypeScript)

Usage::

    from claude_code.services.magic_docs import fetch_magic_doc, MAGIC_DOCS_PROMPT
"""
from __future__ import annotations

from claude_code.services.magic_docs.magic_docs import fetch_magic_doc
from claude_code.services.magic_docs.prompts import MAGIC_DOCS_PROMPT

__all__ = [
    "fetch_magic_doc",
    "MAGIC_DOCS_PROMPT",
]
