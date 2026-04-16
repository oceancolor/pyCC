"""
System prompt type branding.
Port of utils/systemPromptType.ts
"""
from typing import List


# SystemPrompt is just a tuple/list of strings with a brand marker.
# In Python we represent it as a plain list; the brand is enforced by convention.
SystemPrompt = List[str]


def as_system_prompt(value: List[str]) -> SystemPrompt:
    """Cast a list of strings to the SystemPrompt branded type."""
    return value
