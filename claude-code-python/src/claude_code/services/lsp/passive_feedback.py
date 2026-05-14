"""LSP passive feedback. Ported from services/lsp/passiveFeedback.ts"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from urllib.request import url2pathname


def map_lsp_severity(lsp_severity: Optional[int]) -> str:
    """Map LSP severity number to Claude diagnostic severity string.

    LSP DiagnosticSeverity: 1=Error, 2=Warning, 3=Information, 4=Hint
    """
    mapping = {1: "Error", 2: "Warning", 3: "Info", 4: "Hint"}
    return mapping.get(lsp_severity or 0, "Error")  # type: ignore[arg-type]


def format_diagnostics_for_attachment(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert LSP PublishDiagnosticsParams to DiagnosticFile list format."""
    raw_uri: str = params.get("uri", "")

    try:
        from urllib.parse import urlparse
        parsed = urlparse(raw_uri)
        uri = url2pathname(parsed.path) if parsed.scheme == "file" else raw_uri
    except Exception:
        uri = raw_uri

    diagnostics = []
    for diag in params.get("diagnostics", []):
        code = diag.get("code")
        diagnostics.append({
            "message": diag.get("message", ""),
            "severity": map_lsp_severity(diag.get("severity")),
            "range": {
                "start": {
                    "line": (diag.get("range") or {}).get("start", {}).get("line", 0),
                    "character": (diag.get("range") or {}).get("start", {}).get("character", 0),
                },
                "end": {
                    "line": (diag.get("range") or {}).get("end", {}).get("line", 0),
                    "character": (diag.get("range") or {}).get("end", {}).get("character", 0),
                },
            },
            "source": diag.get("source"),
            "code": str(code) if code is not None else None,
        })

    return [{"uri": uri, "diagnostics": diagnostics}]


def register_lsp_notification_handlers(manager: Any) -> Dict[str, Any]:
    """Register LSP notification handlers on all configured servers.

    Returns tracking data: totalServers, successCount, registrationErrors.
    """
    try:
        servers = manager.get_all_servers()
    except Exception:
        return {
            "totalServers": 0,
            "successCount": 0,
            "registrationErrors": [],
            "diagnosticFailures": {},
        }

    registration_errors = []
    success_count = 0
    diagnostic_failures: Dict[str, Dict[str, Any]] = {}

    for server_name, server_instance in servers.items():
        try:
            if not server_instance or not hasattr(server_instance, "on_notification"):
                registration_errors.append({"serverName": server_name, "error": "no on_notification"})
                continue

            def _make_handler(sname: str):
                def handler(params: Any) -> None:
                    try:
                        if not params or not isinstance(params, dict):
                            return
                        if "uri" not in params or "diagnostics" not in params:
                            return

                        diagnostic_files = format_diagnostics_for_attachment(params)
                        first_file = diagnostic_files[0] if diagnostic_files else None
                        if not first_file or not first_file.get("diagnostics"):
                            return

                        try:
                            from claude_code.services.lsp.lsp_diagnostic_registry import (
                                register_pending_lsp_diagnostic,
                            )
                            register_pending_lsp_diagnostic({
                                "serverName": sname,
                                "files": diagnostic_files,
                            })
                        except Exception as exc:
                            fails = diagnostic_failures.setdefault(sname, {"count": 0, "lastError": ""})
                            fails["count"] += 1
                            fails["lastError"] = str(exc)
                    except Exception:
                        pass

                return handler

            server_instance.on_notification(
                "textDocument/publishDiagnostics",
                _make_handler(server_name),
            )
            success_count += 1

        except Exception as exc:
            registration_errors.append({"serverName": server_name, "error": str(exc)})

    return {
        "totalServers": len(servers),
        "successCount": success_count,
        "registrationErrors": registration_errors,
        "diagnosticFailures": diagnostic_failures,
    }
