"""Logout command package.

Ported from commands/logout/
"""
from __future__ import annotations

from .index import call, perform_logout

__all__ = ["call", "perform_logout", "NAME", "DESCRIPTION"]

# Command descriptor constants (mirrors TS index.ts)
NAME = "logout"
DESCRIPTION = "Sign out from your Anthropic account"
