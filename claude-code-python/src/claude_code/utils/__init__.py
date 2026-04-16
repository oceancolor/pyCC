"""
Utils package init
原始 TS: src/utils/
"""
from claude_code.utils.env_utils import (
    get_claude_config_home_dir,
    get_teams_dir,
    is_env_truthy,
    is_env_defined_falsy,
    is_bare_mode,
    parse_env_vars,
    get_aws_region,
    get_default_vertex_region,
    get_vertex_region_for_model,
    is_running_on_homespace,
)
from claude_code.utils.errors import (
    ClaudeError,
    MalformedCommandError,
    AbortError,
    is_abort_error,
    ConfigParseError,
    ShellError,
    TeleportOperationError,
    TelemetrySafeError,
    is_enoent,
    error_message,
)
from claude_code.utils.file import (
    path_exists,
    read_file_safe,
    get_file_modification_time,
    write_text_content,
    add_line_numbers,
    format_file_size,
)
from claude_code.utils.format import (
    format_file_size,
    format_seconds_short,
    format_duration,
    truncate,
)
from claude_code.utils.shell import (
    find_suitable_shell,
    exec_command,
)
from claude_code.utils.shell_command import ExecResult

__all__ = [
    # env_utils
    "get_claude_config_home_dir",
    "get_teams_dir",
    "is_env_truthy",
    "is_env_defined_falsy",
    "is_bare_mode",
    "parse_env_vars",
    "get_aws_region",
    "get_default_vertex_region",
    "get_vertex_region_for_model",
    "is_running_on_homespace",
    # errors
    "ClaudeError",
    "MalformedCommandError",
    "AbortError",
    "is_abort_error",
    "ConfigParseError",
    "ShellError",
    "TeleportOperationError",
    "TelemetrySafeError",
    "is_enoent",
    "error_message",
    # file
    "path_exists",
    "read_file_safe",
    "get_file_modification_time",
    "write_text_content",
    "add_line_numbers",
    # format
    "format_file_size",
    "format_seconds_short",
    "format_duration",
    "truncate",
    # shell
    "find_suitable_shell",
    "exec_command",
    "ExecResult",
]
