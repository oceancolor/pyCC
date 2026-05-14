"""Compact command package."""
from __future__ import annotations
from .index import NAME, DESCRIPTION, ARGUMENT_HINT, SUPPORTS_NON_INTERACTIVE, is_enabled
from .compact import call

__all__ = ["NAME", "DESCRIPTION", "ARGUMENT_HINT", "SUPPORTS_NON_INTERACTIVE", "is_enabled", "call"]
