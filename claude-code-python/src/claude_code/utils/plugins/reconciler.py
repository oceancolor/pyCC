"""
Reconciler - reconciles the desired plugin state with the actual installed state.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set


class ReconcileAction:
    def __init__(
        self,
        action_type: str,  # 'install' | 'uninstall' | 'update'
        plugin_id: str,
        version: Optional[str] = None,
        reason: str = "",
    ) -> None:
        self.action_type = action_type
        self.plugin_id = plugin_id
        self.version = version
        self.reason = reason


def compute_reconcile_actions(
    desired_plugins: List[str],
    installed_plugins: List[str],
    available_updates: Optional[Dict[str, str]] = None,
) -> List[ReconcileAction]:
    """
    Compute the actions needed to reconcile desired with actual state.
    Returns a list of actions to take.
    """
    desired_set = set(desired_plugins)
    installed_set = set(installed_plugins)

    actions: List[ReconcileAction] = []

    # Plugins to install
    for plugin_id in desired_set - installed_set:
        actions.append(ReconcileAction("install", plugin_id))

    # Plugins to uninstall (orphaned)
    for plugin_id in installed_set - desired_set:
        actions.append(ReconcileAction("uninstall", plugin_id, reason="no longer needed"))

    # Plugins to update
    if available_updates:
        for plugin_id in desired_set & installed_set:
            new_version = available_updates.get(plugin_id)
            if new_version:
                actions.append(
                    ReconcileAction("update", plugin_id, version=new_version)
                )

    return actions


async def apply_reconcile_actions(
    actions: List[ReconcileAction],
) -> Dict[str, Any]:
    """Apply a list of reconcile actions. Returns results."""
    results: Dict[str, Any] = {"installed": [], "uninstalled": [], "updated": [], "errors": []}

    for action in actions:
        try:
            if action.action_type == "install":
                from .plugin_installation_helpers import install_plugin
                success, error = await install_plugin(action.plugin_id, action.version)
                if success:
                    results["installed"].append(action.plugin_id)
                else:
                    results["errors"].append({"plugin": action.plugin_id, "error": error})
            elif action.action_type == "uninstall":
                from .plugin_installation_helpers import uninstall_plugin
                success, error = await uninstall_plugin(action.plugin_id)
                if success:
                    results["uninstalled"].append(action.plugin_id)
                else:
                    results["errors"].append({"plugin": action.plugin_id, "error": error})
        except Exception as e:
            results["errors"].append({"plugin": action.plugin_id, "error": str(e)})

    return results
