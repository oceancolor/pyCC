// Original TS source: utils/format.ts
// Display formatting utilities

/// Format a byte count to a human-readable string.
/// e.g., formatFileSize(1536) → "1.5KB"
pub fn format_file_size(size_in_bytes: u64) -> String {
    let kb = size_in_bytes as f64 / 1024.0;
    if kb < 1.0 {
        return format!("{} bytes", size_in_bytes);
    }
    if kb < 1024.0 {
        let s = format!("{:.1}", kb);
        let s = s.trim_end_matches('0').trim_end_matches('.');
        return format!("{}KB", s);
    }
    let mb = kb / 1024.0;
    if mb < 1024.0 {
        let s = format!("{:.1}", mb);
        let s = s.trim_end_matches('0').trim_end_matches('.');
        return format!("{}MB", s);
    }
    let gb = mb / 1024.0;
    let s = format!("{:.1}", gb);
    let s = s.trim_end_matches('0').trim_end_matches('.');
    format!("{}GB", s)
}

/// Format milliseconds as seconds with 1 decimal place.
/// e.g., 1234ms → "1.2s"
pub fn format_seconds_short(ms: f64) -> String {
    format!("{:.1}s", ms / 1000.0)
}

/// Format milliseconds as a human-readable duration.
pub fn format_duration(ms: f64) -> String {
    if ms == 0.0 {
        return "0s".to_string();
    }
    if ms < 1.0 {
        return format!("{:.1}s", ms / 1000.0);
    }
    if ms < 60_000.0 {
        let s = (ms / 1000.0).floor() as u64;
        return format!("{}s", s);
    }

    let total_secs = (ms / 1000.0).round() as u64;
    let days = total_secs / 86400;
    let hours = (total_secs % 86400) / 3600;
    let minutes = (total_secs % 3600) / 60;
    let seconds = total_secs % 60;

    let mut parts = Vec::new();
    if days > 0 { parts.push(format!("{}d", days)); }
    if hours > 0 { parts.push(format!("{}h", hours)); }
    if minutes > 0 { parts.push(format!("{}m", minutes)); }
    if seconds > 0 || parts.is_empty() { parts.push(format!("{}s", seconds)); }

    parts.join(" ")
}

/// Format a number with K/M suffixes.
/// e.g., 1500 → "1.5K"
pub fn format_count(n: u64) -> String {
    if n < 1000 {
        n.to_string()
    } else if n < 1_000_000 {
        let k = n as f64 / 1000.0;
        let s = format!("{:.1}", k);
        let s = s.trim_end_matches('0').trim_end_matches('.');
        format!("{}K", s)
    } else {
        let m = n as f64 / 1_000_000.0;
        let s = format!("{:.1}", m);
        let s = s.trim_end_matches('0').trim_end_matches('.');
        format!("{}M", s)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_format_file_size() {
        assert_eq!(format_file_size(500), "500 bytes");
        assert_eq!(format_file_size(1536), "1.5KB");
        assert_eq!(format_file_size(1024 * 1024), "1MB");
    }

    #[test]
    fn test_format_duration() {
        assert_eq!(format_duration(0.0), "0s");
        assert_eq!(format_duration(5000.0), "5s");
        assert_eq!(format_duration(65000.0), "1m 5s");
    }
}
