// 原始 TS: utils/truncate.ts
//! Text truncation utilities with Unicode grapheme-cluster awareness.
//!
//! Note: Full grapheme segmentation requires the `unicode-segmentation` crate.
//! For ASCII text, we fall back to byte-based truncation.

/// Estimate display width of a string.
/// CJK characters count as 2, ASCII as 1, other Unicode as 1.
/// For full accuracy use the `unicode-width` crate.
pub fn string_width(s: &str) -> usize {
    use unicode_width::UnicodeWidthStr;
    UnicodeWidthStr::width(s)
}

/// Truncate a string to fit within `max_width` terminal columns.
/// Appends '…' when truncation occurs. Grapheme-safe.
pub fn truncate_to_width(text: &str, max_width: usize) -> String {
    use unicode_segmentation::UnicodeSegmentation;
    use unicode_width::UnicodeWidthStr;

    if UnicodeWidthStr::width(text) <= max_width {
        return text.to_string();
    }
    if max_width <= 1 {
        return "…".to_string();
    }

    let ellipsis_width = 1_usize; // '…' = 1 display column
    let budget = max_width - ellipsis_width;
    let mut result = String::new();
    let mut width = 0usize;

    for grapheme in UnicodeSegmentation::graphemes(text, true) {
        let gw = UnicodeWidthStr::width(grapheme);
        if width + gw > budget {
            break;
        }
        result.push_str(grapheme);
        width += gw;
    }
    result.push('…');
    result
}

/// Truncate from the start of a string, keeping the tail end.
/// Prepends '…' when truncation occurs.
pub fn truncate_start_to_width(text: &str, max_width: usize) -> String {
    use unicode_segmentation::UnicodeSegmentation;
    use unicode_width::UnicodeWidthStr;

    if UnicodeWidthStr::width(text) <= max_width {
        return text.to_string();
    }
    if max_width <= 1 {
        return "…".to_string();
    }

    let budget = max_width - 1; // -1 for '…'
    let graphemes: Vec<&str> = UnicodeSegmentation::graphemes(text, true).collect();
    let mut width = 0usize;
    let mut start_idx = graphemes.len();

    for i in (0..graphemes.len()).rev() {
        let gw = UnicodeWidthStr::width(graphemes[i]);
        if width + gw > budget {
            break;
        }
        width += gw;
        start_idx = i;
    }

    let mut result = "…".to_string();
    for g in &graphemes[start_idx..] {
        result.push_str(g);
    }
    result
}

/// Truncate a string without appending an ellipsis.
/// Useful when the caller adds its own separator (e.g. middle-truncation).
pub fn truncate_to_width_no_ellipsis(text: &str, max_width: usize) -> String {
    use unicode_segmentation::UnicodeSegmentation;
    use unicode_width::UnicodeWidthStr;

    if UnicodeWidthStr::width(text) <= max_width {
        return text.to_string();
    }
    if max_width == 0 {
        return String::new();
    }

    let mut result = String::new();
    let mut width = 0usize;

    for grapheme in UnicodeSegmentation::graphemes(text, true) {
        let gw = UnicodeWidthStr::width(grapheme);
        if width + gw > max_width {
            break;
        }
        result.push_str(grapheme);
        width += gw;
    }
    result
}

/// Truncate a file path in the middle to preserve both directory context and filename.
/// For example: "src/components/deeply/nested/folder/MyComponent.tsx" →
/// "src/components/…/MyComponent.tsx" when max_length is 30.
pub fn truncate_path_middle(path: &str, max_length: usize) -> String {
    use unicode_width::UnicodeWidthStr;

    if UnicodeWidthStr::width(path) <= max_length {
        return path.to_string();
    }
    if max_length == 0 {
        return "…".to_string();
    }
    if max_length < 5 {
        return truncate_to_width(path, max_length);
    }

    // Split into directory and filename
    let last_slash = path.rfind('/');
    let (directory, filename) = if let Some(idx) = last_slash {
        (&path[..idx], &path[idx..]) // filename includes the leading '/'
    } else {
        ("", path)
    };

    let filename_width = UnicodeWidthStr::width(filename);

    // If filename alone is too long, truncate from start
    if filename_width >= max_length - 1 {
        return truncate_start_to_width(path, max_length);
    }

    // Space available for directory prefix (subtract 1 for '…')
    let available_for_dir = max_length - 1 - filename_width;

    if available_for_dir == 0 {
        return truncate_start_to_width(filename, max_length);
    }

    let truncated_dir = truncate_to_width_no_ellipsis(directory, available_for_dir);
    format!("{}…{}", truncated_dir, filename)
}

/// Truncate a string with optional single-line mode.
/// In single-line mode, also truncates at the first newline.
pub fn truncate(s: &str, max_width: usize, single_line: bool) -> String {
    use unicode_width::UnicodeWidthStr;

    let mut result = s.to_string();

    if single_line {
        if let Some(newline_idx) = result.find('\n') {
            let before_newline = &result[..newline_idx];
            let w = UnicodeWidthStr::width(before_newline);
            if w + 1 > max_width {
                return truncate_to_width(before_newline, max_width);
            }
            return format!("{}…", before_newline);
        }
    }

    if UnicodeWidthStr::width(result.as_str()) <= max_width {
        return result;
    }
    truncate_to_width(&result, max_width)
}

/// Wrap text into lines of at most `width` display columns.
pub fn wrap_text(text: &str, width: usize) -> Vec<String> {
    use unicode_segmentation::UnicodeSegmentation;
    use unicode_width::UnicodeWidthStr;

    let mut lines: Vec<String> = Vec::new();
    let mut current_line = String::new();
    let mut current_width = 0usize;

    for grapheme in UnicodeSegmentation::graphemes(text, true) {
        let gw = UnicodeWidthStr::width(grapheme);
        if current_width + gw <= width {
            current_line.push_str(grapheme);
            current_width += gw;
        } else {
            if !current_line.is_empty() {
                lines.push(current_line.clone());
            }
            current_line = grapheme.to_string();
            current_width = gw;
        }
    }

    if !current_line.is_empty() {
        lines.push(current_line);
    }
    lines
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_truncate_to_width_short() {
        let s = "hello";
        assert_eq!(truncate_to_width(s, 10), "hello");
    }

    #[test]
    fn test_truncate_to_width_long() {
        let s = "hello world";
        let result = truncate_to_width(s, 7);
        assert!(result.ends_with('…'));
        assert!(string_width(&result) <= 7);
    }

    #[test]
    fn test_truncate_start_to_width() {
        let s = "hello world";
        let result = truncate_start_to_width(s, 7);
        assert!(result.starts_with('…'));
        assert!(string_width(&result) <= 7);
    }

    #[test]
    fn test_truncate_path_middle() {
        let path = "src/components/deeply/nested/folder/MyComponent.tsx";
        let result = truncate_path_middle(path, 35);
        assert!(result.contains('…'));
        assert!(result.ends_with("MyComponent.tsx"));
        assert!(string_width(&result) <= 35);
    }

    #[test]
    fn test_truncate_single_line() {
        let s = "line one\nline two";
        let result = truncate(s, 50, true);
        assert!(!result.contains('\n'));
        assert!(result.ends_with('…'));
    }

    #[test]
    fn test_wrap_text() {
        let text = "hello world";
        let lines = wrap_text(text, 5);
        assert_eq!(lines.len(), 3);
        assert_eq!(lines[0], "hello");
        assert_eq!(lines[1], " ");
        assert_eq!(lines[2], "world");
    }
}
