// Original TS source: utils/file.ts
// File system utilities

use std::path::{Path, PathBuf};
use anyhow::{Context, Result};

pub const MAX_OUTPUT_SIZE: usize = 256 * 1024; // 0.25 MB
pub const FILE_NOT_FOUND_CWD_NOTE: &str =
    "Note: If you're looking for a file, make sure you're in the right directory.";

/// Check if a path exists asynchronously.
pub async fn path_exists(path: &Path) -> bool {
    tokio::fs::metadata(path).await.is_ok()
}

/// Get the modification time of a file in milliseconds.
pub fn get_file_modification_time(file_path: &Path) -> Result<u64> {
    let meta = std::fs::metadata(file_path)
        .with_context(|| format!("Failed to stat {}", file_path.display()))?;
    let mtime = meta
        .modified()?
        .duration_since(std::time::UNIX_EPOCH)?
        .as_millis() as u64;
    Ok(mtime)
}

/// Async variant of get_file_modification_time.
pub async fn get_file_modification_time_async(file_path: &Path) -> Result<u64> {
    let meta = tokio::fs::metadata(file_path)
        .await
        .with_context(|| format!("Failed to stat {}", file_path.display()))?;
    let mtime = meta
        .modified()?
        .duration_since(std::time::UNIX_EPOCH)?
        .as_millis() as u64;
    Ok(mtime)
}

/// Add line numbers to text content.
pub fn add_line_numbers(content: &str, start_line: u64) -> String {
    content
        .lines()
        .enumerate()
        .map(|(i, line)| format!("{:5}\t{}", start_line + i as u64 + 1, line))
        .collect::<Vec<_>>()
        .join("\n")
}

/// Write text content to a file, creating parent directories as needed.
pub async fn write_text_content(file_path: &Path, content: &str) -> Result<()> {
    if let Some(parent) = file_path.parent() {
        tokio::fs::create_dir_all(parent)
            .await
            .with_context(|| format!("Failed to create directories for {}", file_path.display()))?;
    }
    tokio::fs::write(file_path, content)
        .await
        .with_context(|| format!("Failed to write {}", file_path.display()))?;
    Ok(())
}

/// Find a similar file in the cwd (for suggesting corrections).
pub async fn find_similar_file(file_path: &Path, cwd: &Path) -> Option<PathBuf> {
    let target_name = file_path.file_name()?.to_string_lossy().to_lowercase();

    let entries = tokio::fs::read_dir(cwd).await.ok()?;
    let mut stream = entries;

    while let Ok(Some(entry)) = stream.next_entry().await {
        let name = entry.file_name().to_string_lossy().to_lowercase();
        if name.contains(&target_name) || target_name.contains(&name) {
            return Some(entry.path());
        }
    }

    None
}

/// Suggest a path under cwd if the given path isn't found.
pub async fn suggest_path_under_cwd(file_path: &Path, cwd: &Path) -> Option<String> {
    if let Some(similar) = find_similar_file(file_path, cwd).await {
        return Some(format!("Did you mean: {}?", similar.display()));
    }
    Some(format!("Searched in: {}", cwd.display()))
}

/// Check if an error code corresponds to ENOENT (file not found).
pub fn is_enoent(err: &std::io::Error) -> bool {
    err.kind() == std::io::ErrorKind::NotFound
}
