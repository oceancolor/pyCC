// Original TS source: utils/log.ts
// Logging utilities

use chrono::{DateTime, Utc};
use std::path::PathBuf;
use anyhow::Result;

/// Get the display title for a log/session.
pub fn get_log_display_title(
    first_prompt: Option<&str>,
    session_id: Option<&str>,
    agent_name: Option<&str>,
    custom_title: Option<&str>,
    summary: Option<&str>,
) -> String {
    // Skip first_prompt if it's an autonomous mode tick tag
    let stripped_first_prompt = first_prompt
        .map(|p| strip_display_tags(p))
        .filter(|s| !s.is_empty());

    agent_name.unwrap_or_default().to_string()
        .chars().chain(if agent_name.map(|s| !s.is_empty()).unwrap_or(false) {
            return agent_name.unwrap().to_string();
        } else {
            "".chars()
        }).collect::<String>();

    if let Some(name) = agent_name {
        if !name.is_empty() { return name.to_string(); }
    }
    if let Some(title) = custom_title {
        if !title.is_empty() { return title.to_string(); }
    }
    if let Some(s) = summary {
        if !s.is_empty() { return s.to_string(); }
    }
    if let Some(fp) = stripped_first_prompt {
        return fp;
    }
    if let Some(id) = session_id {
        if id.len() >= 8 { return id[..8].to_string(); }
        return id.to_string();
    }
    String::new()
}

/// Strip display-unfriendly XML tags from text.
/// Tags like <ide_opened_file>, <command-name> etc. should be removed.
pub fn strip_display_tags(text: &str) -> String {
    // Remove XML-like tags that are not meant for display
    let re = once_cell::sync::Lazy::force(&DISPLAY_TAG_RE);
    re.replace_all(text, "").trim().to_string()
}

static DISPLAY_TAG_RE: once_cell::sync::Lazy<regex::Regex> = once_cell::sync::Lazy::new(|| {
    regex::Regex::new(r"<(?:ide_opened_file|command-name|file_path|path)[^>]*>.*?</(?:ide_opened_file|command-name|file_path|path)>|<(?:ide_opened_file|command-name)[^>]*/?>").unwrap()
});

/// Convert a Date to a filename-safe format.
pub fn date_to_filename(date: &DateTime<Utc>) -> String {
    date.format("%Y-%m-%dT%H-%M-%S%.3f").to_string()
}

/// Get the log directory path.
pub fn get_log_dir() -> PathBuf {
    crate::env_utils::get_claude_config_home_dir().join("logs")
}

/// Log an error to the error log.
/// TODO: Implement persistent error logging.
pub fn log_error(error: &dyn std::fmt::Debug) {
    tracing::error!("{:?}", error);
}

/// Log for debugging (only in debug mode).
pub fn log_for_debugging(msg: &str) {
    tracing::debug!("{}", msg);
}
