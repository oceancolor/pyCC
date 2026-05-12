"""
Dependency resolver - resolves plugin dependencies.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set


class DependencyResolutionError(Exception):
    pass


class ResolvedDependency:
    def __init__(self, plugin_id: str, version: Optional[str] = None) -> None:
        self.plugin_id = plugin_id
        self.version = version


def resolve_plugin_dependencies(
    plugin_id: str,
    plugin_manifest: Dict[str, Any],
    installed_plugins: Optional[Dict[str, Any]] = None,
    visited: Optional[Set[str]] = None,
) -> List[ResolvedDependency]:
    """
    Resolve plugin dependencies recursively.
    Returns a list of required dependencies in install order.
    """
    if visited is None:
        visited = set()

    if plugin_id in visited:
        raise DependencyResolutionError(f"Circular dependency detected: {plugin_id}")

    visited.add(plugin_id)
    resolved: List[ResolvedDependency] = []
    installed = installed_plugins or {}

    dependencies = plugin_manifest.get("dependencies") or {}
    for dep_id, dep_version in dependencies.items():
        if dep_id not in installed:
            resolved.append(ResolvedDependency(plugin_id=dep_id, version=dep_version))

    return resolved


def check_dependency_conflicts(
    plugins: List[Dict[str, Any]],
) -> List[str]:
    """Check for version conflicts in a list of plugins. Returns error messages."""
    seen: Dict[str, str] = {}
    conflicts = []

    for plugin in plugins:
        plugin_id = plugin.get("id", "")
        version = plugin.get("version", "")
        if plugin_id in seen and seen[plugin_id] != version:
            conflicts.append(
                f"Version conflict for plugin '{plugin_id}': "
                f"{seen[plugin_id]} vs {version}"
            )
        else:
            seen[plugin_id] = version

    return conflicts
