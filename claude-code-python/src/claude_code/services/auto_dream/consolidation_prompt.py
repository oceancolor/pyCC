"""
Auto-dream consolidation prompt builder.
Ported from services/autoDream/consolidationPrompt.ts
"""
from __future__ import annotations

# Constants that would normally come from memdir module
ENTRYPOINT_NAME = "MEMORY.md"
MAX_ENTRYPOINT_LINES = 200
DIR_EXISTS_GUIDANCE = (
    "If the memory directory doesn't exist yet, create it. "
    "All memory files live inside it."
)


def build_consolidation_prompt(
    memory_root: str,
    transcript_dir: str,
    extra: str = "",
) -> str:
    """
    Build the consolidation prompt for the auto-dream forked agent.

    :param memory_root: Path to the memory directory
    :param transcript_dir: Path to the session transcript directory
    :param extra: Additional context appended at the end
    :returns: The full consolidation prompt string
    """
    extra_section = (
        f"\n\n## Additional context\n\n{extra}" if extra.strip() else ""
    )

    return f"""# Dream: Memory Consolidation

You are performing a dream — a reflective pass over your memory files. Synthesize what you've learned recently into durable, well-organized memories so that future sessions can orient quickly.

Memory directory: `{memory_root}`
{DIR_EXISTS_GUIDANCE}

Session transcripts: `{transcript_dir}` (large JSONL files — grep narrowly, don't read whole files)

---

## Phase 1 — Orient

- `ls` the memory directory to see what already exists
- Read `{ENTRYPOINT_NAME}` to understand the current index
- Skim existing topic files so you improve them rather than creating duplicates
- If `logs/` or `sessions/` subdirectories exist (assistant-mode layout), review recent entries there

## Phase 2 — Gather recent signal

Look for new information worth persisting. Sources in rough priority order:

1. **Daily logs** (`logs/YYYY/MM/YYYY-MM-DD.md`) if present — these are the append-only stream
2. **Existing memories that drifted** — facts that contradict something you see in the codebase now
3. **Transcript search** — if you need specific context, grep the JSONL transcripts for narrow terms:
   `grep -rn "<narrow term>" {transcript_dir}/ --include="*.jsonl" | tail -50`

Don't exhaustively read transcripts. Look only for things you already suspect matter.

## Phase 3 — Consolidate

For each thing worth remembering, write or update a memory file at the top level of the memory directory.

Focus on:
- Merging new signal into existing topic files rather than creating near-duplicates
- Converting relative dates ("yesterday", "last week") to absolute dates
- Deleting contradicted facts — if today's investigation disproves an old memory, fix it at the source

## Phase 4 — Prune and index

Update `{ENTRYPOINT_NAME}` so it stays under {MAX_ENTRYPOINT_LINES} lines AND under ~25KB. It's an **index**, not a dump — each entry should be one line under ~150 characters: `- [Title](file.md) — one-line hook`. Never write memory content directly into it.

- Remove pointers to memories that are now stale, wrong, or superseded
- Demote verbose entries: if an index line is over ~200 chars, move the detail to the topic file
- Add pointers to newly important memories
- Resolve contradictions — if two files disagree, fix the wrong one

---

Return a brief summary of what you consolidated, updated, or pruned. If nothing changed (memories are already tight), say so.{extra_section}"""
