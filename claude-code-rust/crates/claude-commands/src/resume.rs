// Original TS source: commands/resume/
// Resume command - continue a previous session

use anyhow::Result;

pub struct ResumeCommand;

impl ResumeCommand {
    pub const NAME: &'static str = "resume";
    pub const DESCRIPTION: &'static str = "Resume a previous session";

    /// List available sessions to resume.
    pub async fn list_sessions() -> Result<Vec<SessionInfo>> {
        let log_dir = claude_utils::env_utils::get_claude_config_home_dir().join("projects");

        if !log_dir.exists() {
            return Ok(vec![]);
        }

        let mut sessions = Vec::new();

        // Walk through project directories
        let mut dir_entries = tokio::fs::read_dir(&log_dir).await?;
        while let Some(entry) = dir_entries.next_entry().await? {
            if entry.path().is_dir() {
                let project_dir = entry.path();
                // TODO: Parse .jsonl session files
                // For now, just collect directory names as session IDs
                sessions.push(SessionInfo {
                    session_id: project_dir.file_name()
                        .unwrap_or_default()
                        .to_string_lossy()
                        .to_string(),
                    first_message: None,
                    created_at: None,
                });
            }
        }

        Ok(sessions)
    }
}

#[derive(Debug, Clone)]
pub struct SessionInfo {
    pub session_id: String,
    pub first_message: Option<String>,
    pub created_at: Option<chrono::DateTime<chrono::Utc>>,
}
