"""Auto dream module exports."""
from claude_code.services.auto_dream.auto_dream import (
    AutoDreamConfig,
    init_auto_dream,
    execute_auto_dream,
)
from claude_code.services.auto_dream.config import is_auto_dream_enabled
from claude_code.services.auto_dream.consolidation_lock import (
    acquire_consolidation_lock,
    release_consolidation_lock,
)

__all__ = [
    "AutoDreamConfig",
    "init_auto_dream",
    "execute_auto_dream",
    "is_auto_dream_enabled",
    "acquire_consolidation_lock",
    "release_consolidation_lock",
]
