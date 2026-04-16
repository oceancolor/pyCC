# 原始 TS: bridge/bridgeApi.ts
"""
Bridge API stub — HTTP 客户端，用于与 claude.ai bridge 服务端交互。
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from .types import (
    BRIDGE_LOGIN_INSTRUCTION,
    BridgeApiClient,
    BridgeConfig,
    PermissionResponseEvent,
    WorkResponse,
)

logger = logging.getLogger(__name__)


class BridgeApiError(Exception):
    """Raised when bridge API returns an error response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class BridgeAuthError(BridgeApiError):
    """Raised on 401 Unauthorized (token expired or missing)."""


def create_bridge_api_client(
    config: BridgeConfig,
    on_401_refresh: Callable[[], bool] | None = None,
    on_debug: Callable[[str], None] | None = None,
) -> BridgeApiClient:
    """
    Factory: create a BridgeApiClient using the provided config.

    Args:
        config: Bridge connection config (base_url, token, etc.)
        on_401_refresh: Optional callback; if set, called on 401 to attempt
            OAuth token refresh. Should return True if refresh succeeded.
        on_debug: Optional callback for debug log messages.

    Returns:
        A concrete BridgeApiClient instance.
    """
    # TODO: return a real HTTP-backed implementation
    return _HttpBridgeApiClient(config, on_401_refresh, on_debug)


class _HttpBridgeApiClient(BridgeApiClient):
    """Concrete HTTP implementation (stub)."""

    def __init__(
        self,
        config: BridgeConfig,
        on_401_refresh: Callable[[], bool] | None,
        on_debug: Callable[[str], None] | None,
    ) -> None:
        self._config = config
        self._on_401_refresh = on_401_refresh
        self._on_debug = on_debug

    def _debug(self, msg: str) -> None:
        if self._on_debug:
            self._on_debug(msg)
        logger.debug(msg)

    def get_work(self, environment_id: str) -> WorkResponse | None:
        """
        Poll the bridge server for the next work item.

        GET /api/environments/{environment_id}/work
        """
        # TODO: implement actual HTTP call with retry on 401
        self._debug(f"get_work: environment_id={environment_id}")
        return None  # stub: no work available

    def complete_work(self, work_id: str, result: dict[str, Any]) -> None:
        """
        Mark a work item as complete.

        POST /api/environments/work/{work_id}/complete
        """
        # TODO: implement actual HTTP call
        self._debug(f"complete_work: work_id={work_id}")

    def respond_to_permission(self, event: PermissionResponseEvent) -> None:
        """
        Send a permission decision back to the bridge.

        POST /api/environments/work/{work_id}/permission
        """
        # TODO: implement actual HTTP call
        self._debug(f"respond_to_permission: tool={event.tool_name} decision={event.decision}")

    def _handle_401(self) -> bool:
        """Attempt token refresh on 401. Returns True if refresh succeeded."""
        if self._on_401_refresh:
            refreshed = self._on_401_refresh()
            if refreshed:
                self._debug("Token refresh succeeded, retrying request.")
                return True
        raise BridgeAuthError(
            f"Authentication failed. {BRIDGE_LOGIN_INSTRUCTION}",
            status_code=401,
        )
