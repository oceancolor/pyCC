"""
Shell command execution prompts and risk classification.
Port of promptShellExecution.ts — parse embedded shell commands in prompt text
and classify their risk level.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pattern constants (mirrors TS BLOCK_PATTERN / INLINE_PATTERN)
# ---------------------------------------------------------------------------

# Code block: ```! ... ```
BLOCK_PATTERN = re.compile(r"```!\s*\n?([\s\S]*?)\n?```", re.MULTILINE)

# Inline: !`command` — must be preceded by whitespace or start-of-line
INLINE_PATTERN = re.compile(r"(?:^|\s)!`([^`]+)`", re.MULTILINE)

# ---------------------------------------------------------------------------
# Risk classification
# ---------------------------------------------------------------------------

# High-risk command prefixes / patterns
_HIGH_RISK_PATTERNS = [
    re.compile(r"\brm\s+-rf?\b"),
    re.compile(r"\bdd\b"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bformat\b"),
    re.compile(r"\bfdisk\b"),
    re.compile(r"\bsudo\b"),
    re.compile(r"\bchmod\s+777\b"),
    re.compile(r"\bcurl\b.*\|\s*(?:bash|sh)\b"),
    re.compile(r"\bwget\b.*\|\s*(?:bash|sh)\b"),
    re.compile(r">\s*/dev/"),
    re.compile(r"\bkill\s+-9\b"),
    re.compile(r"\bpkill\b"),
    re.compile(r"\bsystemctl\s+(?:stop|disable|mask)\b"),
    re.compile(r"\bdrop\s+(?:database|table)\b", re.IGNORECASE),
    re.compile(r"\btruncate\s+table\b", re.IGNORECASE),
]

_MEDIUM_RISK_PATTERNS = [
    re.compile(r"\brm\b"),
    re.compile(r"\bmv\b"),
    re.compile(r"\bchmod\b"),
    re.compile(r"\bchown\b"),
    re.compile(r"\bnpm\s+(?:install|uninstall|publish)\b"),
    re.compile(r"\bpip\s+(?:install|uninstall)\b"),
    re.compile(r"\bapt(?:-get)?\s+(?:install|remove|purge)\b"),
    re.compile(r"\bbrew\s+(?:install|uninstall|remove)\b"),
    re.compile(r"\bgit\s+(?:push|reset|rebase|force)\b"),
    re.compile(r"\bssh\b"),
    re.compile(r"\bscp\b"),
    re.compile(r"\brsync\b"),
    re.compile(r"\bcurl\b"),
    re.compile(r"\bwget\b"),
]


def classify_command_risk(command: str) -> str:
    """Return ``'high'``, ``'medium'``, or ``'low'`` for *command*."""
    cmd = command.strip()
    for pat in _HIGH_RISK_PATTERNS:
        if pat.search(cmd):
            return "high"
    for pat in _MEDIUM_RISK_PATTERNS:
        if pat.search(cmd):
            return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Execution prompt generation
# ---------------------------------------------------------------------------

@dataclass
class ExecutionContext:
    cwd: str = ""
    user: str = ""
    shell: str = "bash"
    extra: dict[str, str] = field(default_factory=dict)


_RISK_LABELS = {
    "high": "⚠️  HIGH RISK",
    "medium": "⚡ MEDIUM RISK",
    "low": "✅ LOW RISK",
}

_RISK_ADVICE = {
    "high": (
        "This command is potentially destructive and cannot be undone. "
        "Review carefully before allowing execution."
    ),
    "medium": (
        "This command modifies the system or transfers data. "
        "Verify the intent before proceeding."
    ),
    "low": "This command appears safe to execute.",
}


def generate_execution_prompt(
    command: str,
    context: Optional[ExecutionContext] = None,
) -> str:
    """Return a human-readable safety warning string for *command*.

    The string is suitable for display in a terminal or as part of a
    permission-check dialogue.
    """
    ctx = context or ExecutionContext()
    risk = classify_command_risk(command)
    label = _RISK_LABELS[risk]
    advice = _RISK_ADVICE[risk]

    lines = [
        f"{label}: Shell command execution requested",
        "",
        f"  Command : {command}",
    ]
    if ctx.cwd:
        lines.append(f"  CWD     : {ctx.cwd}")
    if ctx.user:
        lines.append(f"  User    : {ctx.user}")
    if ctx.shell and ctx.shell != "bash":
        lines.append(f"  Shell   : {ctx.shell}")
    lines += ["", f"  {advice}"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt text parsing helpers
# ---------------------------------------------------------------------------

def extract_shell_commands(text: str) -> list[str]:
    """Return all shell commands embedded in *text*.

    Recognises both block (```! ... ```) and inline (!`...`) syntaxes.
    """
    commands: list[str] = []

    for m in BLOCK_PATTERN.finditer(text):
        cmd = (m.group(1) or "").strip()
        if cmd:
            commands.append(cmd)

    if "!`" in text:
        for m in INLINE_PATTERN.finditer(text):
            cmd = (m.group(1) or "").strip()
            if cmd:
                commands.append(cmd)

    return commands


def has_shell_commands(text: str) -> bool:
    """Return *True* when *text* contains any embedded shell commands."""
    if BLOCK_PATTERN.search(text):
        return True
    if "!`" in text and INLINE_PATTERN.search(text):
        return True
    return False
