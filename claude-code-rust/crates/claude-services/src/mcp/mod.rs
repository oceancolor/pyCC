// Original TS source: services/mcp/
// MCP (Model Context Protocol) service stub

/// MCP server configuration
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct McpServerConfig {
    pub command: Option<String>,
    pub args: Option<Vec<String>>,
    pub env: Option<std::collections::HashMap<String, String>>,
    pub url: Option<String>,
    pub headers: Option<std::collections::HashMap<String, String>>,
}

/// Notify VS Code of a file update via MCP.
/// TODO: Stub - implement VS Code SDK MCP integration.
pub async fn notify_vscode_file_updated(_file_path: &str) {
    // TODO: Implement VS Code notification
}
