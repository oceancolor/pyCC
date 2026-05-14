"""DXT manifest validation helpers. Ported from utils/dxt/helpers.ts"""

from __future__ import annotations

import json
import re
from typing import Any, Optional


def _sanitize_identifier(text: str) -> str:
    """Sanitise a string for use as part of an extension identifier.

    Rules:
    - Lower-case
    - Spaces → hyphens
    - Remove characters that are not alphanumeric, hyphen, underscore, or dot
    - Collapse multiple consecutive hyphens
    - Strip leading/trailing hyphens
    """
    s = text.lower()
    s = re.sub(r'\s+', '-', s)
    s = re.sub(r'[^a-z0-9\-_.]', '', s)
    s = re.sub(r'-+', '-', s)
    s = s.strip('-')
    return s


def validate_manifest(manifest_json: Any) -> dict:
    """Parse and validate a DXT/MCPB manifest from a raw JSON object.

    Performs lightweight schema validation in Python (the TypeScript version
    uses Zod against ``@anthropic-ai/mcpb``).  Required fields:
    - ``name`` (str)
    - ``version`` (str)
    - ``author`` (dict with at least ``name``)

    Args:
        manifest_json: Parsed JSON value (should be a dict).

    Returns:
        The validated manifest dict.

    Raises:
        ValueError: If validation fails.
    """
    if not isinstance(manifest_json, dict):
        raise ValueError("Invalid manifest: manifest must be a JSON object")

    errors = []

    if not manifest_json.get("name"):
        errors.append("name: required")
    elif not isinstance(manifest_json["name"], str):
        errors.append("name: must be a string")

    if not manifest_json.get("version"):
        errors.append("version: required")
    elif not isinstance(manifest_json["version"], str):
        errors.append("version: must be a string")

    author = manifest_json.get("author")
    if not author:
        errors.append("author: required")
    elif not isinstance(author, dict):
        errors.append("author: must be an object")
    elif not author.get("name"):
        errors.append("author.name: required")

    if errors:
        raise ValueError(f"Invalid manifest: {'; '.join(errors)}")

    return manifest_json


async def validate_manifest_async(manifest_json: Any) -> dict:
    """Async wrapper for :func:`validate_manifest` (for API compatibility)."""
    return validate_manifest(manifest_json)


async def parse_and_validate_manifest_from_text(manifest_text: str) -> dict:
    """Parse and validate a DXT manifest from raw JSON text.

    Args:
        manifest_text: The raw JSON string.

    Returns:
        The validated manifest dict.

    Raises:
        ValueError: If the JSON is invalid or the manifest fails validation.
    """
    try:
        manifest_json = json.loads(manifest_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in manifest.json: {exc}") from exc

    return validate_manifest(manifest_json)


async def parse_and_validate_manifest_from_bytes(manifest_data: bytes) -> dict:
    """Parse and validate a DXT manifest from raw bytes.

    Args:
        manifest_data: The raw UTF-8 encoded manifest JSON.

    Returns:
        The validated manifest dict.
    """
    return await parse_and_validate_manifest_from_text(manifest_data.decode("utf-8"))


def generate_extension_id(
    manifest: dict,
    prefix: Optional[str] = None,
) -> str:
    """Generate an extension ID from the manifest's author and name.

    Uses the same algorithm as the directory backend for consistency.

    Args:
        manifest: A validated manifest dict with at least ``name`` and ``author.name``.
        prefix: Optional prefix such as ``'local.unpacked'`` or ``'local.dxt'``.

    Returns:
        An extension ID string like ``"my-author.my-extension"`` or
        ``"local.dxt.my-author.my-extension"``.
    """
    author_name = manifest.get("author", {}).get("name", "unknown")
    extension_name = manifest.get("name", "unknown")

    sanitized_author = _sanitize_identifier(author_name)
    sanitized_name = _sanitize_identifier(extension_name)

    base = f"{sanitized_author}.{sanitized_name}"
    return f"{prefix}.{base}" if prefix else base
