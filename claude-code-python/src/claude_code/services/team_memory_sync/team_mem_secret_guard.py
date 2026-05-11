"""
team_memory_sync/team_mem_secret_guard.py — Team memory secret guard.
Ported from services/teamMemorySync/teamMemSecretGuard.ts (44 lines).

Check if a file write/edit to a team memory path contains secrets.
Returns an error message if secrets are detected, or None if safe.
"""
from __future__ import annotations

from typing import Optional


def check_team_mem_secrets(
    file_path: str,
    content: str,
) -> Optional[str]:
    """
    Check if a file write/edit to a team memory path contains secrets.
    Returns an error message if secrets are detected, or None if safe.

    This is called from FileWriteTool and FileEditTool validate_input to
    prevent the model from writing secrets into team memory files, which
    would be synced to all repository collaborators.

    Callers can import and call this unconditionally — the internal
    TEAMMEM feature guard keeps it inert when the feature is off.
    secretScanner assembles sensitive prefixes at runtime (ANT_KEY_PFX).
    """
    # Check TEAMMEM feature gate
    try:
        from claude_code.utils.feature_flags import is_feature_enabled
        if not is_feature_enabled("TEAMMEM"):
            return None
    except (ImportError, Exception):
        # If we can't check the feature flag, default to safe (return None)
        return None

    try:
        from claude_code.memdir.team_mem_paths import is_team_mem_path
    except ImportError:
        return None

    if not is_team_mem_path(file_path):
        return None

    from claude_code.services.team_memory_sync.secret_scanner import scan_for_secrets

    matches = scan_for_secrets(content)
    if not matches:
        return None

    labels = ", ".join(m.label for m in matches)
    return (
        f"Content contains potential secrets ({labels}) and cannot be written to team memory. "
        "Team memory is shared with all repository collaborators. "
        "Remove the sensitive content and try again."
    )
