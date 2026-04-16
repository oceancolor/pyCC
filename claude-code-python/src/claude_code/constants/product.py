"""
Product URLs and remote session helpers
原始 TS: src/constants/product.ts
"""
from __future__ import annotations

import os
from typing import Optional

PRODUCT_URL = "https://claude.com/claude-code"

# Claude Code Remote session URLs
CLAUDE_AI_BASE_URL = "https://claude.ai"
CLAUDE_AI_STAGING_BASE_URL = "https://claude-ai.staging.ant.dev"
CLAUDE_AI_LOCAL_BASE_URL = "http://localhost:4000"


def is_remote_session_staging(
    session_id: Optional[str] = None,
    ingress_url: Optional[str] = None,
) -> bool:
    """Determine if we're in a staging environment for remote sessions."""
    return (
        (session_id is not None and "_staging_" in session_id)
        or (ingress_url is not None and "staging" in ingress_url)
    )


def is_remote_session_local(
    session_id: Optional[str] = None,
    ingress_url: Optional[str] = None,
) -> bool:
    """Determine if we're in a local-dev environment for remote sessions."""
    return (
        (session_id is not None and "_local_" in session_id)
        or (ingress_url is not None and "localhost" in ingress_url)
    )


def get_claude_ai_base_url(
    session_id: Optional[str] = None,
    ingress_url: Optional[str] = None,
) -> str:
    """Get the base URL for Claude AI based on environment."""
    if is_remote_session_local(session_id, ingress_url):
        return CLAUDE_AI_LOCAL_BASE_URL
    if is_remote_session_staging(session_id, ingress_url):
        return CLAUDE_AI_STAGING_BASE_URL
    return CLAUDE_AI_BASE_URL


def get_remote_session_url(
    session_id: str,
    ingress_url: Optional[str] = None,
) -> str:
    """
    Get the full session URL for a remote session.
    TS NOTE: toCompatSessionId shim translates cse_* → session_* for frontend compat.
    TODO: Port sessionIdCompat.ts if needed.
    """
    base_url = get_claude_ai_base_url(session_id, ingress_url)
    return f"{base_url}/code/{session_id}"
