"""DXT (Desktop Extension) utilities sub-package. Ported from utils/dxt/.

Provides manifest validation, extension ID generation, and zip extraction
helpers for the DXT plugin/extension system.
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
