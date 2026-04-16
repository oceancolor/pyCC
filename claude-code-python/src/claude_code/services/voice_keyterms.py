"""Voice STT keyterms for Deepgram accuracy. Ported from services/voiceKeyterms.ts"""
from __future__ import annotations
import os
import re
from typing import Optional, Set

GLOBAL_KEYTERMS = [
    'MCP', 'symlink', 'grep', 'regex', 'localhost', 'codebase',
    'TypeScript', 'JSON', 'OAuth', 'webhook', 'gRPC', 'dotfiles',
    'subagent', 'worktree',
]
MAX_KEYTERMS = 50


def split_identifier(name: str) -> list:
    """Split camelCase, PascalCase, kebab-case, snake_case into words."""
    words = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
    parts = re.split(r'[-_./\s]+', words)
    return [p.strip() for p in parts if 2 < len(p.strip()) <= 20]


async def get_voice_keyterms(recent_files: Optional[Set[str]] = None) -> list:
    """Build keyterm list for voice STT from global list + project context."""
    terms: Set[str] = set(GLOBAL_KEYTERMS)

    # Add project root basename
    try:
        project_root = os.getcwd()
        name = os.path.basename(project_root)
        if 2 < len(name) <= 50:
            terms.add(name)
    except Exception:
        pass

    # Add git branch words
    try:
        import asyncio
        proc = await asyncio.create_subprocess_exec(
            'git', 'rev-parse', '--abbrev-ref', 'HEAD',
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2.0)
        branch = stdout.decode().strip()
        for word in split_identifier(branch):
            terms.add(word)
    except Exception:
        pass

    # Add recent file words
    if recent_files:
        for f in list(recent_files)[:20]:
            stem = os.path.splitext(os.path.basename(f))[0]
            for word in split_identifier(stem):
                terms.add(word)
                if len(terms) >= MAX_KEYTERMS:
                    break

    return list(terms)[:MAX_KEYTERMS]
