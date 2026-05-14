"""PowerShell command prefix extraction. Ported from utils/powershell/staticPrefix.ts"""

from __future__ import annotations

import re
from typing import List, Optional

from .dangerous_cmdlets import NEVER_SUGGEST


async def get_command_prefix_static(
    command: str,
) -> Optional[dict]:
    """Extract a static prefix suggestion for a PowerShell command.

    Used to pre-populate the "don't ask again for: ___" input in the
    permission dialog.

    Args:
        command: The raw PowerShell command string.

    Returns:
        ``{"commandPrefix": prefix_or_None}`` or None if parsing fails.
    """
    try:
        from .parser import parse_powershell_command, get_all_commands

        parsed = await parse_powershell_command(command)
        if not parsed.get("valid"):
            return None

        cmds = get_all_commands(parsed)
        first_cmd = next(
            (c for c in cmds if c.get("elementType") == "CommandAst"),
            None,
        )
        if not first_cmd:
            return {"commandPrefix": None}

        prefix = await _extract_prefix_from_element(first_cmd)
        return {"commandPrefix": prefix}
    except ImportError:
        # parser module not yet available – fall back to simple heuristic
        prefix = _heuristic_prefix(command)
        return {"commandPrefix": prefix}
    except Exception:
        return None


async def get_compound_command_prefixes_static(
    command: str,
) -> List[str]:
    """Extract prefix suggestions for all subcommands in a compound command.

    Args:
        command: The raw PowerShell command string.

    Returns:
        A deduplicated list of safe prefix strings.
    """
    try:
        from .parser import parse_powershell_command, get_all_commands

        parsed = await parse_powershell_command(command)
        if not parsed.get("valid"):
            return []

        cmds = [c for c in get_all_commands(parsed) if c.get("elementType") == "CommandAst"]
        if len(cmds) <= 1:
            prefix = await _extract_prefix_from_element(cmds[0]) if cmds else None
            return [prefix] if prefix else []

        prefixes: List[str] = []
        for cmd in cmds:
            p = await _extract_prefix_from_element(cmd)
            if p:
                prefixes.append(p)

        return _collapse_prefixes(prefixes)
    except ImportError:
        # Fallback: split on ; && || |
        sub_cmds = re.split(r'(?:;|&&|\|\||(?<!\|)\|(?!\|))', command)
        result: List[str] = []
        for sub in sub_cmds:
            sub = sub.strip()
            if sub:
                p = _heuristic_prefix(sub)
                if p:
                    result.append(p)
        return _collapse_prefixes(result)
    except Exception:
        return []


async def _extract_prefix_from_element(cmd: dict) -> Optional[str]:
    """Extract a safe prefix from a single parsed command element dict."""
    name_type = cmd.get("nameType", "")
    name = cmd.get("name", "")

    if name_type == "application":
        return None
    if not name:
        return None
    if name.lower() in NEVER_SUGGEST:
        return None

    if name_type == "cmdlet":
        return name

    # External command
    args = cmd.get("args", []) or []
    element_types = cmd.get("elementTypes", []) or []

    if element_types and element_types[0] != "StringConstant":
        return None

    for i, t in enumerate(element_types[1:], 1):
        if t not in ("StringConstant", "Parameter"):
            return None

    # Simple prefix: cmd name + first positional non-flag arg (if any)
    positional = [a for a in args if not a.startswith("-")]
    if positional:
        return f"{name} {positional[0]}"
    return name


def _heuristic_prefix(command: str) -> Optional[str]:
    """Simple heuristic prefix extraction when the parser is unavailable.

    Splits on whitespace and takes the first one or two tokens (skipping
    flags). Returns None for commands in NEVER_SUGGEST.
    """
    tokens = command.strip().split()
    if not tokens:
        return None
    cmd_name = tokens[0].lstrip("&").strip()
    if not cmd_name or cmd_name.lower() in NEVER_SUGGEST:
        return None

    # Look for the first non-flag argument as a subcommand
    for token in tokens[1:]:
        if not token.startswith("-"):
            return f"{cmd_name} {token}"
    return cmd_name


def _word_aligned_lcp(strings: List[str]) -> str:
    """Word-aligned longest common prefix (case-insensitive comparison).

    Examples:
    - ["npm run test", "npm run lint"] → "npm run"
    - ["Git status", "git log"] → "Git"
    """
    if not strings:
        return ""
    if len(strings) == 1:
        return strings[0]

    first_words = strings[0].split(" ")
    common = len(first_words)

    for s in strings[1:]:
        words = s.split(" ")
        match = 0
        while match < common and match < len(words) and words[match].lower() == first_words[match].lower():
            match += 1
        common = match
        if common == 0:
            break

    return " ".join(first_words[:common])


def _collapse_prefixes(prefixes: List[str]) -> List[str]:
    """Group by root command and collapse via word-aligned LCP."""
    if not prefixes:
        return []
    if len(prefixes) == 1:
        return prefixes

    groups: dict = {}
    for prefix in prefixes:
        root = prefix.split(" ")[0].lower()
        groups.setdefault(root, []).append(prefix)

    collapsed: List[str] = []
    for root_lower, group in groups.items():
        lcp = _word_aligned_lcp(group)
        if lcp:
            collapsed.append(lcp)

    return collapsed
