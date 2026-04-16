// Original TS source: commands/doctor/
// Doctor command - diagnose Claude Code installation

use anyhow::Result;

pub struct DoctorCommand;

impl DoctorCommand {
    pub const NAME: &'static str = "doctor";
    pub const DESCRIPTION: &'static str = "Diagnose and verify your Claude Code installation and settings";

    /// Run diagnostics on the Claude Code installation.
    pub async fn run() -> Result<()> {
        println!("=== Claude Code Doctor ===\n");

        // Check API key
        let api_key_status = if std::env::var("ANTHROPIC_API_KEY").is_ok() {
            "✓ ANTHROPIC_API_KEY is set"
        } else {
            "✗ ANTHROPIC_API_KEY is not set"
        };
        println!("{}", api_key_status);

        // Check config directory
        let config_dir = claude_utils::env_utils::get_claude_config_home_dir();
        if config_dir.exists() {
            println!("✓ Config directory exists: {}", config_dir.display());
        } else {
            println!("✗ Config directory not found: {}", config_dir.display());
        }

        // Check for ripgrep
        if claude_utils::binary_check::is_binary_installed("rg").await {
            println!("✓ ripgrep (rg) is installed");
        } else {
            println!("! ripgrep (rg) not found - grep tool will use fallback");
        }

        // Check for git
        if claude_utils::binary_check::is_binary_installed("git").await {
            println!("✓ git is installed");
        } else {
            println!("✗ git is not installed");
        }

        println!("\nDiagnostics complete.");
        Ok(())
    }
}
