// Original TS source: commands/version.ts
// Version command

use anyhow::Result;

pub struct VersionCommand;

impl VersionCommand {
    pub const NAME: &'static str = "version";
    pub const DESCRIPTION: &'static str = "Show version information";

    pub fn run() {
        let version = env!("CARGO_PKG_VERSION");
        println!("Claude Code (Rust) {}", version);
    }
}
