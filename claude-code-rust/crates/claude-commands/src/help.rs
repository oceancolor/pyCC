// Original TS source: commands/help/
// Help command

pub struct HelpCommand;

impl HelpCommand {
    pub const NAME: &'static str = "help";
    pub const ALIASES: &'static [&'static str] = &["?"];
    pub const DESCRIPTION: &'static str = "Show help and available commands";

    pub fn run() {
        println!("Claude Code - Available commands:");
        println!();
        println!("  /help             Show this help");
        println!("  /version          Show version");
        println!("  /config           Manage configuration");
        println!("  /doctor           Diagnose installation");
        println!("  /clear            Clear conversation history");
        println!("  /compact          Compact conversation context");
        println!("  /cost             Show token usage and cost");
        println!("  /status           Show current status");
        println!("  /resume           Resume a previous session");
        println!("  /mcp              Manage MCP servers");
        println!("  /exit, /quit      Exit Claude Code");
    }
}
