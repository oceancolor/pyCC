// Original TS source: entrypoints/cli.tsx + cli/
// CLI entry point for Claude Code Rust port

use clap::{Parser, Subcommand};
use anyhow::Result;

const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Claude Code - AI coding assistant
#[derive(Parser)]
#[command(
    name = "claude",
    about = "Claude Code - AI coding assistant",
    version = VERSION,
    long_about = None,
)]
struct Cli {
    /// Print version information
    #[arg(short, long)]
    version: bool,

    /// Non-interactive mode: send a single prompt and exit
    #[arg(short, long, value_name = "PROMPT")]
    print: Option<String>,

    /// Resume a previous session
    #[arg(long, value_name = "SESSION_ID")]
    resume: Option<String>,

    /// Continue the most recent session
    #[arg(short, long)]
    continue_session: bool,

    /// System prompt to append
    #[arg(long, value_name = "PROMPT")]
    append_system_prompt: Option<String>,

    /// Permission mode
    #[arg(long, value_name = "MODE", default_value = "default")]
    permission_mode: String,

    /// Output format (text, json, stream-json)
    #[arg(long, value_name = "FORMAT", default_value = "text")]
    output_format: String,

    /// Verbose debug output
    #[arg(long)]
    verbose: bool,

    #[command(subcommand)]
    command: Option<Commands>,
}

/// Available subcommands
#[derive(Subcommand)]
enum Commands {
    /// Diagnose and verify your Claude Code installation
    Doctor,
    /// Open config panel
    Config {
        #[arg(subcommand)]
        action: Option<ConfigAction>,
    },
    /// Clear conversation history
    Clear,
    /// Manage MCP servers
    Mcp {
        #[command(subcommand)]
        action: McpAction,
    },
}

#[derive(Subcommand)]
enum ConfigAction {
    /// Show current configuration
    Show,
    /// Set a configuration value
    Set {
        key: String,
        value: String,
    },
    /// Get a configuration value
    Get {
        key: String,
    },
}

#[derive(Subcommand)]
enum McpAction {
    /// List configured MCP servers
    List,
    /// Add an MCP server
    Add {
        name: String,
        command: String,
        #[arg(trailing_var_arg = true)]
        args: Vec<String>,
    },
    /// Remove an MCP server
    Remove {
        name: String,
    },
}

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize tracing
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive(tracing::Level::WARN.into()),
        )
        .init();

    let cli = Cli::parse();

    // Handle version flag
    if cli.version {
        println!("{} (Claude Code Rust)", VERSION);
        return Ok(());
    }

    // Dispatch subcommands
    match cli.command {
        Some(Commands::Doctor) => {
            claude_commands::doctor::DoctorCommand::run().await?;
        }
        Some(Commands::Config { action }) => {
            match action {
                Some(ConfigAction::Show) => {
                    show_config();
                }
                Some(ConfigAction::Set { key, value }) => {
                    println!("TODO: Set {} = {}", key, value);
                }
                Some(ConfigAction::Get { key }) => {
                    println!("TODO: Get {}", key);
                }
                None => {
                    claude_commands::config::ConfigCommand::run();
                }
            }
        }
        Some(Commands::Clear) => {
            claude_commands::clear::clear_caches();
            println!("Session cleared.");
        }
        Some(Commands::Mcp { action }) => {
            match action {
                McpAction::List => {
                    println!("TODO: List MCP servers from config");
                }
                McpAction::Add { name, command, args } => {
                    println!("TODO: Add MCP server: {} = {} {:?}", name, command, args);
                }
                McpAction::Remove { name } => {
                    println!("TODO: Remove MCP server: {}", name);
                }
            }
        }
        None => {
            // Default: start interactive session or run print mode
            if let Some(prompt) = cli.print {
                run_print_mode(&prompt, &cli.permission_mode, &cli.output_format).await?;
            } else {
                run_interactive_mode(&cli).await?;
            }
        }
    }

    Ok(())
}

fn show_config() {
    let config_dir = claude_utils::env_utils::get_claude_config_home_dir();
    println!("Config directory: {}", config_dir.display());
    println!("API key: {}", if std::env::var("ANTHROPIC_API_KEY").is_ok() { "<set>" } else { "<not set>" });
    println!("Model: {}", std::env::var("CLAUDE_MODEL").unwrap_or_else(|_| "claude-opus-4-5 (default)".to_string()));
}

/// Run in print (non-interactive) mode: send prompt, output response, exit.
async fn run_print_mode(
    prompt: &str,
    _permission_mode: &str,
    output_format: &str,
) -> Result<()> {
    let client = claude_services::api::AnthropicClient::from_env();

    let model = std::env::var("CLAUDE_MODEL")
        .unwrap_or_else(|_| "claude-opus-4-5".to_string());

    let request = serde_json::json!({
        "model": model,
        "max_tokens": 8096,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    });

    let response = client.create_message(&request).await?;

    match output_format {
        "json" => {
            println!("{}", serde_json::to_string_pretty(&response)?);
        }
        _ => {
            // Extract text from response
            if let Some(content) = response["content"].as_array() {
                for block in content {
                    if block["type"] == "text" {
                        if let Some(text) = block["text"].as_str() {
                            println!("{}", text);
                        }
                    }
                }
            }
        }
    }

    Ok(())
}

/// Run in interactive REPL mode.
/// TODO: Implement full interactive TUI using ratatui.
async fn run_interactive_mode(_cli: &Cli) -> Result<()> {
    println!("Claude Code {} (Rust port)", VERSION);
    println!("TODO: Interactive mode with full TUI - use ratatui for terminal UI");
    println!("Hint: Use 'claude --print \"<prompt>\"' for non-interactive usage");
    Ok(())
}
