"""
Semantic boolean coercion. Ported from semanticBoolean.ts
(Also re-exported from semantic_number.py — kept separate for import compat)
"""
from claude_code.utils.semantic_number import parse_semantic_boolean, semantic_boolean

__all__ = ["parse_semantic_boolean", "semantic_boolean"]
