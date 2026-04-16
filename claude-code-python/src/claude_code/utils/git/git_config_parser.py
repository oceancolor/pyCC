"""Git config file parser. Ported from utils/git/gitConfigParser.ts"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Optional


def parse_config_string(config: str, section: str, subsection: Optional[str], key: str) -> Optional[str]:
    current_section = None
    current_subsection = None
    for line in config.splitlines():
        line = line.strip()
        if line.startswith('['):
            m = re.match(r'\[(\w[\w-]*)\s*(?:"([^"]*)")?\]', line)
            if m:
                current_section = m.group(1).lower()
                current_subsection = m.group(2)
            continue
        if '=' in line and not line.startswith('#') and not line.startswith(';'):
            k, _, v = line.partition('=')
            k = k.strip().lower()
            v = v.strip()
            if (current_section == section.lower() and
                    current_subsection == subsection and
                    k == key.lower()):
                return v
    return None


async def parse_git_config_value(git_dir: str, section: str,
                                   subsection: Optional[str], key: str) -> Optional[str]:
    try:
        content = Path(git_dir, "config").read_text()
        return parse_config_string(content, section, subsection, key)
    except Exception:
        return None
