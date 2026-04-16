// Original TS source: constants/product.ts
// Product URLs and remote session helpers

pub const PRODUCT_URL: &str = "https://claude.com/claude-code";
pub const CLAUDE_AI_BASE_URL: &str = "https://claude.ai";
pub const CLAUDE_AI_STAGING_BASE_URL: &str = "https://claude-ai.staging.ant.dev";
pub const CLAUDE_AI_LOCAL_BASE_URL: &str = "http://localhost:4000";

/// Determine if we're in a staging environment for remote sessions.
pub fn is_remote_session_staging(session_id: Option<&str>, ingress_url: Option<&str>) -> bool {
    session_id.map_or(false, |id| id.contains("_staging_"))
        || ingress_url.map_or(false, |url| url.contains("staging"))
}

/// Determine if we're in a local-dev environment for remote sessions.
pub fn is_remote_session_local(session_id: Option<&str>, ingress_url: Option<&str>) -> bool {
    session_id.map_or(false, |id| id.contains("_local_"))
        || ingress_url.map_or(false, |url| url.contains("localhost"))
}

/// Get the base URL for Claude AI based on environment.
pub fn get_claude_ai_base_url(session_id: Option<&str>, ingress_url: Option<&str>) -> &'static str {
    if is_remote_session_local(session_id, ingress_url) {
        return CLAUDE_AI_LOCAL_BASE_URL;
    }
    if is_remote_session_staging(session_id, ingress_url) {
        return CLAUDE_AI_STAGING_BASE_URL;
    }
    CLAUDE_AI_BASE_URL
}

/// Get the full session URL for a remote session.
pub fn get_remote_session_url(session_id: &str, ingress_url: Option<&str>) -> String {
    let compat_id = to_compat_session_id(session_id);
    let base_url = get_claude_ai_base_url(Some(&compat_id), ingress_url);
    format!("{}/code/{}", base_url, compat_id)
}

/// Convert session ID to compat format (cse_ → session_).
/// TODO: This is a temporary shim; remove when server handles cse_ IDs natively.
pub fn to_compat_session_id(session_id: &str) -> String {
    if session_id.starts_with("cse_") {
        format!("session_{}", &session_id[4..])
    } else {
        session_id.to_string()
    }
}
