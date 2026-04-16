"""LSP server config. Ported from services/lsp/config.ts"""
from __future__ import annotations
import os

def get_lsp_enabled() -> bool:
    return os.environ.get("CLAUDE_CODE_LSP", "").lower() in ("1", "true")

def get_lsp_timeout_ms() -> int:
    return int(os.environ.get("CLAUDE_CODE_LSP_TIMEOUT_MS", "5000"))
