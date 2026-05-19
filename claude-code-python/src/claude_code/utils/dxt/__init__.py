"""DXT (Desktop Extension) utilities.

Provides manifest validation, extension ID generation, and zip-extraction
helpers for the DXT plugin/extension system used to distribute Claude Code
extensions as self-contained ``.dxt`` archives.

Ported from: src/utils/dxt/ (TypeScript)

Usage::

    from claude_code.utils.dxt import validate_manifest, generate_extension_id
"""
from __future__ import annotations

from claude_code.utils.dxt.helpers import (
    generate_extension_id,
    validate_manifest,
)

__all__ = [
    "validate_manifest",
    "generate_extension_id",
]
