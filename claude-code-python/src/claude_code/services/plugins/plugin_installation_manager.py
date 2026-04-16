"""Plugin installation manager. Stub."""
from __future__ import annotations
from typing import List


class PluginInstallationManager:
    def list_installed(self) -> List[str]:
        return []

    def install(self, plugin_id: str) -> bool:
        return False

    def uninstall(self, plugin_id: str) -> bool:
        return False
