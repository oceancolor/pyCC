"""
exec_sync wrapper with slow-operation logging. Ported from execSyncWrapper.ts
"""
from __future__ import annotations
import subprocess
import time
import logging
from typing import Optional

_logger = logging.getLogger(__name__)
SLOW_THRESHOLD_MS = 500


def exec_sync_deprecated(command: str, cwd: Optional[str] = None,
                          env: Optional[dict] = None, encoding: str = "utf-8") -> str:
    """
    Synchronous exec with slow-operation warning.
    Deprecated: use async alternatives when possible.
    """
    start = time.monotonic()
    result = subprocess.run(command, shell=True, capture_output=True,
                            text=True, encoding=encoding, cwd=cwd, env=env)
    elapsed_ms = (time.monotonic() - start) * 1000
    if elapsed_ms > SLOW_THRESHOLD_MS:
        _logger.warning("Slow execSync (%dms): %s", int(elapsed_ms), command[:100])
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, command,
                                            result.stdout, result.stderr)
    return result.stdout
