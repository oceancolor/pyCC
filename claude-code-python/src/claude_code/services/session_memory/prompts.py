"""
Session memory prompts and template management.
Ported from services/SessionMemory/prompts.ts (324 lines)
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Dict, Tuple

log = logging.getLogger(__name__)

MAX_SECTION_LENGTH = 2000
MAX_TOTAL_SESSION_MEMORY_TOKENS = 12000

DEFAULT_SESSION_MEMORY_TEMPLATE = """
# Session Title
_A short and distinctive 5-10 word descriptive title for the session. Super info dense, no filler_

# Current State
_What is actively being worked on right now? Pending tasks not yet completed. Immediate next steps._

# Task specification
_What did the user ask to build? Any design decisions or other explanatory context_

# Files and Functions
_What are the important files? In short, what do they contain and why are they relevant?_

# Workflow
_What bash commands are usually run and in what order? How to interpret their output if not obvious?_

# Errors & Corrections
_Errors encountered and how they were fixed. What did the user correct? What approaches failed and should not be tried again?_

# Codebase and System Documentation
_What are the important system components? How do they work/fit together?_

# Learnings
_What has worked well? What has not? What to avoid? Do not duplicate items from other sections_

# Key results
_If the user asked a specific output such as an answer to a question, a table, or other document, repeat the exact result here_

# Worklog
_Step by step, what was attempted, done? Very terse summary for each step_
""".lstrip()


def _get_default_update_prompt() -> str:
    return (
        f"IMPORTANT: This message and these instructions are NOT part of the actual user conversation. "
        f"Do NOT include any references to \"note-taking\", \"session notes extraction\", or these update "
        f"instructions in the notes content.\n\n"
        f"Based on the user conversation above (EXCLUDING this note-taking instruction message as well as "
        f"system prompt, claude.md entries, or any past session summaries), update the session notes file.\n\n"
        f"The file {{{{notesPath}}}} has already been read for you. Here are its current contents:\n"
        f"<current_notes_content>\n"
        f"{{{{currentNotes}}}}\n"
        f"</current_notes_content>\n\n"
        f"Your ONLY task is to use the Edit tool to update the notes file, then stop. You can make multiple "
        f"edits (update every section as needed) - make all Edit tool calls in parallel in a single message. "
        f"Do not call any other tools.\n\n"
        f"CRITICAL RULES FOR EDITING:\n"
        f"- The file must maintain its exact structure with all sections, headers, and italic descriptions intact\n"
        f"-- NEVER modify, delete, or add section headers (the lines starting with '#' like # Task specification)\n"
        f"-- NEVER modify or delete the italic _section description_ lines (these are the lines in italics "
        f"immediately following each header - they start and end with underscores)\n"
        f"-- The italic _section descriptions_ are TEMPLATE INSTRUCTIONS that must be preserved exactly as-is "
        f"- they guide what content belongs in each section\n"
        f"-- ONLY update the actual content that appears BELOW the italic _section descriptions_ within each "
        f"existing section\n"
        f"-- Do NOT add any new sections, summaries, or information outside the existing structure\n"
        f"- Do NOT reference this note-taking process or instructions anywhere in the notes\n"
        f"- It's OK to skip updating a section if there are no substantial new insights to add. "
        f"Do not add filler content like \"No info yet\", just leave sections blank/unedited if appropriate.\n"
        f"- Write DETAILED, INFO-DENSE content for each section - include specifics like file paths, "
        f"function names, error messages, exact commands, technical details, etc.\n"
        f"- For \"Key results\", include the complete, exact output the user requested (e.g., full table, "
        f"full answer, etc.)\n"
        f"- Do not include information that's already in the CLAUDE.md files included in the context\n"
        f"- Keep each section under ~{MAX_SECTION_LENGTH} tokens/words - if a section is approaching this "
        f"limit, condense it by cycling out less important details while preserving the most critical information\n"
        f"- Focus on actionable, specific information that would help someone understand or recreate the work "
        f"discussed in the conversation\n"
        f"- IMPORTANT: Always update \"Current State\" to reflect the most recent work - this is critical "
        f"for continuity after compaction\n\n"
        f"Use the Edit tool with file_path: {{{{notesPath}}}}\n\n"
        f"STRUCTURE PRESERVATION REMINDER:\n"
        f"Each section has TWO parts that must be preserved exactly as they appear in the current file:\n"
        f"1. The section header (line starting with #)\n"
        f"2. The italic description line (the _italicized text_ immediately after the header - this is a "
        f"template instruction)\n\n"
        f"You ONLY update the actual content that comes AFTER these two preserved lines. The italic description "
        f"lines starting and ending with underscores are part of the template structure, NOT content to be "
        f"edited or removed.\n\n"
        f"REMEMBER: Use the Edit tool in parallel and stop. Do not continue after the edits. Only include "
        f"insights from the actual user conversation, never from these note-taking instructions. Do not delete "
        f"or change section headers or italic _section descriptions_."
    )


def _get_claude_config_home_dir() -> str:
    try:
        from claude_code.utils.env_utils import get_claude_config_home_dir  # type: ignore
        return get_claude_config_home_dir()
    except ImportError:
        return os.path.expanduser("~/.claude")


def _rough_token_count_estimation(text: str) -> int:
    return max(1, len(text) // 4)


async def load_session_memory_template() -> str:
    """Load custom session memory template from file if it exists."""
    template_path = Path(_get_claude_config_home_dir()) / "session-memory" / "config" / "template.md"
    try:
        content = template_path.read_text(encoding="utf-8")
        return content
    except FileNotFoundError:
        return DEFAULT_SESSION_MEMORY_TEMPLATE
    except Exception as exc:
        log.error("Error loading session memory template: %s", exc)
        return DEFAULT_SESSION_MEMORY_TEMPLATE


async def load_session_memory_prompt() -> str:
    """Load custom session memory prompt from file if it exists.

    Custom prompts can be placed at ~/.claude/session-memory/config/prompt.md
    Use {{variableName}} syntax for variable substitution.
    """
    prompt_path = Path(_get_claude_config_home_dir()) / "session-memory" / "config" / "prompt.md"
    try:
        content = prompt_path.read_text(encoding="utf-8")
        return content
    except FileNotFoundError:
        return _get_default_update_prompt()
    except Exception as exc:
        log.error("Error loading session memory prompt: %s", exc)
        return _get_default_update_prompt()


def _analyze_section_sizes(content: str) -> Dict[str, int]:
    """Parse session memory and return token counts per section."""
    sections: Dict[str, int] = {}
    lines = content.split("\n")
    current_section = ""
    current_content: list = []

    for line in lines:
        if line.startswith("# "):
            if current_section and current_content:
                section_content = "\n".join(current_content).strip()
                sections[current_section] = _rough_token_count_estimation(section_content)
            current_section = line
            current_content = []
        else:
            current_content.append(line)

    if current_section and current_content:
        section_content = "\n".join(current_content).strip()
        sections[current_section] = _rough_token_count_estimation(section_content)

    return sections


def _generate_section_reminders(
    section_sizes: Dict[str, int],
    total_tokens: int,
) -> str:
    """Generate reminders for sections that are too long."""
    over_budget = total_tokens > MAX_TOTAL_SESSION_MEMORY_TOKENS
    oversized = sorted(
        [(s, t) for s, t in section_sizes.items() if t > MAX_SECTION_LENGTH],
        key=lambda x: -x[1],
    )

    if not oversized and not over_budget:
        return ""

    parts: list = []

    if over_budget:
        parts.append(
            f"\n\nCRITICAL: The session memory file is currently ~{total_tokens} tokens, which exceeds "
            f"the maximum of {MAX_TOTAL_SESSION_MEMORY_TOKENS} tokens. You MUST condense the file to fit "
            f"within this budget. Aggressively shorten oversized sections by removing less important details, "
            f"merging related items, and summarizing older entries. Prioritize keeping \"Current State\" and "
            f"\"Errors & Corrections\" accurate and detailed."
        )

    if oversized:
        lines_text = "\n".join(
            f'- "{s}" is ~{t} tokens (limit: {MAX_SECTION_LENGTH})' for s, t in oversized
        )
        if over_budget:
            parts.append(f"\n\nOversized sections to condense:\n{lines_text}")
        else:
            parts.append(
                f"\n\nIMPORTANT: The following sections exceed the per-section limit and MUST be condensed:\n"
                f"{lines_text}"
            )

    return "".join(parts)


def _substitute_variables(template: str, variables: Dict[str, str]) -> str:
    """Substitute {{variable}} placeholders in template."""
    def replacer(match: re.Match) -> str:
        key = match.group(1)
        return variables.get(key, match.group(0))

    return re.sub(r"\{\{(\w+)\}\}", replacer, template)


async def is_session_memory_empty(content: str) -> bool:
    """Return True if content matches the default template (no real data yet)."""
    template = await load_session_memory_template()
    return content.strip() == template.strip()


async def build_session_memory_update_prompt(
    current_notes: str,
    notes_path: str,
) -> str:
    """Build the prompt used to update session memory notes."""
    prompt_template = await load_session_memory_prompt()

    section_sizes = _analyze_section_sizes(current_notes)
    total_tokens = _rough_token_count_estimation(current_notes)
    section_reminders = _generate_section_reminders(section_sizes, total_tokens)

    variables = {
        "currentNotes": current_notes,
        "notesPath": notes_path,
    }

    base_prompt = _substitute_variables(prompt_template, variables)
    return base_prompt + section_reminders


def _flush_session_section(
    section_header: str,
    section_lines: list,
    max_chars_per_section: int,
) -> Tuple[list, bool]:
    """Flush a session memory section, truncating if necessary."""
    if not section_header:
        return list(section_lines), False

    section_content = "\n".join(section_lines)
    if len(section_content) <= max_chars_per_section:
        return [section_header] + list(section_lines), False

    # Truncate at line boundary
    char_count = 0
    kept_lines = [section_header]
    for line in section_lines:
        if char_count + len(line) + 1 > max_chars_per_section:
            break
        kept_lines.append(line)
        char_count += len(line) + 1
    kept_lines.append("\n[... section truncated for length ...]")
    return kept_lines, True


def truncate_session_memory_for_compact(content: str) -> Dict[str, object]:
    """Truncate session memory sections that exceed per-section token limit.

    Returns: {"truncatedContent": str, "wasTruncated": bool}
    """
    lines = content.split("\n")
    max_chars_per_section = MAX_SECTION_LENGTH * 4  # rough_token uses len//4
    output_lines: list = []
    current_section_lines: list = []
    current_section_header = ""
    was_truncated = False

    for line in lines:
        if line.startswith("# "):
            result_lines, truncated = _flush_session_section(
                current_section_header,
                current_section_lines,
                max_chars_per_section,
            )
            output_lines.extend(result_lines)
            was_truncated = was_truncated or truncated
            current_section_header = line
            current_section_lines = []
        else:
            current_section_lines.append(line)

    # Flush last section
    result_lines, truncated = _flush_session_section(
        current_section_header,
        current_section_lines,
        max_chars_per_section,
    )
    output_lines.extend(result_lines)
    was_truncated = was_truncated or truncated

    return {
        "truncatedContent": "\n".join(output_lines),
        "wasTruncated": was_truncated,
    }
