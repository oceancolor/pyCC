"""
YOLO (auto mode) classifier for Claude Code.
Python port of utils/permissions/yoloClassifier.ts

Provides the security classifier that decides whether to allow or block
agent actions in auto/bypass-permissions mode. In the Python port,
the heavy API-calling logic is stubbed while the data structures,
transcript building, and parsing helpers are fully implemented.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple, Union


# ---------------------------------------------------------------------------
# Type definitions
# ---------------------------------------------------------------------------

@dataclass
class ClassifierUsage:
    """Token usage stats from a classifier API call."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class YoloClassifierResult:
    """
    Result from the YOLO/auto-mode classifier.

    should_block: True if the action should be blocked.
    reason: Human-readable reason for the decision.
    model: Model used for classification.
    thinking: Optional chain-of-thought reasoning (stage 2 / thinking).
    usage: Token usage statistics.
    duration_ms: Total duration in milliseconds.
    unavailable: True if the classifier was unavailable (API error, abort).
    transcript_too_long: True if the transcript exceeded the context window.
    error_dump_path: Path to the error dump file (if any).
    stage: Which stage produced the final decision ('fast' or 'thinking').
    """
    should_block: bool
    reason: str
    model: str = ""
    thinking: Optional[str] = None
    usage: Optional[ClassifierUsage] = None
    duration_ms: Optional[int] = None
    unavailable: bool = False
    transcript_too_long: bool = False
    error_dump_path: Optional[str] = None
    stage: Optional[Literal["fast", "thinking"]] = None
    prompt_lengths: Optional[Dict[str, int]] = None


@dataclass
class AutoModeRules:
    """
    Parsed settings.autoMode config.
    The three classifier prompt sections a user can customize.
    Required-field variant (empty lists when absent).
    """
    allow: List[str] = field(default_factory=list)
    soft_deny: List[str] = field(default_factory=list)
    environment: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Transcript types
# ---------------------------------------------------------------------------

TranscriptTextBlock = Dict[str, str]   # {"type": "text", "text": "..."}
TranscriptToolUseBlock = Dict[str, Any]  # {"type": "tool_use", "name": "...", "input": ...}
TranscriptBlock = Union[TranscriptTextBlock, TranscriptToolUseBlock]


@dataclass
class TranscriptEntry:
    """A single entry in the classifier transcript."""
    role: Literal["user", "assistant"]
    content: List[TranscriptBlock]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

YOLO_CLASSIFIER_TOOL_NAME = "classify_result"

YOLO_CLASSIFIER_TOOL_SCHEMA = {
    "type": "custom",
    "name": YOLO_CLASSIFIER_TOOL_NAME,
    "description": "Report the security classification result for the agent action",
    "input_schema": {
        "type": "object",
        "properties": {
            "thinking": {
                "type": "string",
                "description": "Brief step-by-step reasoning.",
            },
            "shouldBlock": {
                "type": "boolean",
                "description": "Whether the action should be blocked (true) or allowed (false)",
            },
            "reason": {
                "type": "string",
                "description": "Brief explanation of the classification decision",
            },
        },
        "required": ["thinking", "shouldBlock", "reason"],
    },
}

# Stage 1 suffix: nudges immediate decision
XML_S1_SUFFIX = "\nErr on the side of blocking. <block> immediately."

# Stage 2 suffix: asks for chain-of-thought
XML_S2_SUFFIX = (
    "\nReview the classification process and follow it carefully, making sure you deny actions "
    "that should be blocked. As a reminder, explicit (not suggestive or implicit) user "
    "confirmation is required to override blocks. Use <thinking> before responding with <block>."
)

# PowerShell deny guidance
POWERSHELL_DENY_GUIDANCE: Tuple[str, ...] = (
    "PowerShell Download-and-Execute: `iex (iwr ...)`, `Invoke-Expression (Invoke-WebRequest ...)`, "
    "`Invoke-Expression (New-Object Net.WebClient).DownloadString(...)`, and any pipeline feeding "
    "remote content into `Invoke-Expression`/`iex` fall under \"Code from External\" — same as `curl | bash`.",
    "PowerShell Irreversible Destruction: `Remove-Item -Recurse -Force`, `rm -r -fo`, `Clear-Content`, "
    "and `Set-Content` truncation of pre-existing files fall under \"Irreversible Local Destruction\" "
    "— same as `rm -rf` and `> file`.",
    "PowerShell Persistence: modifying `$PROFILE` (any of the four profile paths), "
    "`Register-ScheduledTask`, `New-Service`, writing to registry Run keys and WMI event subscriptions "
    "fall under \"Unauthorized Persistence\" — same as `.bashrc` edits and cron jobs.",
    "PowerShell Elevation: `Start-Process -Verb RunAs`, `-ExecutionPolicy Bypass`, and disabling "
    "AMSI/Defender fall under \"Security Weaken\".",
)


# ---------------------------------------------------------------------------
# Default auto-mode rules parsing
# ---------------------------------------------------------------------------

def get_default_external_auto_mode_rules() -> AutoModeRules:
    """
    Returns the default external auto-mode rules.
    In the Python port, returns empty lists (no bundled template file).
    """
    return AutoModeRules(allow=[], soft_deny=[], environment=[])


# ---------------------------------------------------------------------------
# Transcript building
# ---------------------------------------------------------------------------

def build_transcript_entries(messages: List[Dict[str, Any]]) -> List[TranscriptEntry]:
    """
    Build transcript entries from messages.
    Includes user text messages and assistant tool_use blocks.
    Mirrors the TS buildTranscriptEntries function.

    Message format expected:
    - {"type": "attachment", "attachment": {"type": "queued_command", "prompt": str|list}}
    - {"type": "user", "message": {"content": str|list}}
    - {"type": "assistant", "message": {"content": list}}
    """
    transcript: List[TranscriptEntry] = []

    for msg in messages:
        msg_type = msg.get("type")

        if msg_type == "attachment":
            attachment = msg.get("attachment", {})
            if attachment.get("type") == "queued_command":
                prompt = attachment.get("prompt")
                text: Optional[str] = None
                if isinstance(prompt, str):
                    text = prompt
                elif isinstance(prompt, list):
                    text_parts = [
                        block["text"]
                        for block in prompt
                        if isinstance(block, dict) and block.get("type") == "text"
                    ]
                    text = "\n".join(text_parts) if text_parts else None
                if text is not None:
                    transcript.append(TranscriptEntry(
                        role="user",
                        content=[{"type": "text", "text": text}],
                    ))

        elif msg_type == "user":
            content = msg.get("message", {}).get("content", "")
            text_blocks: List[TranscriptBlock] = []
            if isinstance(content, str):
                text_blocks.append({"type": "text", "text": content})
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_blocks.append({"type": "text", "text": block["text"]})
            if text_blocks:
                transcript.append(TranscriptEntry(role="user", content=text_blocks))

        elif msg_type == "assistant":
            blocks: List[TranscriptBlock] = []
            content = msg.get("message", {}).get("content", [])
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    blocks.append({
                        "type": "tool_use",
                        "name": block.get("name", ""),
                        "input": block.get("input", {}),
                    })
            if blocks:
                transcript.append(TranscriptEntry(role="assistant", content=blocks))

    return transcript


def _to_compact_block(
    block: TranscriptBlock,
    role: str,
    tool_lookup: Dict[str, Any],
    use_jsonl: bool = False,
) -> str:
    """
    Serialize a single transcript block as a compact string line.
    Tool use: {"Bash": "ls"} (jsonl) or "Bash ls" (text prefix).
    User text: {"user": "text"} (jsonl) or "User: text" (text prefix).
    """
    block_type = block.get("type") if isinstance(block, dict) else ""

    if block_type == "tool_use":
        name = block.get("name", "")
        tool = tool_lookup.get(name)
        if not tool:
            return ""
        inp = block.get("input", {}) or {}

        # Try to call toAutoClassifierInput if the tool has it
        encoded: Any
        try:
            encode_fn = getattr(tool, "to_auto_classifier_input", None)
            if encode_fn is not None:
                encoded = encode_fn(inp)
            else:
                encoded = inp
        except Exception:
            encoded = inp

        if encoded == "":
            return ""

        if use_jsonl:
            return json.dumps({name: encoded}, ensure_ascii=False) + "\n"
        s = encoded if isinstance(encoded, str) else json.dumps(encoded, ensure_ascii=False)
        return f"{name} {s}\n"

    if block_type == "text" and role == "user":
        text = block.get("text", "")
        if use_jsonl:
            return json.dumps({"user": text}, ensure_ascii=False) + "\n"
        return f"User: {text}\n"

    return ""


def _to_compact(
    entry: TranscriptEntry,
    tool_lookup: Dict[str, Any],
    use_jsonl: bool = False,
) -> str:
    return "".join(
        _to_compact_block(b, entry.role, tool_lookup, use_jsonl)
        for b in entry.content
    )


def build_transcript_for_classifier(
    messages: List[Dict[str, Any]],
    tools: List[Any],
    use_jsonl: bool = False,
) -> str:
    """
    Build a compact transcript string for the classifier.
    Mirrors the TS buildTranscriptForClassifier function.

    tools: list of tool objects (must have a 'name' attribute)
    use_jsonl: whether to use JSONL format ({"Bash":"ls"}) vs text prefix ("Bash ls")
    """
    lookup: Dict[str, Any] = {}
    for tool in tools:
        name = getattr(tool, "name", None)
        if name:
            lookup[name] = tool
        for alias in getattr(tool, "aliases", []):
            lookup[alias] = tool

    entries = build_transcript_entries(messages)
    return "".join(_to_compact(e, lookup, use_jsonl) for e in entries)


# ---------------------------------------------------------------------------
# XML parsing helpers
# ---------------------------------------------------------------------------

def _strip_thinking(text: str) -> str:
    """
    Strip <thinking>...</thinking> blocks to avoid matching tags inside them.
    Mirrors the TS stripThinking function.
    """
    text = re.sub(r"<thinking>[\s\S]*?</thinking>", "", text)
    text = re.sub(r"<thinking>[\s\S]*$", "", text)
    return text


def parse_xml_block(text: str) -> Optional[bool]:
    """
    Parse XML block response: <block>yes/no</block>.
    Returns True for "yes" (should block), False for "no", None if unparseable.
    Mirrors the TS parseXmlBlock function.
    """
    stripped = _strip_thinking(text)
    matches = list(re.finditer(r"<block>(yes|no)\b(</block>)?", stripped, re.IGNORECASE))
    if not matches:
        return None
    first = matches[0].group(1).lower()
    return first == "yes"


def parse_xml_reason(text: str) -> Optional[str]:
    """
    Parse XML reason: <reason>...</reason>.
    Strips thinking content first.
    Mirrors the TS parseXmlReason function.
    """
    stripped = _strip_thinking(text)
    matches = list(re.finditer(r"<reason>([\s\S]*?)</reason>", stripped))
    if not matches:
        return None
    return matches[0].group(1).strip()


def parse_xml_thinking(text: str) -> Optional[str]:
    """
    Parse XML thinking content: <thinking>...</thinking>.
    Mirrors the TS parseXmlThinking function.
    """
    match = re.search(r"<thinking>([\s\S]*?)</thinking>", text)
    return match.group(1).strip() if match else None


# ---------------------------------------------------------------------------
# Tool-use / JSON classifier response parsing
# ---------------------------------------------------------------------------

def parse_classifier_response_dict(response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Parse a classifier response dict (from tool_use block).
    Expected keys: thinking, shouldBlock, reason.
    Returns None if the response is malformed.
    """
    should_block = response.get("shouldBlock")
    reason = response.get("reason", "")
    thinking = response.get("thinking")

    if not isinstance(should_block, bool):
        return None

    return {
        "shouldBlock": should_block,
        "reason": reason,
        "thinking": thinking,
    }


# ---------------------------------------------------------------------------
# System prompt building (simplified)
# ---------------------------------------------------------------------------

def build_default_external_system_prompt() -> str:
    """
    Returns the full external classifier system prompt with default rules.
    In the Python port, returns a minimal stub (no bundled template files).
    """
    return (
        "You are a security classifier for Claude Code auto mode.\n"
        "Evaluate the agent's actions and determine if they should be blocked.\n\n"
        "Use the classify_result tool to report your classification.\n"
    )


def build_yolo_system_prompt(
    context: Optional[Dict[str, Any]] = None,
    auto_mode_config: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build the system prompt for the auto mode classifier.
    Assembles the base prompt with permission rules from settings.

    In the Python port, returns a simplified version that incorporates
    allow/deny rules if provided.
    """
    base = build_default_external_system_prompt()

    allow_rules: List[str] = []
    deny_rules: List[str] = []
    environment_rules: List[str] = []

    if auto_mode_config:
        allow_rules = auto_mode_config.get("allow", []) or []
        deny_rules = auto_mode_config.get("soft_deny", []) or []
        environment_rules = auto_mode_config.get("environment", []) or []

    sections: List[str] = [base]

    if allow_rules:
        bullet_allow = "\n".join(f"- {r}" for r in allow_rules)
        sections.append(f"## Always Allow\n{bullet_allow}")

    if deny_rules:
        bullet_deny = "\n".join(f"- {r}" for r in deny_rules)
        sections.append(f"## Always Block\n{bullet_deny}")

    if environment_rules:
        bullet_env = "\n".join(f"- {r}" for r in environment_rules)
        sections.append(f"## Environment\n{bullet_env}")

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Classifier result → YoloClassifierResult helpers
# ---------------------------------------------------------------------------

def make_blocked_result(
    reason: str,
    model: str = "",
    unavailable: bool = False,
    transcript_too_long: bool = False,
    error_dump_path: Optional[str] = None,
) -> YoloClassifierResult:
    """Create a 'block' classifier result."""
    return YoloClassifierResult(
        should_block=True,
        reason=reason,
        model=model,
        unavailable=unavailable,
        transcript_too_long=transcript_too_long,
        error_dump_path=error_dump_path,
    )


def make_allowed_result(
    reason: str = "Allowed",
    model: str = "",
    stage: Optional[Literal["fast", "thinking"]] = None,
    thinking: Optional[str] = None,
    usage: Optional[ClassifierUsage] = None,
    duration_ms: Optional[int] = None,
) -> YoloClassifierResult:
    """Create an 'allow' classifier result."""
    return YoloClassifierResult(
        should_block=False,
        reason=reason,
        model=model,
        stage=stage,
        thinking=thinking,
        usage=usage,
        duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# Classifier mode / config helpers
# ---------------------------------------------------------------------------

def get_classifier_model() -> str:
    """
    Get the model to use for the YOLO classifier.
    Checks CLAUDE_CODE_AUTO_MODE_MODEL env var, then falls back to a default.
    """
    env_model = os.environ.get("CLAUDE_CODE_AUTO_MODE_MODEL", "")
    if env_model:
        return env_model
    # Default model
    return os.environ.get("CLAUDE_CODE_MODEL", "claude-opus-4-5")


def is_two_stage_classifier_enabled() -> bool:
    """
    Check if the XML two-stage classifier is enabled.
    Checks CLAUDE_CODE_TWO_STAGE_CLASSIFIER env var.
    """
    env = os.environ.get("CLAUDE_CODE_TWO_STAGE_CLASSIFIER", "")
    return env.lower() in ("1", "true", "yes", "fast", "thinking")


def get_two_stage_mode() -> Optional[Literal["both", "fast", "thinking"]]:
    """
    Get the two-stage classifier mode from environment.
    Returns None if not configured (tool_use classifier).
    """
    env = os.environ.get("CLAUDE_CODE_TWO_STAGE_CLASSIFIER", "")
    if env.lower() == "fast":
        return "fast"
    if env.lower() == "thinking":
        return "thinking"
    if env.lower() in ("1", "true", "yes"):
        return "both"
    return None


def is_jsonl_transcript_enabled() -> bool:
    """Check if JSONL transcript format is enabled."""
    env = os.environ.get("CLAUDE_CODE_JSONL_TRANSCRIPT", "")
    return env.lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Auto mode error dump path
# ---------------------------------------------------------------------------

def get_auto_mode_classifier_error_dump_path(session_id: Optional[str] = None) -> str:
    """
    Returns the path for auto-mode classifier error dumps.
    Python equivalent of getAutoModeClassifierErrorDumpPath.
    """
    from claude_code.utils.permissions.filesystem import get_claude_temp_dir

    sid = session_id or os.environ.get("CLAUDE_SESSION_ID", "default")
    return os.path.join(
        get_claude_temp_dir().rstrip(os.sep),
        "auto-mode-classifier-errors",
        f"{sid}.txt",
    )


# ---------------------------------------------------------------------------
# Classifier output format: replace tool_use instruction with XML format
# ---------------------------------------------------------------------------

def replace_output_format_with_xml(system_prompt: str) -> str:
    """
    Replace the tool_use output format instruction with XML format.
    Mirrors the TS replaceOutputFormatWithXml function.
    """
    tool_use_line = "Use the classify_result tool to report your classification."
    xml_format = "\n".join([
        "## Output Format",
        "",
        "If the action should be blocked:",
        "<block>yes</block><reason>one short sentence</reason>",
        "",
        "If the action should be allowed:",
        "<block>no</block>",
        "",
        "Do NOT include a <reason> tag when the action is allowed.",
        "Your ENTIRE response MUST begin with <block>. Do NOT output any analysis, "
        "reasoning, or commentary before <block>. No \"Looking at...\" or similar preamble.",
    ])
    return system_prompt.replace(tool_use_line, xml_format)


# ---------------------------------------------------------------------------
# Combine usage stats
# ---------------------------------------------------------------------------

def combine_usage(a: ClassifierUsage, b: ClassifierUsage) -> ClassifierUsage:
    """Combine usage from two classifier stages."""
    return ClassifierUsage(
        input_tokens=a.input_tokens + b.input_tokens,
        output_tokens=a.output_tokens + b.output_tokens,
        cache_read_input_tokens=a.cache_read_input_tokens + b.cache_read_input_tokens,
        cache_creation_input_tokens=a.cache_creation_input_tokens + b.cache_creation_input_tokens,
    )


# ---------------------------------------------------------------------------
# CLAUDE.md message building
# ---------------------------------------------------------------------------

def build_claude_md_message(claude_md_content: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Build the CLAUDE.md prefix message for the classifier.
    Returns None when claude_md_content is None or empty.
    Mirrors the TS buildClaudeMdMessage function.
    """
    if not claude_md_content:
        return None
    return {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": (
                    "The following is the user's CLAUDE.md configuration. These are "
                    "instructions the user provided to the agent and should be treated "
                    "as part of the user's intent when evaluating actions.\n\n"
                    f"<user_claude_md>\n{claude_md_content}\n</user_claude_md>"
                ),
            }
        ],
    }


# ---------------------------------------------------------------------------
# Main classify function (stub for API-free environments)
# ---------------------------------------------------------------------------

def classify_yolo_action(
    action_description: str,
    context: Optional[Dict[str, Any]] = None,
    auto_mode_config: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
) -> YoloClassifierResult:
    """
    Classify whether a YOLO (auto mode) action should be blocked or allowed.

    This is a Python-native stub that performs classification based on
    heuristics (no API call). Use this for environments where the classifier
    API is unavailable or for testing.

    For production use with a live Claude API, use classify_yolo_action_api().
    """
    # In Python port, the classifier is unavailable by default
    # (requires live API connection). Return a safe default.
    return YoloClassifierResult(
        should_block=True,
        reason="Classifier unavailable - blocking for safety",
        model=model or get_classifier_model(),
        unavailable=True,
    )


async def classify_yolo_action_api(
    action_description: str,
    transcript_messages: List[Dict[str, Any]],
    tools: List[Any],
    context: Optional[Dict[str, Any]] = None,
    auto_mode_config: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
    signal: Any = None,
) -> YoloClassifierResult:
    """
    Async version of the YOLO classifier using the Claude API.
    Mirrors the TS classifyYoloAction function structure.

    This function builds the transcript, system prompt, and user prompt,
    then calls the classifier API.

    Note: Actual API integration requires the anthropic Python SDK.
    """
    effective_model = model or get_classifier_model()
    system_prompt = build_yolo_system_prompt(context, auto_mode_config)
    transcript = build_transcript_for_classifier(
        transcript_messages, tools, use_jsonl=is_jsonl_transcript_enabled()
    )

    # In the Python port, this stub returns unavailable
    # (no live API connection configured here)
    return YoloClassifierResult(
        should_block=True,
        reason="Classifier API not configured - blocking for safety",
        model=effective_model,
        unavailable=True,
    )
