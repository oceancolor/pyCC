"""Magic docs module exports."""
from claude_code.services.magic_docs.magic_docs import fetch_magic_doc
from claude_code.services.magic_docs.prompts import MAGIC_DOCS_PROMPT, MAGIC_DOCS_TOOL_DESCRIPTION

__all__ = [
    "fetch_magic_doc",
    "MAGIC_DOCS_PROMPT",
    "MAGIC_DOCS_TOOL_DESCRIPTION",
]
