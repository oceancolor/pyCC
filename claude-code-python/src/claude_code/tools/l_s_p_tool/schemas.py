"""LSP tool input schemas. Ported from LSPTool/schemas.ts"""
from __future__ import annotations

LSP_OPERATIONS = [
    "go_to_definition", "find_references", "hover",
    "document_symbols", "workspace_symbols",
    "prepare_call_hierarchy", "call_hierarchy_incoming",
    "call_hierarchy_outgoing",
]

def lsp_tool_input_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "operation": {"type": "string", "enum": LSP_OPERATIONS},
            "file_path": {"type": "string"},
            "line": {"type": "integer"},
            "character": {"type": "integer"},
            "symbol": {"type": "string"},
        },
        "required": ["operation"],
    }
