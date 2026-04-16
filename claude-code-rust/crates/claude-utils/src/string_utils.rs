// Original TS source: utils/stringUtils.ts
// String utility functions

/// Escape special regex characters in a string.
pub fn escape_regex(s: &str) -> String {
    let mut result = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            '.' | '*' | '+' | '?' | '^' | '$' | '{' | '}' | '(' | ')' | '|' | '[' | ']' | '\\' => {
                result.push('\\');
                result.push(c);
            }
            _ => result.push(c),
        }
    }
    result
}

/// Capitalize the first character of a string (does NOT lowercase the rest).
pub fn capitalize(s: &str) -> String {
    let mut chars = s.chars();
    match chars.next() {
        None => String::new(),
        Some(first) => {
            let mut result = String::new();
            for c in first.to_uppercase() {
                result.push(c);
            }
            result.push_str(chars.as_str());
            result
        }
    }
}

/// Return singular or plural form based on count.
/// e.g., plural(1, "file", "files") → "file"
/// e.g., plural(3, "file", "files") → "files"
pub fn plural<'a>(n: usize, word: &'a str, plural_word: &'a str) -> &'a str {
    if n == 1 { word } else { plural_word }
}

/// Get the first line of a string.
pub fn first_line_of(s: &str) -> &str {
    match s.find('\n') {
        None => s,
        Some(pos) => &s[..pos],
    }
}

/// Count occurrences of a character in a string.
pub fn count_char(s: &str, c: char) -> usize {
    s.chars().filter(|&ch| ch == c).count()
}

/// Normalize full-width digits to half-width digits (for Japanese/CJK IME input).
pub fn normalize_full_width_digits(s: &str) -> String {
    s.chars().map(|c| {
        if c >= '\u{FF10}' && c <= '\u{FF19}' {
            char::from_u32(c as u32 - 0xFEE0).unwrap_or(c)
        } else {
            c
        }
    }).collect()
}

/// Truncate a string to max_length characters, adding ellipsis if needed.
pub fn truncate_str(s: &str, max_length: usize) -> String {
    if s.len() <= max_length {
        s.to_string()
    } else {
        let truncated: String = s.chars().take(max_length - 1).collect();
        format!("{}…", truncated)
    }
}

/// Remove ANSI escape sequences from a string.
pub fn strip_ansi(s: &str) -> String {
    // Match ESC[...m or ESC[...A/B/C/D etc.
    static ANSI_RE: once_cell::sync::Lazy<regex::Regex> = once_cell::sync::Lazy::new(|| {
        regex::Regex::new(r"\x1b\[[0-9;]*[mABCDEFGHJKST]").unwrap()
    });
    ANSI_RE.replace_all(s, "").to_string()
}

/// Check if a string looks like a URL.
pub fn looks_like_url(s: &str) -> bool {
    s.starts_with("http://") || s.starts_with("https://")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_escape_regex() {
        assert_eq!(escape_regex("hello.world"), "hello\\.world");
        assert_eq!(escape_regex("a+b*c"), "a\\+b\\*c");
    }

    #[test]
    fn test_capitalize() {
        assert_eq!(capitalize("fooBar"), "FooBar");
        assert_eq!(capitalize("hello world"), "Hello world");
        assert_eq!(capitalize(""), "");
    }

    #[test]
    fn test_plural() {
        assert_eq!(plural(1, "file", "files"), "file");
        assert_eq!(plural(3, "file", "files"), "files");
        assert_eq!(plural(0, "item", "items"), "items");
    }

    #[test]
    fn test_first_line_of() {
        assert_eq!(first_line_of("hello\nworld"), "hello");
        assert_eq!(first_line_of("no newline"), "no newline");
    }
}
