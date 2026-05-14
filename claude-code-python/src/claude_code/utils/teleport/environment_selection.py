"""Teleport environment selection utilities. Ported from utils/teleport/environmentSelection.ts"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class EnvironmentResource:
    """A remote execution environment available via Teleport."""

    environment_id: str
    name: str
    kind: str  # e.g. 'remote', 'bridge'
    description: Optional[str] = None
    region: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class EnvironmentSelectionInfo:
    """Information about available environments and the currently selected one."""

    available_environments: List[EnvironmentResource]
    selected_environment: Optional[EnvironmentResource]
    selected_environment_source: Optional[str]  # SettingSource or None


async def fetch_environments() -> List[EnvironmentResource]:
    """Fetch the list of available Teleport environments from the API.

    Returns an empty list if the API is unavailable or the user is not
    authenticated.
    """
    try:
        from claude_code.utils.teleport.api import get_with_retry
    except ImportError:
        return []

    try:
        from claude_code.utils.auth import auth as _auth

        tokens = await _auth.get_claude_ai_oauth_tokens()
        if not tokens:
            return []
        bearer = tokens.get("access_token", "")
    except Exception:
        return []

    try:
        import os

        base_url = os.environ.get(
            "CLAUDE_API_BASE_URL", "https://api.claude.ai"
        )
        data = await get_with_retry(
            f"{base_url}/api/remote_environments",
            headers={"Authorization": f"Bearer {bearer}"},
        )
        envs: List[EnvironmentResource] = []
        for item in data.get("environments", []):
            envs.append(
                EnvironmentResource(
                    environment_id=item["environment_id"],
                    name=item.get("name", item["environment_id"]),
                    kind=item.get("kind", "remote"),
                    description=item.get("description"),
                    region=item.get("region"),
                    metadata=item.get("metadata", {}),
                )
            )
        return envs
    except Exception:
        return []


async def get_environment_selection_info() -> EnvironmentSelectionInfo:
    """Get information about available environments and the currently selected one.

    Returns:
        An :class:`EnvironmentSelectionInfo` with the full list, the resolved
        selected environment, and where that selection came from.
    """
    environments = await fetch_environments()

    if not environments:
        return EnvironmentSelectionInfo(
            available_environments=[],
            selected_environment=None,
            selected_environment_source=None,
        )

    # Get the configured default environment ID from settings
    default_environment_id: Optional[str] = None
    selected_source: Optional[str] = None

    try:
        from claude_code.utils.settings import get_settings

        settings = get_settings()
        remote = getattr(settings, "remote", None) or {}
        if isinstance(remote, dict):
            default_environment_id = remote.get("defaultEnvironmentId")
        elif hasattr(remote, "default_environment_id"):
            default_environment_id = remote.default_environment_id
    except Exception:
        pass

    # Default selection: first non-bridge environment
    selected = next(
        (e for e in environments if e.kind != "bridge"), environments[0]
    )

    if default_environment_id:
        match = next(
            (e for e in environments if e.environment_id == default_environment_id),
            None,
        )
        if match:
            selected = match
            selected_source = "settings"

    return EnvironmentSelectionInfo(
        available_environments=environments,
        selected_environment=selected,
        selected_environment_source=selected_source,
    )
