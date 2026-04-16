"""LSP diagnostic registry. Ported from services/lsp/LSPDiagnosticRegistry.ts (386L → core)."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
import threading


class LSPDiagnosticRegistry:
    """Tracks LSP diagnostics (errors/warnings) per file."""

    def __init__(self):
        self._diagnostics: Dict[str, List[dict]] = {}
        self._lock = threading.Lock()

    def set_diagnostics(self, uri: str, diagnostics: List[dict]) -> None:
        with self._lock:
            self._diagnostics[uri] = list(diagnostics)

    def get_diagnostics(self, uri: str) -> List[dict]:
        with self._lock:
            return list(self._diagnostics.get(uri, []))

    def get_all_diagnostics(self) -> Dict[str, List[dict]]:
        with self._lock:
            return dict(self._diagnostics)

    def clear_diagnostics(self, uri: str) -> None:
        with self._lock:
            self._diagnostics.pop(uri, None)

    def clear_all(self) -> None:
        with self._lock:
            self._diagnostics.clear()

    def get_errors(self, uri: Optional[str] = None) -> List[dict]:
        """Return diagnostics with severity=1 (Error)."""
        if uri:
            return [d for d in self.get_diagnostics(uri) if d.get("severity") == 1]
        errors = []
        for diags in self.get_all_diagnostics().values():
            errors.extend(d for d in diags if d.get("severity") == 1)
        return errors

    def format_diagnostics_for_tool(self, uri: str) -> str:
        diags = self.get_diagnostics(uri)
        if not diags:
            return "No diagnostics."
        lines = []
        for d in diags:
            sev = {1: "Error", 2: "Warning", 3: "Info", 4: "Hint"}.get(d.get("severity", 1), "?")
            start = d.get("range", {}).get("start", {})
            line = start.get("line", 0) + 1
            col = start.get("character", 0) + 1
            msg = d.get("message", "")
            lines.append(f"  {sev} [{line}:{col}] {msg}")
        return "\n".join(lines)


# Global registry instance
_registry = LSPDiagnosticRegistry()


def get_lsp_diagnostic_registry() -> LSPDiagnosticRegistry:
    return _registry
