"""Remote managed settings service index.

Re-exports the public API of the remote managed settings service.

Remote managed settings are operator-controlled configuration values
fetched from a URL specified in the project or global settings file.
They override local user preferences and are used to enforce
organisation-wide policies.

Ported from: src/services/remoteManagedSettings/ (TypeScript)

Usage::

    from claude_code.services.remote_managed_settings.index import (
        get_remote_managed_settings,
        load_remote_managed_settings,
        clear_remote_managed_settings_cache,
    )
"""
from __future__ import annotations

from claude_code.services.remote_managed_settings.remote_managed_settings import (
    get_remote_managed_settings,
    load_remote_managed_settings,
    clear_remote_managed_settings_cache,
)

__all__ = [
    "get_remote_managed_settings",
    "load_remote_managed_settings",
    "clear_remote_managed_settings_cache",
]
