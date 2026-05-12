"""
Compact prompt builders.
Ported from services/compact/prompt.ts
"""
from __future__ import annotations

import os
import re
from typing import Optional

# ─── Constants ──────────────────────────────────────────────────────────────

DETAILED_ANALYSIS_INSTRUCTION_BASE = """\
Before answering, consider and analyze the conversation in depth:
1. Identify the most important information and context from the conversation
2. Determine what technical details are crucial for continuation
3. Note any ongoing tasks or unresolved issues
4. Consider what context would be most valuable for someone continuing the work

Be thorough and precise in your analysis, ensuring all key information is captured."""

NO_TOOLS_PREAMBLE = (
    "IMPORTANT: Do NOT use any tools. "
    "Do NOT call any functions. "
    "Respond with plain text only.\n\n"
)

NO_TOOLS_TRAILER = (
    "\n\nREMINDER: Do NOT call any tools. "
    "Respond with plain text only — "
    "an <analysis> block followed by a <summary> block. "
    "Tool calls will be rejected and you will fail the task."
)

BASE_COMPACT_PROMPT = f"""\
Your task is to create a detailed summary of the conversation so far. \
This summary will be used to continue the conversation in a new context window.

{DETAILED_ANALYSIS_INSTRUCTION_BASE}

Your summary should include the following sections:

1. Primary Request and Intent: Capture the user's explicit requests and intents in detail
2. Key Technical Concepts: List important technical concepts, technologies, and frameworks discussed.
3. Files and Code Sections: Enumerate specific files and code sections examined, modified, or created. \
Include full code snippets where applicable and include a summary of why this file read or edit is important.
4. Errors and fixes: List errors encountered and how they were fixed.
5. Problem Solving: Document problems solved and any ongoing troubleshooting efforts.
6. All user messages: List ALL user messages that are not tool results.
7. Pending Tasks: Outline any pending tasks.
8. Current Work: Describe in detail precisely what was being worked on immediately before this summary, \
providing enough detail that work can resume without losing progress.
9. Optional Next Step: List the next step that you will take that will fulfill the user's request.

Here's an example of how your output should be structured:

<example>
<analysis>
[Your thought process, ensuring all points are covered thoroughly and accurately]
</analysis>

<summary>
1. Primary Request and Intent:
   [Detailed description]

2. Key Technical Concepts:
   - [Concept 1]
   - [Concept 2]

3. Files and Code Sections:
   - [File Name 1]
      - [Summary of why this file is important]
      - [Important Code Snippet]

4. Errors and fixes:
    - [Error description]:
      - [How you fixed it]

5. Problem Solving:
   [Description]

6. All user messages:
    - [Detailed non tool use user message]

7. Pending Tasks:
   - [Task 1]

8. Current Work:
   [Precise description of current work]

9. Optional Next Step:
   [Optional Next step to take]

</summary>
</example>

Please provide your summary based on the RECENT messages only (after the retained earlier context), \
following this structure and ensuring precision and thoroughness in your response.
"""

PARTIAL_COMPACT_PROMPT = BASE_COMPACT_PROMPT

PARTIAL_COMPACT_UP_TO_PROMPT = f"""\
Your task is to create a detailed summary of this conversation. \
This summary will be placed at the start of a continuing session; newer messages that build on this \
context will follow after your summary (you do not see them here). \
Summarize thoroughly so that someone reading only your summary and then the newer messages can fully \
understand what happened and continue the work.

{DETAILED_ANALYSIS_INSTRUCTION_BASE}

Your summary should include the following sections:

1. Primary Request and Intent: Capture the user's explicit requests and intents in detail
2. Key Technical Concepts: List important technical concepts, technologies, and frameworks discussed.
3. Files and Code Sections: Enumerate specific files and code sections examined, modified, or created. \
Include full code snippets where applicable and include a summary of why this file read or edit is important.
4. Errors and fixes: List errors encountered and how they were fixed.
5. Problem Solving: Document problems solved and any ongoing troubleshooting efforts.
6. All user messages: List ALL user messages that are not tool results.
7. Pending Tasks: Outline any pending tasks.
8. Work Completed: Describe what was accomplished by the end of this portion.
9. Context for Continuing Work: Summarize any context, decisions, or state that would be needed to \
understand and continue the work in subsequent messages.

Here's an example of how your output should be structured:

<example>
<analysis>
[Your thought process, ensuring all points are covered thoroughly and accurately]
</analysis>

<summary>
1. Primary Request and Intent:
   [Detailed description]

2. Key Technical Concepts:
   - [Concept 1]
   - [Concept 2]

3. Files and Code Sections:
   - [File Name 1]
      - [Summary of why this file is important]
      - [Important Code Snippet]

4. Errors and fixes:
    - [Error description]:
      - [How you fixed it]

5. Problem Solving:
   [Description]

6. All user messages:
    - [Detailed non tool use user message]

7. Pending Tasks:
   - [Task 1]

8. Work Completed:
   [Description of what was accomplished]

9. Context for Continuing Work:
   [Key context, decisions, or state needed to continue the work]

</summary>
</example>

Please provide your summary following this structure, ensuring precision and thoroughness in your response.
"""

# ─── Public API ─────────────────────────────────────────────────────────────


def get_partial_compact_prompt(
    custom_instructions: Optional[str] = None,
    direction: str = "from",
) -> str:
    """Build the partial compact prompt (direction: 'from' or 'up_to')."""
    template = (
        PARTIAL_COMPACT_UP_TO_PROMPT if direction == "up_to" else PARTIAL_COMPACT_PROMPT
    )
    prompt = NO_TOOLS_PREAMBLE + template

    if custom_instructions and custom_instructions.strip():
        prompt += f"\n\nAdditional Instructions:\n{custom_instructions}"

    prompt += NO_TOOLS_TRAILER
    return prompt


def get_compact_prompt(custom_instructions: Optional[str] = None) -> str:
    """Build the full compact prompt."""
    prompt = NO_TOOLS_PREAMBLE + BASE_COMPACT_PROMPT

    if custom_instructions and custom_instructions.strip():
        prompt += f"\n\nAdditional Instructions:\n{custom_instructions}"

    prompt += NO_TOOLS_TRAILER
    return prompt


def format_compact_summary(summary: str) -> str:
    """Format a compact summary by stripping ``<analysis>`` and cleaning ``<summary>`` tags."""
    formatted = summary

    # Strip analysis block
    formatted = re.sub(r"<analysis>[\s\S]*?</analysis>", "", formatted)

    # Extract and format summary block
    m = re.search(r"<summary>([\s\S]*?)</summary>", formatted)
    if m:
        content = m.group(1) or ""
        formatted = re.sub(
            r"<summary>[\s\S]*?</summary>",
            f"Summary:\n{content.strip()}",
            formatted,
        )

    # Clean up whitespace
    formatted = re.sub(r"\n\n+", "\n\n", formatted)
    return formatted.strip()


def get_compact_user_summary_message(
    summary: str,
    suppress_follow_up_questions: Optional[bool] = None,
    transcript_path: Optional[str] = None,
    recent_messages_preserved: Optional[bool] = None,
) -> str:
    """Build the user-facing compact summary message."""
    formatted_summary = format_compact_summary(summary)

    base_summary = (
        "This session is being continued from a previous conversation that ran out of context. "
        "The summary below covers the earlier portion of the conversation.\n\n"
        + formatted_summary
    )

    if transcript_path:
        base_summary += (
            f"\n\nIf you need specific details from before compaction "
            f"(like exact code snippets, error messages, or content you generated), "
            f"read the full transcript at: {transcript_path}"
        )

    if recent_messages_preserved:
        base_summary += "\n\nRecent messages are preserved verbatim."

    if suppress_follow_up_questions:
        is_proactive = False
        try:
            from claude_code.utils.proactive import is_proactive_active  # type: ignore
            is_proactive = is_proactive_active()
        except ImportError:
            pass

        continuation = (
            f"{base_summary}\n"
            "Continue the conversation from where it left off without asking the user any further questions. "
            "Resume directly — do not acknowledge the summary, do not recap what was happening, "
            "do not preface with \"I'll continue\" or similar. "
            "Pick up the last task as if the break never happened."
        )

        if is_proactive:
            continuation += (
                "\n\nYou are running in autonomous/proactive mode. "
                "This is NOT a first wake-up — you were already working autonomously before compaction. "
                "Continue your work loop: pick up where you left off based on the summary above. "
                "Do not greet the user or ask what to work on."
            )

        return continuation

    return base_summary
