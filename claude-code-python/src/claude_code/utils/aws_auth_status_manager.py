"""
AWS/Cloud Auth Status Manager - Python port of awsAuthStatusManager.ts

Singleton manager for cloud-provider authentication status (AWS Bedrock,
GCP Vertex). Communicates auth refresh state between auth utilities and
UI components. The 'auth_status' message shape is provider-agnostic,
so a single manager serves all providers.

Legacy name: originally AWS-only; now used by all cloud auth refresh flows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class AwsAuthStatus:
    is_authenticating: bool = False
    output: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def copy(self) -> "AwsAuthStatus":
        return AwsAuthStatus(
            is_authenticating=self.is_authenticating,
            output=list(self.output),
            error=self.error,
        )


class AwsAuthStatusManager:
    """Singleton manager for cloud provider authentication status."""

    _instance: Optional["AwsAuthStatusManager"] = None

    def __init__(self) -> None:
        self._status = AwsAuthStatus()
        self._subscribers: List[Callable[[AwsAuthStatus], None]] = []

    @classmethod
    def get_instance(cls) -> "AwsAuthStatusManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _emit(self) -> None:
        snapshot = self._status.copy()
        for cb in list(self._subscribers):
            cb(snapshot)

    def get_status(self) -> AwsAuthStatus:
        return self._status.copy()

    def start_authentication(self) -> None:
        self._status = AwsAuthStatus(is_authenticating=True, output=[])
        self._emit()

    def add_output(self, line: str) -> None:
        self._status.output.append(line)
        self._emit()

    def set_error(self, error: str) -> None:
        self._status.error = error
        self._emit()

    def end_authentication(self, success: bool) -> None:
        if success:
            # Clear status completely on success
            self._status = AwsAuthStatus(is_authenticating=False, output=[])
        else:
            # Keep output visible on failure
            self._status.is_authenticating = False
        self._emit()

    def subscribe(self, callback: Callable[[AwsAuthStatus], None]) -> Callable[[], None]:
        """Subscribe to status changes. Returns an unsubscribe function."""
        self._subscribers.append(callback)

        def unsubscribe() -> None:
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass

        return unsubscribe

    @classmethod
    def reset(cls) -> None:
        """Clean up for testing."""
        if cls._instance is not None:
            cls._instance._subscribers.clear()
            cls._instance = None
