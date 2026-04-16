// Original TS source: types/plugin.ts
// Plugin system types

use std::collections::HashMap;
use serde::{Deserialize, Serialize};

/// Definition for a built-in plugin
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BuiltinPluginDefinition {
    pub name: String,
    pub description: String,
    pub version: Option<String>,
    pub default_enabled: Option<bool>,
}

/// Plugin repository configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PluginRepository {
    pub url: String,
    pub branch: String,
    pub last_updated: Option<String>,
    pub commit_sha: Option<String>,
}

/// Plugin configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PluginConfig {
    pub repositories: HashMap<String, PluginRepository>,
}

/// A loaded plugin
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LoadedPlugin {
    pub name: String,
    pub path: String,
    pub source: String,
    pub repository: String,
    pub enabled: Option<bool>,
    pub is_builtin: Option<bool>,
    pub sha: Option<String>,
    pub commands_path: Option<String>,
    pub commands_paths: Option<Vec<String>>,
    pub agents_path: Option<String>,
    pub agents_paths: Option<Vec<String>>,
    pub skills_path: Option<String>,
    pub skills_paths: Option<Vec<String>>,
    pub output_styles_path: Option<String>,
    pub output_styles_paths: Option<Vec<String>>,
    pub mcp_servers: Option<HashMap<String, serde_json::Value>>,
    pub lsp_servers: Option<HashMap<String, serde_json::Value>>,
    pub settings: Option<HashMap<String, serde_json::Value>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum PluginComponent {
    Commands,
    Agents,
    Skills,
    Hooks,
    OutputStyles,
}

/// Plugin error discriminated union
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "kebab-case")]
pub enum PluginError {
    PathNotFound {
        source: String,
        plugin: Option<String>,
        path: String,
        component: PluginComponent,
    },
    GitAuthFailed {
        source: String,
        plugin: Option<String>,
        git_url: String,
        auth_type: GitAuthType,
    },
    GitTimeout {
        source: String,
        plugin: Option<String>,
        git_url: String,
        operation: GitOperation,
    },
    NetworkError {
        source: String,
        plugin: Option<String>,
        url: String,
        details: Option<String>,
    },
    ManifestParseError {
        source: String,
        plugin: Option<String>,
        manifest_path: String,
        parse_error: String,
    },
    ManifestValidationError {
        source: String,
        plugin: Option<String>,
        manifest_path: String,
        validation_errors: Vec<String>,
    },
    PluginNotFound {
        source: String,
        plugin_id: String,
        marketplace: String,
    },
    MarketplaceNotFound {
        source: String,
        marketplace: String,
        available_marketplaces: Vec<String>,
    },
    MarketplaceLoadFailed {
        source: String,
        marketplace: String,
        reason: String,
    },
    McpConfigInvalid {
        source: String,
        plugin: String,
        server_name: String,
        validation_error: String,
    },
    McpServerSuppressedDuplicate {
        source: String,
        plugin: String,
        server_name: String,
        duplicate_of: String,
    },
    LspConfigInvalid {
        source: String,
        plugin: String,
        server_name: String,
        validation_error: String,
    },
    HookLoadFailed {
        source: String,
        plugin: String,
        hook_path: String,
        reason: String,
    },
    ComponentLoadFailed {
        source: String,
        plugin: String,
        component: PluginComponent,
        path: String,
        reason: String,
    },
    McpbDownloadFailed {
        source: String,
        plugin: String,
        url: String,
        reason: String,
    },
    McpbExtractFailed {
        source: String,
        plugin: String,
        mcpb_path: String,
        reason: String,
    },
    McpbInvalidManifest {
        source: String,
        plugin: String,
        mcpb_path: String,
        validation_error: String,
    },
    LspServerStartFailed {
        source: String,
        plugin: String,
        server_name: String,
        reason: String,
    },
    LspServerCrashed {
        source: String,
        plugin: String,
        server_name: String,
        exit_code: Option<i32>,
        signal: Option<String>,
    },
    LspRequestTimeout {
        source: String,
        plugin: String,
        server_name: String,
        method: String,
        timeout_ms: u64,
    },
    LspRequestFailed {
        source: String,
        plugin: String,
        server_name: String,
        method: String,
        error: String,
    },
    MarketplaceBlockedByPolicy {
        source: String,
        plugin: Option<String>,
        marketplace: String,
        blocked_by_blocklist: Option<bool>,
        allowed_sources: Vec<String>,
    },
    DependencyUnsatisfied {
        source: String,
        plugin: String,
        dependency: String,
        reason: DependencyUnsatisfiedReason,
    },
    PluginCacheMiss {
        source: String,
        plugin: String,
        install_path: String,
    },
    GenericError {
        source: String,
        plugin: Option<String>,
        error: String,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum GitAuthType {
    Ssh,
    Https,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum GitOperation {
    Clone,
    Pull,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum DependencyUnsatisfiedReason {
    NotEnabled,
    NotFound,
}

impl PluginError {
    /// Get a display message from any PluginError
    pub fn display_message(&self) -> String {
        match self {
            PluginError::GenericError { error, .. } => error.clone(),
            PluginError::PathNotFound { path, component, .. } => {
                format!("Path not found: {} ({:?})", path, component)
            }
            PluginError::GitAuthFailed { auth_type, git_url, .. } => {
                format!("Git authentication failed ({:?}): {}", auth_type, git_url)
            }
            PluginError::GitTimeout { operation, git_url, .. } => {
                format!("Git {:?} timeout: {}", operation, git_url)
            }
            PluginError::NetworkError { url, details, .. } => {
                if let Some(d) = details {
                    format!("Network error: {} - {}", url, d)
                } else {
                    format!("Network error: {}", url)
                }
            }
            PluginError::ManifestParseError { parse_error, .. } => {
                format!("Manifest parse error: {}", parse_error)
            }
            PluginError::ManifestValidationError { validation_errors, .. } => {
                format!("Manifest validation failed: {}", validation_errors.join(", "))
            }
            PluginError::PluginNotFound { plugin_id, marketplace, .. } => {
                format!("Plugin {} not found in marketplace {}", plugin_id, marketplace)
            }
            PluginError::MarketplaceNotFound { marketplace, .. } => {
                format!("Marketplace {} not found", marketplace)
            }
            PluginError::MarketplaceLoadFailed { marketplace, reason, .. } => {
                format!("Marketplace {} failed to load: {}", marketplace, reason)
            }
            PluginError::McpConfigInvalid { server_name, validation_error, .. } => {
                format!("MCP server {} invalid: {}", server_name, validation_error)
            }
            PluginError::McpServerSuppressedDuplicate { server_name, duplicate_of, .. } => {
                let dup = if duplicate_of.starts_with("plugin:") {
                    format!("server provided by plugin \"{}\"", &duplicate_of[7..])
                } else {
                    format!("already-configured \"{}\"", duplicate_of)
                };
                format!("MCP server \"{}\" skipped — same command/URL as {}", server_name, dup)
            }
            PluginError::HookLoadFailed { reason, .. } => {
                format!("Hook load failed: {}", reason)
            }
            PluginError::ComponentLoadFailed { component, path, reason, .. } => {
                format!("{:?} load failed from {}: {}", component, path, reason)
            }
            PluginError::LspConfigInvalid { plugin, server_name, validation_error, .. } => {
                format!("Plugin \"{}\" has invalid LSP server config for \"{}\": {}", plugin, server_name, validation_error)
            }
            PluginError::LspServerStartFailed { plugin, server_name, reason, .. } => {
                format!("Plugin \"{}\" failed to start LSP server \"{}\": {}", plugin, server_name, reason)
            }
            PluginError::LspServerCrashed { plugin, server_name, exit_code, signal, .. } => {
                if let Some(sig) = signal {
                    format!("Plugin \"{}\" LSP server \"{}\" crashed with signal {}", plugin, server_name, sig)
                } else {
                    format!("Plugin \"{}\" LSP server \"{}\" crashed with exit code {}", 
                        plugin, server_name, exit_code.map_or("unknown".to_string(), |c| c.to_string()))
                }
            }
            PluginError::LspRequestTimeout { plugin, server_name, method, timeout_ms, .. } => {
                format!("Plugin \"{}\" LSP server \"{}\" timed out on {} request after {}ms", plugin, server_name, method, timeout_ms)
            }
            PluginError::LspRequestFailed { plugin, server_name, method, error, .. } => {
                format!("Plugin \"{}\" LSP server \"{}\" {} request failed: {}", plugin, server_name, method, error)
            }
            PluginError::MarketplaceBlockedByPolicy { marketplace, blocked_by_blocklist, .. } => {
                if blocked_by_blocklist.unwrap_or(false) {
                    format!("Marketplace '{}' is blocked by enterprise policy", marketplace)
                } else {
                    format!("Marketplace '{}' is not in the allowed marketplace list", marketplace)
                }
            }
            PluginError::DependencyUnsatisfied { dependency, reason, .. } => {
                let hint = match reason {
                    DependencyUnsatisfiedReason::NotEnabled => "disabled — enable it or remove the dependency",
                    DependencyUnsatisfiedReason::NotFound => "not found in any configured marketplace",
                };
                format!("Dependency \"{}\" is {}", dependency, hint)
            }
            PluginError::PluginCacheMiss { plugin, install_path, .. } => {
                format!("Plugin \"{}\" not cached at {} — run /plugins to refresh", plugin, install_path)
            }
            PluginError::McpbDownloadFailed { url, reason, .. } => {
                format!("Failed to download MCPB from {}: {}", url, reason)
            }
            PluginError::McpbExtractFailed { mcpb_path, reason, .. } => {
                format!("Failed to extract MCPB {}: {}", mcpb_path, reason)
            }
            PluginError::McpbInvalidManifest { mcpb_path, validation_error, .. } => {
                format!("MCPB manifest invalid at {}: {}", mcpb_path, validation_error)
            }
        }
    }
}

/// Result of loading plugins
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PluginLoadResult {
    pub enabled: Vec<LoadedPlugin>,
    pub disabled: Vec<LoadedPlugin>,
    pub errors: Vec<PluginError>,
}
