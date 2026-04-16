// Original TS source: utils/cwd.ts
// Working directory management

use std::sync::Mutex;
use once_cell::sync::Lazy;
use std::path::PathBuf;

static CURRENT_CWD: Lazy<Mutex<Option<String>>> = Lazy::new(|| Mutex::new(None));

/// Get the current working directory.
/// Returns the override if set, otherwise falls back to the process cwd.
pub fn get_cwd() -> String {
    let lock = CURRENT_CWD.lock().unwrap_or_else(|e| e.into_inner());
    if let Some(ref cwd) = *lock {
        return cwd.clone();
    }
    std::env::current_dir()
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_else(|_| "/".to_string())
}

/// Set a global cwd override.
pub fn set_cwd(cwd: impl Into<String>) {
    let mut lock = CURRENT_CWD.lock().unwrap_or_else(|e| e.into_inner());
    *lock = Some(cwd.into());
}

/// Clear the cwd override (revert to process cwd).
pub fn clear_cwd_override() {
    let mut lock = CURRENT_CWD.lock().unwrap_or_else(|e| e.into_inner());
    *lock = None;
}

// Note: AsyncLocalStorage-like scoped overrides would require async context propagation.
// In Rust, this can be done via tokio::task_local! for async contexts.
// For now, provide a simpler global-mutex approach.

tokio::task_local! {
    static CWD_OVERRIDE: String;
}

/// Run a closure with a temporary cwd override (within an async context).
pub async fn run_with_cwd_override<F, T>(cwd: String, f: F) -> T
where
    F: std::future::Future<Output = T>,
{
    CWD_OVERRIDE.scope(cwd, f).await
}

/// Get the async-context-aware cwd.
pub fn pwd() -> String {
    CWD_OVERRIDE.try_with(|s| s.clone())
        .unwrap_or_else(|_| get_cwd())
}
