"""
Plugin identifier - parses and normalizes plugin identifiers.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple


class PluginIdentifier:
    """Represents a parsed plugin identifier."""

    def __init__(
        self,
        raw: str,
        owner: Optional[str] = None,
        name: Optional[str] = None,
        version: Optional[str] = None,
    ) -> None:
        self.raw = raw
        self.owner = owner
        self.name = name
        self.version = version

    @property
    def full_name(self) -> str:
        if self.owner:
            return f"{self.owner}/{self.name}"
        return self.name or self.raw

    @property
    def id(self) -> str:
        """Plugin ID used for filesystem storage."""
        return re.sub(r"[^a-zA-Z0-9._-]", "_", self.full_name)


def parse_plugin_identifier(identifier: str) -> PluginIdentifier:
    """Parse a plugin identifier string."""
    # Format: [owner/]name[@version]
    version: Optional[str] = None
    if "@" in identifier:
        identifier, version = identifier.rsplit("@", 1)

    if "/" in identifier:
        owner, name = identifier.split("/", 1)
        return PluginIdentifier(raw=identifier, owner=owner, name=name, version=version)

    return PluginIdentifier(raw=identifier, owner=None, name=identifier, version=version)


def normalize_plugin_id(plugin_id: str) -> str:
    """Normalize a plugin identifier for storage."""
    parsed = parse_plugin_identifier(plugin_id)
    return parsed.id
