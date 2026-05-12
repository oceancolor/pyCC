"""
Exec HTTP hook - executes HTTP-based hooks.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional
import urllib.parse
import urllib.request

DEFAULT_HTTP_HOOK_TIMEOUT_MS = 10 * 60 * 1000  # 10 minutes


async def exec_http_hook(
    hook: Dict[str, Any],
    hook_name: str,
    hook_event: str,
    json_input: str,
    signal: Any,
) -> Dict[str, Any]:
    """Execute an HTTP-based hook."""
    try:
        from .ssrf_guard import ssrf_guarded_lookup
        from ..log import log_for_debugging

        url = hook.get("url", "")
        timeout_ms = hook.get("timeout", DEFAULT_HTTP_HOOK_TIMEOUT_MS)
        timeout_s = timeout_ms / 1000.0

        log_for_debugging(f"Hooks: Executing HTTP hook {hook_name} to {url}")

        # Validate the URL target against SSRF guard
        parsed = urllib.parse.urlparse(url)
        hostname = parsed.hostname or ""
        ssrf_guarded_lookup(hostname)

        # Execute the HTTP request
        data = json_input.encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        loop = asyncio.get_event_loop()

        def do_request():
            import urllib.error
            try:
                with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                    body = resp.read().decode("utf-8")
                    return {"ok": True, "body": body, "status": resp.status}
            except urllib.error.HTTPError as e:
                return {"ok": False, "body": e.read().decode("utf-8"), "status": e.code}

        result = await loop.run_in_executor(None, do_request)
        stdout = result.get("body", "")
        exit_code = 0 if result.get("ok") else 1

        return {
            "type": "success" if result.get("ok") else "error",
            "ok": result.get("ok", False),
            "output": stdout,
            "stdout": stdout,
            "stderr": "",
            "exitCode": exit_code,
        }
    except Exception as e:
        return {
            "type": "error",
            "ok": False,
            "output": str(e),
            "stdout": "",
            "stderr": str(e),
            "exitCode": 1,
        }
