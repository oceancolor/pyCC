"""
SkillTool — invokes named skills (slash-command / SKILL.md workflows).
Ported from SkillTool/SkillTool.ts (1108 lines → core logic).

The TypeScript original is deeply integrated with Claude Code's React/Ink UI,
forked-agent execution, telemetry, and remote skill search features.  This
Python port captures the observable contract:

  * skill discovery  – scan project and home directories for SKILL.md files
  * skill listing    – list_available_skills() returns SkillInfo objects
  * skill search     – fuzzy substring match across name + description
  * skill execution  – read SKILL.md, return its content as the result
  * call() entry     – validate → find → execute pipeline

Non-portable pieces (forked sub-agent runner, Ink UI renderers, Growthbook
feature flags, AKI/GCS remote skill loading) are stubbed out gracefully.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants (mirrors SkillTool/constants.ts)
# ---------------------------------------------------------------------------

SKILL_TOOL_NAME = "Skill"
SKILL_TOOL_DESCRIPTION = (
    "Execute a named skill (a pre-defined workflow defined in a SKILL.md file). "
    "Skills can be discovered with list_available_skills() and invoked by name."
)

# Standard file that defines a skill inside a skill directory
SKILL_MD_FILENAME = "SKILL.md"

# Directories searched for skills (in priority order)
_DEFAULT_SKILL_SEARCH_PATHS: List[str] = [
    # Project-local skills are discovered dynamically from cwd
    # Global / home-level skills
    os.path.join(str(Path.home()), ".claude", "skills"),
    # OpenClaw-specific skill roots
    "/usr/local/lib/.nvm/versions/node/v22.17.0/lib/node_modules/openclaw/skills",
    "/usr/local/lib/.nvm/versions/node/v22.17.0/lib/node_modules/openclaw/dist/extensions/wecom-openclaw-plugin/skills",
    "/projects/.openclaw/skills",
]


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class SkillInfo:
    """Metadata about a discovered skill (mirrors PromptCommand core fields)."""
    name: str
    description: str
    skill_path: str          # path to the SKILL.md file
    skill_dir: str           # directory containing SKILL.md
    source: str = "local"    # 'local' | 'bundled' | 'plugin'
    loaded_from: str = "disk"

    # Optional overrides extracted from YAML front-matter
    model: Optional[str] = None
    allowed_tools: List[str] = field(default_factory=list)
    args: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Front-matter parsing (mirrors parseFrontmatter utility)
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_text).  Silently ignores parse errors."""
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return {}, content
    body = content[m.end():]
    fm: dict = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    return fm, body


# ---------------------------------------------------------------------------
# Skill discovery
# ---------------------------------------------------------------------------

def _extra_search_paths() -> List[str]:
    """Environment-variable override for extra skill directories."""
    env = os.environ.get("CLAUDE_SKILL_DIRS", "")
    if env:
        return [p.strip() for p in env.split(os.pathsep) if p.strip()]
    return []


def _project_skill_dirs(project_root: Optional[str] = None) -> List[str]:
    """Return .claude/skills paths relative to the project root (and cwd)."""
    candidates: List[str] = []
    cwd = os.getcwd()
    for base in {cwd, project_root} - {None}:  # type: ignore[operator]
        if base:
            candidates.append(os.path.join(base, ".claude", "skills"))
            candidates.append(os.path.join(base, "skills"))
    return candidates


def find_skills(
    project_root: Optional[str] = None,
    extra_dirs: Optional[List[str]] = None,
) -> List[SkillInfo]:
    """
    Discover all SKILL.md files from well-known directories.

    Mirrors the TypeScript loadSkillsDir / getCommands flow at a high level:
      1. Walk each candidate directory.
      2. Each sub-directory that contains a SKILL.md is one skill.
      3. Parse YAML front-matter for metadata (name, description, model, …).
      4. Deduplicate by name (first one wins).
    """
    search_dirs: List[str] = (
        _project_skill_dirs(project_root)
        + _DEFAULT_SKILL_SEARCH_PATHS
        + (extra_dirs or [])
        + _extra_search_paths()
    )

    seen_names: dict[str, bool] = {}
    skills: List[SkillInfo] = []

    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue
        try:
            entries = sorted(os.listdir(search_dir))
        except OSError:
            continue
        for entry in entries:
            entry_path = os.path.join(search_dir, entry)
            if not os.path.isdir(entry_path):
                continue
            skill_md = os.path.join(entry_path, SKILL_MD_FILENAME)
            if not os.path.isfile(skill_md):
                continue

            # Read content for front-matter extraction
            try:
                raw = Path(skill_md).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            fm, _body = _parse_frontmatter(raw)

            # Determine canonical name: front-matter 'name' → directory name
            skill_name = fm.get("name", entry).strip() or entry

            if skill_name in seen_names:
                continue
            seen_names[skill_name] = True

            description = fm.get("description", "").strip()

            # Allowed-tools list (comma-separated in front-matter)
            allowed_raw = fm.get("allowedTools", fm.get("allowed_tools", "")).strip()
            allowed_tools = (
                [t.strip() for t in allowed_raw.split(",") if t.strip()]
                if allowed_raw
                else []
            )

            skills.append(
                SkillInfo(
                    name=skill_name,
                    description=description,
                    skill_path=skill_md,
                    skill_dir=entry_path,
                    model=fm.get("model") or None,
                    allowed_tools=allowed_tools,
                )
            )

    return skills


def list_available_skills(
    project_root: Optional[str] = None,
    extra_dirs: Optional[List[str]] = None,
) -> List[SkillInfo]:
    """Public alias of find_skills (matches TypeScript API surface)."""
    return find_skills(project_root=project_root, extra_dirs=extra_dirs)


# ---------------------------------------------------------------------------
# Skill search
# ---------------------------------------------------------------------------

def search_skills(
    query: str,
    skills: Optional[List[SkillInfo]] = None,
    project_root: Optional[str] = None,
) -> List[SkillInfo]:
    """
    Fuzzy substring search over skill name + description.
    Returns skills ordered by relevance (name match first, then description).
    """
    if skills is None:
        skills = find_skills(project_root=project_root)

    query_lower = query.lower().strip()
    if not query_lower:
        return skills

    # Split into tokens so "pdf read" matches both "pdf" and "read" skills
    tokens = query_lower.split()

    name_matches: List[SkillInfo] = []
    desc_matches: List[SkillInfo] = []

    for skill in skills:
        name_l = skill.name.lower()
        desc_l = skill.description.lower()

        if any(tok in name_l for tok in tokens):
            name_matches.append(skill)
        elif any(tok in desc_l for tok in tokens):
            desc_matches.append(skill)

    return name_matches + desc_matches


# ---------------------------------------------------------------------------
# Skill execution
# ---------------------------------------------------------------------------

def _substitute_variables(content: str, skill_dir: str, args: str = "") -> str:
    """Expand ${CLAUDE_SKILL_DIR} and $ARGUMENTS placeholders (mirrors TS)."""
    content = content.replace("${CLAUDE_SKILL_DIR}", skill_dir)
    content = content.replace("$ARGUMENTS", args)
    return content


def execute_skill(
    name: str,
    args: str = "",
    project_root: Optional[str] = None,
    extra_dirs: Optional[List[str]] = None,
) -> dict:
    """
    Load and 'execute' a skill by name.

    In the full TypeScript implementation, execution spawns a forked sub-agent
    or injects the SKILL.md content directly into the conversation context.
    In this Python port we:
      1. Locate the SKILL.md file.
      2. Strip YAML front-matter.
      3. Apply $ARGUMENTS / ${CLAUDE_SKILL_DIR} substitution.
      4. Return the processed content so the caller can inject it.

    Returns a dict with keys:
      success     bool
      name        str  – canonical skill name
      content     str  – processed SKILL.md body
      skill_path  str  – path to the SKILL.md
      skill_dir   str  – directory containing SKILL.md
      error       str  – present only on failure
    """
    skills = find_skills(project_root=project_root, extra_dirs=extra_dirs)

    # Normalize: strip leading /
    normalized = name.lstrip("/").strip()
    skill = next((s for s in skills if s.name == normalized), None)

    if skill is None:
        available = [s.name for s in skills]
        return {
            "success": False,
            "name": normalized,
            "error": (
                f"Unknown skill: '{normalized}'. "
                f"Available skills: {available if available else '(none found)'}"
            ),
        }

    try:
        raw = Path(skill.skill_path).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {
            "success": False,
            "name": normalized,
            "error": f"Failed to read skill file: {exc}",
        }

    _fm, body = _parse_frontmatter(raw)
    processed = _substitute_variables(body, skill.skill_dir, args)

    # Prepend base-directory header (matches loadSkillsDir.ts behaviour)
    final_content = f"Base directory for this skill: {skill.skill_dir}\n\n{processed}"

    return {
        "success": True,
        "name": normalized,
        "content": final_content,
        "skill_path": skill.skill_path,
        "skill_dir": skill.skill_dir,
    }


# ---------------------------------------------------------------------------
# SkillTool class (Tool API)
# ---------------------------------------------------------------------------

class SkillTool:
    """
    Tool wrapper around skill discovery / execution.
    Implements the same JSON-schema call interface as other tools in this port.
    """

    name = SKILL_TOOL_NAME
    description = SKILL_TOOL_DESCRIPTION
    is_read_only = True

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "skill": {
                    "type": "string",
                    "description": (
                        "The skill name, e.g. 'commit', 'review-pr', 'pdf'. "
                        "Use list_available_skills to discover available skills."
                    ),
                },
                "args": {
                    "type": "string",
                    "description": "Optional arguments passed to the skill via $ARGUMENTS.",
                },
            },
            "required": ["skill"],
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_input(self, skill: str, args: str = "") -> dict:
        """
        Mirrors TS validateInput:
          – non-empty skill name
          – known skill (prompt-type command)
        Returns {'valid': bool, 'error': str|None, 'error_code': int}.
        """
        trimmed = skill.strip()
        if not trimmed:
            return {"valid": False, "error": f"Invalid skill format: '{skill}'", "error_code": 1}

        normalized = trimmed.lstrip("/")
        skills = find_skills()
        found = next((s for s in skills if s.name == normalized), None)
        if not found:
            return {
                "valid": False,
                "error": f"Unknown skill: '{normalized}'",
                "error_code": 2,
            }
        return {"valid": True, "error": None, "error_code": 0}

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def call(
        self,
        input_data: Dict[str, Any],
        context: Any = None,
    ) -> dict:
        """
        Execute a skill.

        Mirrors the TypeScript call() pipeline:
          1. Normalise skill name (strip leading /)
          2. Find the skill
          3. Load + process SKILL.md
          4. Return content (inline injection pattern)

        Returns the same shape as execute_skill() with an added 'status' field.
        """
        skill_name: str = input_data.get("skill", "")
        args: str = input_data.get("args", "") or ""

        if not skill_name.strip():
            return {
                "success": False,
                "name": skill_name,
                "error": "Skill name must not be empty.",
                "status": "error",
            }

        # Derive project_root from context if available
        project_root: Optional[str] = None
        if context is not None:
            project_root = getattr(context, "project_root", None)

        result = execute_skill(
            name=skill_name,
            args=args,
            project_root=project_root,
        )

        result["status"] = "inline" if result["success"] else "error"
        return result

    # ------------------------------------------------------------------
    # Convenience helpers (public API used by other modules)
    # ------------------------------------------------------------------

    def find_skills(
        self,
        project_root: Optional[str] = None,
        extra_dirs: Optional[List[str]] = None,
    ) -> List[SkillInfo]:
        """Discover all skills (delegates to module-level find_skills)."""
        return find_skills(project_root=project_root, extra_dirs=extra_dirs)

    def list_available_skills(
        self,
        project_root: Optional[str] = None,
        extra_dirs: Optional[List[str]] = None,
    ) -> List[SkillInfo]:
        """List all available skills."""
        return list_available_skills(project_root=project_root, extra_dirs=extra_dirs)

    def search_skills(
        self,
        query: str,
        project_root: Optional[str] = None,
    ) -> List[SkillInfo]:
        """Search skills by name/description."""
        return search_skills(query=query, project_root=project_root)

    def execute_skill(
        self,
        name: str,
        args: str = "",
        project_root: Optional[str] = None,
    ) -> dict:
        """Execute (load) a skill by name."""
        return execute_skill(name=name, args=args, project_root=project_root)

    # ------------------------------------------------------------------
    # Legacy interface (maintains backward compat with the 28-line stub)
    # ------------------------------------------------------------------

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema(),
        }
