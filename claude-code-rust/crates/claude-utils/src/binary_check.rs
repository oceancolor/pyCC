// Original TS source: utils/binaryCheck.ts
// Binary/command availability detection with caching

use std::collections::HashMap;
use std::sync::Mutex;
use once_cell::sync::Lazy;

static BINARY_CACHE: Lazy<Mutex<HashMap<String, bool>>> = Lazy::new(|| {
    Mutex::new(HashMap::new())
});

/// Check if a binary/command is installed and available on the system.
/// Uses 'which' on Unix and 'where' on Windows. Results are cached.
pub async fn is_binary_installed(command: &str) -> bool {
    let command = command.trim();
    if command.is_empty() {
        return false;
    }

    // Check cache
    {
        let cache = BINARY_CACHE.lock().unwrap_or_else(|e| e.into_inner());
        if let Some(&cached) = cache.get(command) {
            return cached;
        }
    }

    let exists = check_binary_exists(command).await;

    // Cache the result
    let mut cache = BINARY_CACHE.lock().unwrap_or_else(|e| e.into_inner());
    cache.insert(command.to_string(), exists);

    exists
}

async fn check_binary_exists(command: &str) -> bool {
    #[cfg(unix)]
    let which_cmd = "which";
    #[cfg(windows)]
    let which_cmd = "where";

    tokio::process::Command::new(which_cmd)
        .arg(command)
        .output()
        .await
        .map(|output| output.status.success())
        .unwrap_or(false)
}

/// Clear the binary check cache (useful for testing).
pub fn clear_binary_cache() {
    let mut cache = BINARY_CACHE.lock().unwrap_or_else(|e| e.into_inner());
    cache.clear();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_empty_command() {
        assert!(!is_binary_installed("").await);
        assert!(!is_binary_installed("  ").await);
    }

    #[tokio::test]
    async fn test_common_binary() {
        // 'ls' should exist on all Unix systems
        #[cfg(unix)]
        assert!(is_binary_installed("ls").await);
    }
}
