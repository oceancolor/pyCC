// Original TS source: utils/git/gitFilesystem.ts, utils/git.ts
// Git filesystem utilities

use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::collections::HashMap;
use once_cell::sync::Lazy;
use anyhow::Result;

static GIT_DIR_CACHE: Lazy<Mutex<HashMap<String, Option<PathBuf>>>> = Lazy::new(|| {
    Mutex::new(HashMap::new())
});

/// Clear the git dir cache
pub fn clear_resolve_git_dir_cache() {
    let mut cache = GIT_DIR_CACHE.lock().unwrap_or_else(|e| e.into_inner());
    cache.clear();
}

/// Resolve the actual .git directory for a repo.
/// Handles worktrees/submodules where .git is a file.
pub async fn resolve_git_dir(start_path: Option<&Path>) -> Result<Option<PathBuf>> {
    let cwd = start_path.map(|p| p.to_path_buf())
        .or_else(|| std::env::current_dir().ok())
        .unwrap_or_else(|| PathBuf::from("."));

    let cwd_str = cwd.to_string_lossy().to_string();

    // Check cache
    {
        let cache = GIT_DIR_CACHE.lock().unwrap_or_else(|e| e.into_inner());
        if let Some(cached) = cache.get(&cwd_str) {
            return Ok(cached.clone());
        }
    }

    let root = find_git_root(&cwd);
    if root.is_none() {
        let mut cache = GIT_DIR_CACHE.lock().unwrap_or_else(|e| e.into_inner());
        cache.insert(cwd_str, None);
        return Ok(None);
    }

    let root = root.unwrap();
    let git_path = root.join(".git");

    let result = if git_path.exists() {
        if git_path.is_file() {
            // Worktree or submodule: .git is a file with `gitdir: <path>`
            let content = tokio::fs::read_to_string(&git_path).await?;
            if let Some(path) = content.strip_prefix("gitdir: ") {
                let resolved = root.join(path.trim());
                Some(resolved.canonicalize().unwrap_or(resolved))
            } else {
                Some(git_path)
            }
        } else {
            Some(git_path)
        }
    } else {
        None
    };

    let mut cache = GIT_DIR_CACHE.lock().unwrap_or_else(|e| e.into_inner());
    cache.insert(cwd_str, result.clone());

    Ok(result)
}

/// Find the git root directory (where .git lives) by walking up from start_path.
pub fn find_git_root(start_path: &Path) -> Option<PathBuf> {
    let mut current = if start_path.is_absolute() {
        start_path.to_path_buf()
    } else {
        std::env::current_dir().ok()?.join(start_path)
    };

    loop {
        let git = current.join(".git");
        if git.exists() {
            return Some(current);
        }

        if !current.pop() {
            return None;
        }
    }
}

/// Get the current branch name for a repository.
pub async fn get_current_branch(git_dir: &Path) -> Result<Option<String>> {
    let head_path = git_dir.join("HEAD");
    if !head_path.exists() {
        return Ok(None);
    }

    let head_content = tokio::fs::read_to_string(&head_path).await?;
    let head = head_content.trim();

    if let Some(branch) = head.strip_prefix("ref: refs/heads/") {
        Ok(Some(branch.to_string()))
    } else {
        // Detached HEAD - return commit SHA
        if head.len() >= 7 {
            Ok(Some(format!("(HEAD detached at {})", &head[..7])))
        } else {
            Ok(None)
        }
    }
}

/// Read git config value for a key.
pub async fn get_git_config(git_dir: &Path, key: &str) -> Result<Option<String>> {
    let config_path = git_dir.join("config");
    if !config_path.exists() {
        return Ok(None);
    }

    let content = tokio::fs::read_to_string(&config_path).await?;
    Ok(parse_git_config_value(&content, key))
}

/// Simple git config parser for key=value lookup.
fn parse_git_config_value(config: &str, key: &str) -> Option<String> {
    // key format: "section.subsection.name" or "section.name"
    let parts: Vec<&str> = key.splitn(3, '.').collect();
    let (section, subsection, name) = match parts.len() {
        2 => (parts[0], None, parts[1]),
        3 => (parts[0], Some(parts[1]), parts[2]),
        _ => return None,
    };

    let mut in_section = false;
    let mut current_section = String::new();
    let mut current_subsection: Option<String> = None;

    for line in config.lines() {
        let trimmed = line.trim();

        if trimmed.starts_with('[') && trimmed.ends_with(']') {
            let sec_content = &trimmed[1..trimmed.len()-1];
            let parts: Vec<&str> = sec_content.splitn(2, ' ').collect();
            current_section = parts[0].to_lowercase();
            current_subsection = parts.get(1).map(|s| {
                s.trim().trim_matches('"').to_string()
            });
            in_section = current_section == section
                && current_subsection.as_deref() == subsection;
        } else if in_section {
            if let Some(eq_pos) = trimmed.find('=') {
                let k = trimmed[..eq_pos].trim().to_lowercase();
                let v = trimmed[eq_pos+1..].trim();
                if k == name {
                    return Some(v.to_string());
                }
            }
        }
    }

    None
}

/// Check if a path is inside a git repository.
pub fn is_in_git_repo(path: &Path) -> bool {
    find_git_root(path).is_some()
}
