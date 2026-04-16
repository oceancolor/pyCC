// Original TS source: commands/status/
// Status command - show current session status

use anyhow::Result;

pub struct StatusCommand;

impl StatusCommand {
    pub const NAME: &'static str = "status";
    pub const DESCRIPTION: &'static str = "Show current session status";

    pub fn run() {
        let cwd = std::env::current_dir()
            .map(|p| p.to_string_lossy().to_string())
            .unwrap_or_else(|_| "<unknown>".to_string());

        let api_key_status = if std::env::var("ANTHROPIC_API_KEY").is_ok() {
            "✓ API key set"
        } else {
            "✗ API key not set"
        };

        let model = std::env::var("ANTHROPIC_MODEL")
            .or_else(|_| std::env::var("CLAUDE_MODEL"))
            .unwrap_or_else(|_| "claude-opus-4-6 (default)".to_string());

        println!("=== Claude Code Status ===");
        println!("Working directory: {}", cwd);
        println!("Model: {}", model);
        println!("Auth: {}", api_key_status);
        println!("Version: {}", env!("CARGO_PKG_VERSION"));
    }
}
