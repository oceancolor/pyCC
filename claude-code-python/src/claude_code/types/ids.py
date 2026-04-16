"""
Branded ID types
原始 TS: src/types/ids.ts

TypeScript branded string types → Python NewType
"""
from __future__ import annotations

import re
from typing import NewType, Optional

# ---------------------------------------------------------------------------
# Branded string types  (TS: string & { __brand: 'X' })
# In Python we use NewType — same runtime type (str) but distinct at type check
# ---------------------------------------------------------------------------

SessionId = NewType("SessionId", str)
AgentId = NewType("AgentId", str)

_AGENT_ID_PATTERN = re.compile(r"^a(?:.+-)?[0-9a-f]{16}$")


def as_session_id(id_: str) -> SessionId:
    """Cast a raw string to SessionId. Use sparingly."""
    return SessionId(id_)


def as_agent_id(id_: str) -> AgentId:
    """Cast a raw string to AgentId. Use sparingly."""
    return AgentId(id_)


def to_agent_id(s: str) -> Optional[AgentId]:
    """
    Validate and brand a string as AgentId.
    Returns None if the string does not match the expected format.
    Format: `a` + optional `<label>-` + 16 hex chars.
    """
    if _AGENT_ID_PATTERN.match(s):
        return AgentId(s)
    return None
