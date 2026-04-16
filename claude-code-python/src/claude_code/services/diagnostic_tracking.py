# 原始 TS: services/diagnosticTracking.ts
"""Diagnostic tracking service.

Tracks IDE linter diagnostics via the connected MCP/IDE client and detects
new errors introduced since the last baseline snapshot.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

MAX_DIAGNOSTICS_SUMMARY_CHARS = 4000


@dataclass
class DiagnosticRange:
    start_line: int
    start_character: int
    end_line: int
    end_character: int


@dataclass
class Diagnostic:
    message: str
    severity: str  # "Error" | "Warning" | "Info" | "Hint"
    range: DiagnosticRange
    source: str = ""
    code: str = ""


@dataclass
class DiagnosticFile:
    uri: str
    diagnostics: list[Diagnostic] = field(default_factory=list)


class DiagnosticTrackingService:
    """Singleton service that monitors IDE diagnostics.

    TODO: Wire up to MCP IDE client for real diagnostic data.
    """

    _instance: "DiagnosticTrackingService | None" = None

    def __init__(self) -> None:
        self._baseline: dict[str, list[Diagnostic]] = {}
        self._initialized = False
        self._last_processed: dict[str, float] = {}

    @classmethod
    def get_instance(cls) -> "DiagnosticTrackingService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize(self, mcp_client: Any = None) -> None:
        """Snapshot current diagnostics as the baseline."""
        if self._initialized:
            return
        # TODO: call IDE MCP to get current diagnostics
        self._initialized = True
        logger.debug("DiagnosticTrackingService initialized (stub)")

    async def get_new_errors(self, files: list[str] | None = None) -> list[DiagnosticFile]:
        """Return diagnostics not present in the baseline.

        TODO: Fetch current diagnostics via MCP and diff against baseline.
        """
        return []

    def reset_baseline(self) -> None:
        self._baseline.clear()
        self._initialized = False
