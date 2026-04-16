// Original TS source: utils/path.ts
// Path expansion and manipulation utilities

use std::path::{Path, PathBuf};

/// Get the home directory.
pub fn home_dir() -> Option<PathBuf> {
    #[cfg(unix)]
    return std::env::var("HOME").ok().map(PathBuf::from);
    #[cfg(windows)]
    return std::env::var("USERPROFILE").ok().map(PathBuf::from)
        .or_else(|| std::env::var("HOMEDRIVE").ok().zip(std::env::var("HOMEPATH").ok())
            .map(|(drive, path)| PathBuf::from(format!("{}{}", drive, path))));
    #[allow(unreachable_code)]
    None
}

/// Expand a path that may contain tilde notation (~) to an absolute path.
///
/// # Arguments
/// * `path` - The path to expand
/// * `base_dir` - Base directory for resolving relative paths (defaults to cwd)
pub fn expand_path(path_str: &str, base_dir: Option<&str>) -> Result<PathBuf, String> {
    let trimmed = path_str.trim();

    if trimmed.is_empty() {
        let base = base_dir.map(PathBuf::from)
            .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));
        return Ok(base);
    }

    // Security: check for null bytes
    if trimmed.contains('\0') {
        return Err("Path contains null bytes".to_string());
    }

    // Handle home directory notation
    if trimmed == "~" {
        return home_dir().ok_or_else(|| "Cannot determine home directory".to_string());
    }

    if let Some(rest) = trimmed.strip_prefix("~/") {
        let home = home_dir().ok_or_else(|| "Cannot determine home directory".to_string())?;
        return Ok(home.join(rest));
    }

    let path = Path::new(trimmed);
    if path.is_absolute() {
        return Ok(path.to_path_buf());
    }

    // Relative path: resolve against base_dir
    let base = if let Some(b) = base_dir {
        PathBuf::from(b)
    } else {
        std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
    };

    Ok(base.join(path))
}

/// Convert an absolute path to a relative path from a base directory.
pub fn to_relative_path(absolute: &Path, base: &Path) -> PathBuf {
    if let Ok(rel) = absolute.strip_prefix(base) {
        rel.to_path_buf()
    } else {
        absolute.to_path_buf()
    }
}

/// Get the directory of a file path.
pub fn dirname(path: &Path) -> PathBuf {
    path.parent().unwrap_or(Path::new(".")).to_path_buf()
}

/// Check if a path is under a given directory.
pub fn is_path_under_dir(path: &Path, dir: &Path) -> bool {
    let abs_path = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir().unwrap_or_default().join(path)
    };

    let abs_dir = if dir.is_absolute() {
        dir.to_path_buf()
    } else {
        std::env::current_dir().unwrap_or_default().join(dir)
    };

    abs_path.starts_with(&abs_dir)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_expand_path_absolute() {
        let result = expand_path("/usr/local/bin", None).unwrap();
        assert_eq!(result, PathBuf::from("/usr/local/bin"));
    }

    #[test]
    fn test_expand_path_tilde() {
        if home_dir().is_some() {
            let result = expand_path("~/Documents", None).unwrap();
            assert!(result.starts_with(home_dir().unwrap()));
        }
    }

    #[test]
    fn test_to_relative_path() {
        let abs = Path::new("/project/src/main.rs");
        let base = Path::new("/project");
        let rel = to_relative_path(abs, base);
        assert_eq!(rel, PathBuf::from("src/main.rs"));
    }
}
