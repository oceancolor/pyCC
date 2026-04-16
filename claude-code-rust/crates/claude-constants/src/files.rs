// Original TS source: constants/files.ts
// File extension and binary content detection

use std::collections::HashSet;
use once_cell::sync::Lazy;

/// Set of binary file extensions to skip for text-based operations.
pub static BINARY_EXTENSIONS: Lazy<HashSet<&'static str>> = Lazy::new(|| {
    [
        // Images
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tiff", ".tif",
        // Videos
        ".mp4", ".mov", ".avi", ".mkv", ".webm", ".wmv", ".flv", ".m4v", ".mpeg", ".mpg",
        // Audio
        ".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma", ".aiff", ".opus",
        // Archives
        ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".xz", ".z", ".tgz", ".iso",
        // Executables/binaries
        ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".obj", ".lib", ".app",
        ".msi", ".deb", ".rpm",
        // Documents
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp",
        // Fonts
        ".ttf", ".otf", ".woff", ".woff2", ".eot",
        // Bytecode / VM artifacts
        ".pyc", ".pyo", ".class", ".jar", ".war", ".ear", ".node", ".wasm", ".rlib",
        // Database files
        ".sqlite", ".sqlite3", ".db", ".mdb", ".idx",
        // Design / 3D
        ".psd", ".ai", ".eps", ".sketch", ".fig", ".xd", ".blend", ".3ds", ".max",
        // Flash
        ".swf", ".fla",
        // Lock/profiling data
        ".lockb", ".dat", ".data",
    ]
    .iter()
    .cloned()
    .collect()
});

/// Check if a file path has a binary extension.
pub fn has_binary_extension(file_path: &str) -> bool {
    if let Some(dot_pos) = file_path.rfind('.') {
        let ext = &file_path[dot_pos..].to_lowercase();
        BINARY_EXTENSIONS.contains(ext.as_str())
    } else {
        false
    }
}

const BINARY_CHECK_SIZE: usize = 8192;

/// Check if a buffer contains binary content by looking for null bytes
/// or a high proportion of non-printable characters.
pub fn is_binary_content(buffer: &[u8]) -> bool {
    let check_size = buffer.len().min(BINARY_CHECK_SIZE);
    let buf = &buffer[..check_size];

    let mut non_printable = 0usize;
    for &byte in buf {
        if byte == 0 {
            return true;
        }
        if byte < 32 && byte != 9 && byte != 10 && byte != 13 {
            non_printable += 1;
        }
    }

    if check_size == 0 {
        return false;
    }

    (non_printable as f64) / (check_size as f64) > 0.1
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_has_binary_extension() {
        assert!(has_binary_extension("image.png"));
        assert!(has_binary_extension("video.mp4"));
        assert!(!has_binary_extension("main.rs"));
        assert!(!has_binary_extension("readme.md"));
    }

    #[test]
    fn test_is_binary_content() {
        let text = b"Hello, world! This is plain text.\n";
        assert!(!is_binary_content(text));

        let binary = &[0u8, 1, 2, 3, 4];
        assert!(is_binary_content(binary));
    }
}
