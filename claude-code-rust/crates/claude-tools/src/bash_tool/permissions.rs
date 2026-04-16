// Original TS source: tools/BashTool/bashPermissions.ts
// Bash tool permissions - simplified Rust stub

use claude_types::permissions::{PermissionResult, PermissionBehavior, PermissionAllowDecision, PermissionDecisionReason};

/// Check if a bash command has permission to run.
/// Returns a PermissionResult indicating allow/deny/ask.
/// TODO: Full implementation requires bash AST parsing, classifier, rule matching etc.
pub async fn bash_tool_has_permission(
    command: &str,
    cwd: &str,
    _always_allow_rules: &[String],
    _always_deny_rules: &[String],
    _is_bypass_permissions: bool,
) -> PermissionResult {
    // Stub: allow all commands by default
    // TODO: Implement full permission checking with:
    // - bash AST parsing (parseForSecurity)
    // - wildcard rule matching
    // - classifier-based checks
    // - path constraint validation
    // - sed command validation
    PermissionResult::Allow(PermissionAllowDecision {
        updated_input: None,
        user_modified: None,
        decision_reason: None,
        tool_use_id: None,
        accept_feedback: None,
    })
}

/// Check if a command matches a wildcard pattern.
pub fn match_wildcard_pattern(pattern: &str, command: &str) -> bool {
    if pattern.ends_with('*') {
        let prefix = &pattern[..pattern.len() - 1];
        command.starts_with(prefix)
    } else {
        pattern == command
    }
}

/// Extract the prefix (base command) from a permission rule.
/// e.g., "git*" → "git", "npm run" → "npm"
pub fn permission_rule_extract_prefix(rule: &str) -> &str {
    if let Some(star_pos) = rule.find('*') {
        let prefix = &rule[..star_pos];
        // Get last non-space segment
        prefix.trim_end()
    } else {
        rule.split_whitespace().next().unwrap_or(rule)
    }
}
