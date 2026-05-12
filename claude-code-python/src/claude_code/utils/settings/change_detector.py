"""
Change detector - watches settings files for changes.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional


class SettingsChangeDetector:
    """Watches settings files and notifies on changes."""

    def __init__(
        self,
        on_change: Callable[[str, str], None],
    ) -> None:
        self._on_change = on_change
        self._watched_files: Dict[str, float] = {}
        self._watcher: Optional[Any] = None

    def start(self, file_paths: List[str]) -> None:
        """Start watching the given file paths."""
        for path in file_paths:
            if os.path.exists(path):
                self._watched_files[path] = os.path.getmtime(path)
            else:
                self._watched_files[path] = 0.0

    def stop(self) -> None:
        """Stop watching."""
        self._watched_files.clear()
        if self._watcher:
            try:
                self._watcher.close()
            except Exception:
                pass
            self._watcher = None

    def check_for_changes(self) -> List[str]:
        """Check for changed files. Returns list of changed file paths."""
        changed = []
        for path, mtime in list(self._watched_files.items()):
            try:
                new_mtime = os.path.getmtime(path) if os.path.exists(path) else 0.0
                if new_mtime != mtime:
                    self._watched_files[path] = new_mtime
                    changed.append(path)
                    self._on_change(path, "changed")
            except Exception:
                pass
        return changed


_detector: Optional[SettingsChangeDetector] = None


def create_settings_change_detector(
    on_change: Callable[[str, str], None],
) -> SettingsChangeDetector:
    """Create a new settings change detector."""
    return SettingsChangeDetector(on_change=on_change)
