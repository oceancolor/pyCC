"""Session memory module exports."""
from claude_code.services.session_memory.session_memory import (
    should_extract_memory,
    reset_last_memory_message_uuid,
)
from claude_code.services.session_memory.prompts import (
    load_session_memory_prompt,
    build_session_memory_update_prompt,
)
from claude_code.services.session_memory.session_memory_utils import (
    is_session_memory_enabled,
)

# Optional exports that may not exist on all builds
try:
    from claude_code.services.session_memory.session_memory import (
        init_session_memory,
        manually_extract_session_memory,
        ManualExtractionResult,
        create_memory_file_can_use_tool,
    )
except ImportError:
    pass

try:
    from claude_code.services.session_memory.session_memory_utils import get_session_memory_path
except ImportError:
    pass

__all__ = [
    "should_extract_memory",
    "reset_last_memory_message_uuid",
    "load_session_memory_prompt",
    "build_session_memory_update_prompt",
    "is_session_memory_enabled",
]
