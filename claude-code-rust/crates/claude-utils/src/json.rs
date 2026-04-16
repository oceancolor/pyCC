// 原始 TS: utils/json.ts
//! JSON and JSONL parsing utilities with caching and BOM stripping.

use std::fs;
use std::path::Path;
use serde_json::Value;

const MAX_JSONL_READ_BYTES: u64 = 100 * 1024 * 1024; // 100 MB
const PARSE_CACHE_MAX_KEY_BYTES: usize = 8 * 1024;

/// Strip UTF-8 BOM (EF BB BF) from the beginning of a string.
pub fn strip_bom(s: &str) -> &str {
    s.strip_prefix('\u{FEFF}').unwrap_or(s)
}

/// Safely parse a JSON string, returning None on error.
/// Strips BOM before parsing.
pub fn safe_parse_json(json: &str) -> Option<Value> {
    if json.is_empty() {
        return None;
    }
    let stripped = strip_bom(json);
    serde_json::from_str(stripped).ok()
}

/// Safely parse a JSON string with optional error logging.
pub fn safe_parse_json_logged(json: Option<&str>, should_log_error: bool) -> Option<Value> {
    let json = json?;
    if json.is_empty() {
        return None;
    }
    let stripped = strip_bom(json);
    match serde_json::from_str(stripped) {
        Ok(v) => Some(v),
        Err(e) => {
            if should_log_error {
                eprintln!("[json] parse error: {}", e);
            }
            None
        }
    }
}

/// Parse a JSONL string, skipping malformed lines.
/// Each line is parsed as a separate JSON value.
pub fn parse_jsonl<T>(data: &str) -> Vec<T>
where
    T: for<'de> serde::Deserialize<'de>,
{
    let stripped = strip_bom(data);
    let mut results = Vec::new();
    for line in stripped.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        match serde_json::from_str::<T>(trimmed) {
            Ok(v) => results.push(v),
            Err(_) => {
                // Skip malformed lines (same behavior as TS)
            }
        }
    }
    results
}

/// Parse a JSONL byte slice, stripping UTF-8 BOM, skipping malformed lines.
pub fn parse_jsonl_bytes<T>(data: &[u8]) -> Vec<T>
where
    T: for<'de> serde::Deserialize<'de>,
{
    // Strip UTF-8 BOM (EF BB BF)
    let data = if data.starts_with(&[0xEF, 0xBB, 0xBF]) {
        &data[3..]
    } else {
        data
    };

    let mut results = Vec::new();
    let mut start = 0;
    while start < data.len() {
        let end = data[start..]
            .iter()
            .position(|&b| b == b'\n')
            .map(|i| start + i)
            .unwrap_or(data.len());

        let line_bytes = &data[start..end];
        start = end + 1;

        // Try to parse as UTF-8
        if let Ok(line) = std::str::from_utf8(line_bytes) {
            let trimmed = line.trim();
            if !trimmed.is_empty() {
                if let Ok(v) = serde_json::from_str::<T>(trimmed) {
                    results.push(v);
                }
            }
        }
    }
    results
}

/// Read and parse a JSONL file, reading at most the last 100 MB for large files.
pub fn read_jsonl_file<T>(file_path: &Path) -> std::io::Result<Vec<T>>
where
    T: for<'de> serde::Deserialize<'de>,
{
    let metadata = fs::metadata(file_path)?;
    let size = metadata.len();

    if size <= MAX_JSONL_READ_BYTES {
        let data = fs::read(file_path)?;
        return Ok(parse_jsonl_bytes(&data));
    }

    // File is too large — read the last 100 MB and skip the first partial line
    use std::io::{Read, Seek, SeekFrom};
    let mut file = fs::File::open(file_path)?;
    let offset = size - MAX_JSONL_READ_BYTES;
    file.seek(SeekFrom::Start(offset))?;

    let mut buf = vec![0u8; MAX_JSONL_READ_BYTES as usize];
    let mut total_read = 0;
    loop {
        match file.read(&mut buf[total_read..]) {
            Ok(0) => break,
            Ok(n) => total_read += n,
            Err(e) => return Err(e),
        }
    }
    let buf = &buf[..total_read];

    // Skip the first partial line
    if let Some(newline_pos) = buf.iter().position(|&b| b == b'\n') {
        if newline_pos + 1 < buf.len() {
            return Ok(parse_jsonl_bytes(&buf[newline_pos + 1..]));
        }
    }
    Ok(parse_jsonl_bytes(buf))
}

/// Add an item to a JSON array string.
/// If the content is empty, creates a new array. Preserves formatting where possible.
pub fn add_item_to_json_array(content: &str, new_item: &Value) -> String {
    let cleaned = strip_bom(content.trim());
    if cleaned.is_empty() {
        return serde_json::to_string_pretty(&serde_json::json!([new_item]))
            .unwrap_or_else(|_| "[]".to_string());
    }

    match serde_json::from_str::<Value>(cleaned) {
        Ok(Value::Array(mut arr)) => {
            arr.push(new_item.clone());
            serde_json::to_string_pretty(&arr).unwrap_or_else(|_| "[]".to_string())
        }
        _ => {
            // Not an array — replace with new array
            serde_json::to_string_pretty(&serde_json::json!([new_item]))
                .unwrap_or_else(|_| "[]".to_string())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_strip_bom() {
        assert_eq!(strip_bom("\u{FEFF}hello"), "hello");
        assert_eq!(strip_bom("hello"), "hello");
        assert_eq!(strip_bom(""), "");
    }

    #[test]
    fn test_safe_parse_json() {
        assert!(safe_parse_json("null").is_some());
        assert!(safe_parse_json(r#"{"key": "value"}"#).is_some());
        assert!(safe_parse_json("invalid").is_none());
        assert!(safe_parse_json("").is_none());
    }

    #[test]
    fn test_parse_jsonl() {
        let data = r#"{"a": 1}
{"b": 2}
invalid line
{"c": 3}
"#;
        let results: Vec<Value> = parse_jsonl(data);
        assert_eq!(results.len(), 3);
    }

    #[test]
    fn test_add_item_to_json_array() {
        let result = add_item_to_json_array("", &serde_json::json!("item"));
        let parsed: Value = serde_json::from_str(&result).unwrap();
        assert!(parsed.is_array());
        assert_eq!(parsed.as_array().unwrap().len(), 1);

        let result2 = add_item_to_json_array(r#"["existing"]"#, &serde_json::json!("new"));
        let parsed2: Value = serde_json::from_str(&result2).unwrap();
        assert_eq!(parsed2.as_array().unwrap().len(), 2);
    }
}
