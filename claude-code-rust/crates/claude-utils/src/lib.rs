// Original TS source: utils/ directory
// Utility functions - 549 TypeScript files being ported

pub mod abort;
pub mod agent_id;
pub mod array;
pub mod betas;
pub mod binary_check;
pub mod buffered_writer;
pub mod clipboard;
pub mod compact;
pub mod cwd;
pub mod diff;
pub mod env_utils;
pub mod errors;
pub mod file;
pub mod format;
pub mod git;
pub mod hash;
pub mod json;
pub mod log_util;
pub mod memoize;
pub mod messages;
pub mod model;
pub mod model_cost;
pub mod path;
pub mod paths;
pub mod permissions;
pub mod session_storage;
pub mod set;
pub mod settings;
pub mod sleep;
pub mod string_utils;
pub mod system_prompt;
pub mod tokens;
pub mod truncate;
pub mod uuid;
pub mod words;

// Re-export commonly used items
pub use array::{intersperse, count, uniq};
pub use agent_id::{
    format_agent_id, parse_agent_id, generate_request_id, parse_request_id,
    AgentIdParts, RequestIdParts,
};
pub use env_utils::{
    get_claude_config_home_dir, get_teams_dir, is_env_truthy, is_env_defined_falsy,
    is_bare_mode, parse_env_vars, get_aws_region, get_default_vertex_region,
    get_vertex_region_for_model,
};
pub use binary_check::{is_binary_installed, clear_binary_cache};
pub use paths::get_cache_dir;
pub use file::{path_exists, get_file_modification_time, write_text_content, is_enoent};
pub use format::{format_file_size, format_duration, format_seconds_short};
pub use diff::{DiffHunk, compute_patch, count_lines_changed, format_patch};
pub use log_util::{log_error, log_for_debugging};
pub use path::{expand_path, home_dir, to_relative_path, is_path_under_dir};
pub use string_utils::{
    escape_regex, capitalize, plural, first_line_of, count_char, truncate_str, strip_ansi,
};
pub use cwd::{get_cwd, set_cwd, pwd};
pub use model::{
    get_small_fast_model, get_default_haiku_model, get_default_opus_model,
    get_default_sonnet_model, resolve_model_alias, is_model_alias, ALL_MODEL_CONFIGS,
};
pub use errors::{ClaudeError, AbortError, is_abort_error, is_fs_inaccessible};
pub use sleep::{sleep, with_timeout};
pub use permissions::{parse_permission_mode, parse_external_permission_mode};
pub use tokens::{get_token_usage, get_token_count_from_usage, estimate_token_count};
pub use uuid::{validate_uuid, create_agent_id, generate_uuid, generate_uuid_string};
pub use betas::{get_model_betas, is_claude_3_7_or_newer, supports_token_efficient_tools};
pub use settings::{SettingsJson, PermissionsSettings, McpServerSettings, SettingSource};
pub use git::{find_git_root, resolve_git_dir, get_current_branch, is_in_git_repo};
pub use session_storage::{get_transcript_path, parse_jsonl, append_jsonl_record, read_transcript};
pub use system_prompt::{
    SystemPrompt, as_system_prompt, build_effective_system_prompt,
    get_base_system_prompt_prefix, combine_system_prompt_parts,
};
pub use abort::{AbortController, AbortSignal};
pub use hash::{hash_string, hash_bytes, hash_file};
pub use json::{safe_parse_json, safe_stringify_json, JsonValue};
pub use memoize::{memoize, memoize_async};
pub use model_cost::{ModelCost, get_model_cost, calculate_cost};
pub use set::{SetOps};
pub use truncate::{truncate_text, truncate_lines};
pub use words::{count_words, split_words};
