"""Session memory prompts. Ported from services/SessionMemory/prompts.ts (324L)"""

MEMORY_EXTRACTION_SYSTEM_PROMPT = """You are a memory extraction assistant.
Extract important facts, user preferences, key decisions, and context from conversations.
Return each memory as a concise, factual statement.
Focus on information that would be useful in future sessions."""

MEMORY_EXTRACTION_USER_TEMPLATE = """Please extract memories from the following conversation:

{conversation}

Return memories as bullet points inside <memory> tags.
Example: <memory>User prefers TypeScript over JavaScript</memory>"""
