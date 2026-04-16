// Original TS source: tools/
// Tool implementations

pub mod bash_tool;
pub mod file_read_tool;
pub mod file_write_tool;
pub mod file_edit_tool;
pub mod glob_tool;
pub mod grep_tool;
pub mod shared;
pub mod tool_base;
pub mod agent_tool;

// Re-export tool names
pub use bash_tool::BASH_TOOL_NAME;
pub use file_read_tool::FILE_READ_TOOL_NAME;
pub use file_write_tool::FILE_WRITE_TOOL_NAME;
pub use file_edit_tool::FILE_EDIT_TOOL_NAME;
pub use glob_tool::GLOB_TOOL_NAME;
pub use grep_tool::GREP_TOOL_NAME;
pub use agent_tool::{AGENT_TOOL_NAME, LEGACY_AGENT_TOOL_NAME, SLEEP_TOOL_NAME};

// Re-export the Tool trait for convenience
pub use tool_base::{Tool, ToolDefinition, ToolInputSchema, ToolResult, ToolUseContext};
