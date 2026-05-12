"""
Parse marketplace input - parses user input for marketplace plugin identifiers.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


class ParsedMarketplaceInput:
    def __init__(
        self,
        raw: str,
        marketplace_url: Optional[str] = None,
        plugin_id: Optional[str] = None,
        version: Optional[str] = None,
        is_url: bool = False,
    ) -> None:
        self.raw = raw
        self.marketplace_url = marketplace_url
        self.plugin_id = plugin_id
        self.version = version
        self.is_url = is_url


def parse_marketplace_input(input_str: str) -> ParsedMarketplaceInput:
    """
    Parse a user-provided marketplace input string.
    Can be:
    - A plugin ID: "author/plugin-name"
    - A plugin ID with version: "author/plugin-name@1.2.3"
    - A marketplace URL: "https://marketplace.example.com/plugin/..."
    """
    raw = input_str.strip()

    # Check if it looks like a URL
    if raw.startswith("http://") or raw.startswith("https://"):
        # Parse marketplace URL
        from urllib.parse import urlparse
        parsed = urlparse(raw)
        return ParsedMarketplaceInput(
            raw=raw,
            marketplace_url=f"{parsed.scheme}://{parsed.netloc}",
            is_url=True,
        )

    # Parse as plugin identifier
    from .plugin_identifier import parse_plugin_identifier
    parsed_id = parse_plugin_identifier(raw)
    return ParsedMarketplaceInput(
        raw=raw,
        plugin_id=parsed_id.full_name,
        version=parsed_id.version,
        is_url=False,
    )
