"""DXT manifest validation. Ported from utils/dxt/helpers.ts (stub - mcpb not available)."""
from __future__ import annotations
import json
from typing import Any

async def validate_manifest(manifest_json: Any) -> dict:
    if not isinstance(manifest_json, dict):
        raise ValueError("Manifest must be a JSON object")
    return manifest_json
