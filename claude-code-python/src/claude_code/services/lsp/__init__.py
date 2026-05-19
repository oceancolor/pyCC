"""LSP (Language Server Protocol) service.

Manages connections to LSP servers, routes notifications to passive
diagnostic handlers, and provides utilities for formatting diagnostics
as tool-result attachments.

Ported from: src/services/lsp/ (TypeScript)

Usage::

    from claude_code.services.lsp import (
        LSPClient,
        LSPManager,
        get_all_lsp_servers,
        register_lsp_notification_handlers,
        format_diagnostics_for_attachment,
        map_lsp_severity,
    )
"""
from __future__ import annotations

from claude_code.services.lsp.lsp_client import LSPClient
from claude_code.services.lsp.manager import LSPManager
from claude_code.services.lsp.config import get_all_lsp_servers
from claude_code.services.lsp.passive_feedback import (
    register_lsp_notification_handlers,
    format_diagnostics_for_attachment,
    map_lsp_severity,
)

__all__ = [
    "LSPClient",
    "LSPManager",
    "get_all_lsp_servers",
    "register_lsp_notification_handlers",
    "format_diagnostics_for_attachment",
    "map_lsp_severity",
]
