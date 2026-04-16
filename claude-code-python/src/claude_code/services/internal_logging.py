# 原始 TS: services/internalLogging.ts
"""Internal Anthropic-employee logging helpers (no-op outside Ant environments)."""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _is_ant_user() -> bool:
    return os.environ.get("USER_TYPE") == "ant"


@lru_cache(maxsize=1)
async def get_kubernetes_namespace() -> str | None:
    """Return k8s namespace if running inside an Ant devbox, else None."""
    if not _is_ant_user():
        return None
    ns_path = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
    try:
        with open(ns_path) as f:
            return f.read().strip()
    except OSError:
        return "namespace not found"


async def get_container_id() -> str | None:
    """Return container ID from /proc/self/mountinfo, or None."""
    if not _is_ant_user():
        return None
    try:
        with open("/proc/self/mountinfo") as f:
            content = f.read()
        # Extract container ID from overlay mount path (heuristic)
        for line in content.splitlines():
            parts = line.split()
            if len(parts) > 3 and "overlay" in line:
                return parts[3].split("/")[-1][:12] or None
    except OSError:
        pass
    return "container ID not found"


def log_internal_event(event_name: str, metadata: dict[str, Any] | None = None) -> None:
    """Log an internal analytics event (Ant-only)."""
    if not _is_ant_user():
        return
    logger.debug("[internal] %s %s", event_name, metadata or {})
