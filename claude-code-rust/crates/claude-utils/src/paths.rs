// Original TS source: utils/cachePaths.ts (inferred)
// Cache and config path helpers

use std::path::PathBuf;
use crate::env_utils::get_claude_config_home_dir;

/// Get the cache directory (within Claude config home).
pub fn get_cache_dir() -> PathBuf {
    get_claude_config_home_dir().join("cache")
}

/// Get the logs directory.
pub fn get_logs_dir() -> PathBuf {
    get_claude_config_home_dir().join("projects")
}

/// Get the sessions directory.
pub fn get_sessions_dir() -> PathBuf {
    get_claude_config_home_dir()
}

/// Get the plugins directory.
pub fn get_plugins_dir() -> PathBuf {
    get_claude_config_home_dir().join("plugins")
}

/// Get the MCPs directory.
pub fn get_mcps_dir() -> PathBuf {
    get_claude_config_home_dir().join("mcps")
}
