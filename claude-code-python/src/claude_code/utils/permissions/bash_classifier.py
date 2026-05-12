"""
Bash classifier - semantic Bash command classification (ANT-only stub).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

PROMPT_PREFIX = "prompt:"


class ClassifierResult:
    def __init__(
        self,
        matches: bool,
        confidence: str,
        reason: str,
        matched_description: Optional[str] = None,
    ) -> None:
        self.matches = matches
        self.matched_description = matched_description
        self.confidence = confidence  # 'high' | 'medium' | 'low'
        self.reason = reason


ClassifierBehavior = str  # 'deny' | 'ask' | 'allow'


def extract_prompt_description(rule_content: Optional[str]) -> Optional[str]:
    """Extract the prompt description from rule content."""
    return None


def create_prompt_rule_content(description: str) -> str:
    """Create a rule content string with prompt prefix."""
    return f"{PROMPT_PREFIX} {description.strip()}"


def is_classifier_permissions_enabled() -> bool:
    """Check if classifier permissions feature is enabled (ANT-only)."""
    return False


def get_bash_prompt_deny_descriptions(context: Any) -> List[str]:
    return []


def get_bash_prompt_ask_descriptions(context: Any) -> List[str]:
    return []


def get_bash_prompt_allow_descriptions(context: Any) -> List[str]:
    return []


async def classify_bash_command(
    command: str,
    cwd: str,
    descriptions: List[str],
    behavior: ClassifierBehavior,
    signal: Any,
    is_non_interactive_session: bool,
) -> ClassifierResult:
    """Classify a Bash command (ANT-only stub: always returns not matching)."""
    return ClassifierResult(
        matches=False,
        confidence="high",
        reason="This feature is disabled",
    )


async def generate_generic_description(
    command: str,
    specific_description: Optional[str],
    signal: Any,
) -> Optional[str]:
    """Generate a generic description for a command."""
    return specific_description
