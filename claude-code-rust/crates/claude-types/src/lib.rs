// Original TS source: types/ids.ts, types/command.ts, types/permissions.ts, types/logs.ts, types/plugin.ts
// Claude Code Rust Port - Core Type Definitions

pub mod ids;
pub mod permissions;
pub mod logs;
pub mod plugin;
pub mod command;
pub mod message;
pub mod hooks;
pub mod events;

// Re-export commonly used types
pub use ids::{SessionId, AgentId};
pub use permissions::{
    PermissionMode, PermissionBehavior, PermissionRule, PermissionRuleSource,
    PermissionRuleValue, PermissionUpdate, PermissionDecision, PermissionResult,
    ExternalPermissionMode,
};
pub use message::{Message, AssistantMessage, UserMessage};
