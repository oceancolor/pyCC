"""LSP result formatters. Ported from LSPTool/formatters.ts"""
from __future__ import annotations
from typing import Any, List

def format_go_to_definition_result(locations: List[Any]) -> str:
    if not locations:
        return "No definition found."
    return "\n".join(f"{loc.get('uri', '')}:{loc.get('range', {})}" for loc in locations)

def format_find_references_result(locations: List[Any]) -> str:
    if not locations:
        return "No references found."
    return "\n".join(f"{loc.get('uri', '')}:{loc.get('range', {})}" for loc in locations)

def format_hover_result(hover: Any) -> str:
    if not hover:
        return "No hover information."
    contents = hover.get("contents", "")
    return str(contents)

def format_document_symbol_result(symbols: List[Any]) -> str:
    if not symbols:
        return "No symbols found."
    return "\n".join(f"{s.get('name', '')} ({s.get('kind', '')})" for s in symbols)

def format_workspace_symbol_result(symbols: List[Any]) -> str:
    return format_document_symbol_result(symbols)

def format_prepare_call_hierarchy_result(items: List[Any]) -> str:
    return "\n".join(f"{i.get('name', '')} in {i.get('uri', '')}" for i in items)

def format_incoming_calls_result(calls: List[Any]) -> str:
    return "\n".join(f"← {c.get('from', {}).get('name', '')}" for c in calls)

def format_outgoing_calls_result(calls: List[Any]) -> str:
    return "\n".join(f"→ {c.get('to', {}).get('name', '')}" for c in calls)
