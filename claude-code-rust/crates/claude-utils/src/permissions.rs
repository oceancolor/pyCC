// Original TS source: utils/permissions/PermissionMode.ts, PermissionResult.ts, permissions.ts
// Permission utilities

use claude_types::permissions::{PermissionMode, ExternalPermissionMode, PermissionBehavior, PermissionRule};

// ============================================================================
// Permission Mode Constants
// ============================================================================

pub const PERMISSION_MODES: &[&str] = &[
    "acceptEdits", "bypassPermissions", "default", "dontAsk", "plan", "auto", "bubble"
];

pub const EXTERNAL_PERMISSION_MODES: &[&str] = &[
    "acceptEdits", "bypassPermissions", "default", "dontAsk", "plan"
];

/// Configuration for displaying a permission mode in the UI.
#[derive(Debug, Clone)]
pub struct PermissionModeConfig {
    pub title: &'static str,
    pub short_title: &'static str,
    pub symbol: &'static str,
}

/// Get the display config for a permission mode.
pub fn get_permission_mode_config(mode: &PermissionMode) -> PermissionModeConfig {
    match mode {
        PermissionMode::Default => PermissionModeConfig {
            title: "Normal",
            short_title: "Normal",
            symbol: "◇",
        },
        PermissionMode::Plan => PermissionModeConfig {
            title: "Plan Mode",
            short_title: "Plan",
            symbol: "⏸",
        },
        PermissionMode::AcceptEdits => PermissionModeConfig {
            title: "Accept Edits",
            short_title: "Accept",
            symbol: "✓",
        },
        PermissionMode::DontAsk => PermissionModeConfig {
            title: "Auto Mode",
            short_title: "Auto",
            symbol: "⚡",
        },
        PermissionMode::BypassPermissions => PermissionModeConfig {
            title: "Bypass Permissions",
            short_title: "Bypass",
            symbol: "★",
        },
        PermissionMode::Auto => PermissionModeConfig {
            title: "Auto",
            short_title: "Auto",
            symbol: "→",
        },
        PermissionMode::Bubble => PermissionModeConfig {
            title: "Bubble",
            short_title: "Bubble",
            symbol: "↑",
        },
    }
}

/// Check if a permission mode is the bypass mode.
pub fn is_bypass_permissions_mode(mode: &PermissionMode) -> bool {
    matches!(mode, PermissionMode::BypassPermissions)
}

/// Check if a permission mode requires user prompts.
pub fn mode_requires_prompts(mode: &PermissionMode) -> bool {
    matches!(mode, PermissionMode::Default | PermissionMode::Plan)
}

/// Parse a permission mode string.
pub fn parse_permission_mode(s: &str) -> Option<PermissionMode> {
    match s {
        "acceptEdits" | "accept-edits" => Some(PermissionMode::AcceptEdits),
        "bypassPermissions" | "bypass-permissions" => Some(PermissionMode::BypassPermissions),
        "default" => Some(PermissionMode::Default),
        "dontAsk" | "dont-ask" => Some(PermissionMode::DontAsk),
        "plan" => Some(PermissionMode::Plan),
        "auto" => Some(PermissionMode::Auto),
        "bubble" => Some(PermissionMode::Bubble),
        _ => None,
    }
}

/// Parse an external permission mode string.
pub fn parse_external_permission_mode(s: &str) -> Option<ExternalPermissionMode> {
    match s {
        "acceptEdits" | "accept-edits" => Some(ExternalPermissionMode::AcceptEdits),
        "bypassPermissions" | "bypass-permissions" => Some(ExternalPermissionMode::BypassPermissions),
        "default" => Some(ExternalPermissionMode::Default),
        "dontAsk" | "dont-ask" => Some(ExternalPermissionMode::DontAsk),
        "plan" => Some(ExternalPermissionMode::Plan),
        _ => None,
    }
}
