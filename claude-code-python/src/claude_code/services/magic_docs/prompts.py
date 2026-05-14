"""MagicDocs prompts. Ported from services/MagicDocs/prompts.ts"""
from __future__ import annotations
from pathlib import Path
from typing import Optional


def get_update_prompt_template() -> str:
    """Return the template used to ask Claude to update a Magic Doc."""
    return (
        "IMPORTANT: This message and these instructions are NOT part of the actual user "
        "conversation. Do NOT include any references to \"documentation updates\", \"magic docs\", "
        "or these update instructions in the document content.\n\n"
        "Based on the user conversation above (EXCLUDING this documentation update instruction "
        "message), update the Magic Doc file to incorporate any NEW learnings, insights, or "
        "information that would be valuable to preserve.\n\n"
        "The file {{docPath}} has already been read for you. Here are its current contents:\n"
        "<current_doc_content>\n"
        "{{docContents}}\n"
        "</current_doc_content>\n\n"
        "Document title: {{docTitle}}\n"
        "{{customInstructions}}\n\n"
        "Your ONLY task is to use the Edit tool to update the documentation file if there is "
        "substantial new information to add, then stop. You can make multiple edits (update "
        "multiple sections as needed) - make all Edit tool calls in parallel in a single message. "
        "If there's nothing substantial to add, simply respond with a brief explanation and do "
        "not call any tools.\n\n"
        "CRITICAL RULES FOR EDITING:\n"
        "- Preserve the Magic Doc header exactly as-is: # MAGIC DOC: {{docTitle}}\n"
        "- Keep the document CURRENT with the latest state of the codebase\n"
        "- Update information IN-PLACE to reflect the current state\n"
        "- Remove or replace outdated information\n"
        "- Fix obvious errors: typos, grammar mistakes, broken formatting, incorrect information\n\n"
        "DOCUMENTATION PHILOSOPHY:\n"
        "- BE TERSE. High signal only. No filler words.\n"
        "- Documentation is for OVERVIEWS, ARCHITECTURE, and ENTRY POINTS.\n"
        "- Do NOT duplicate information that's already obvious from reading the source code.\n"
        "- Focus on: WHY things exist, HOW components connect, WHERE to start reading."
    )


def build_update_prompt(
    doc_path: str,
    doc_contents: str,
    doc_title: str,
    custom_instructions: str = "",
) -> str:
    """Build a filled-in Magic Doc update prompt."""
    template = get_update_prompt_template()
    return (
        template
        .replace("{{docPath}}", doc_path)
        .replace("{{docContents}}", doc_contents)
        .replace("{{docTitle}}", doc_title)
        .replace("{{customInstructions}}", custom_instructions)
    )


async def get_update_prompt(
    doc_path: str,
    doc_title: str,
    custom_instructions: str = "",
) -> str:
    """Read doc_path and build a filled-in update prompt."""
    try:
        path = Path(doc_path)
        doc_contents = path.read_text(encoding="utf-8") if path.exists() else ""
    except Exception:
        doc_contents = ""
    return build_update_prompt(doc_path, doc_contents, doc_title, custom_instructions)


# Legacy alias
MAGIC_DOCS_PROMPT = get_update_prompt_template()
