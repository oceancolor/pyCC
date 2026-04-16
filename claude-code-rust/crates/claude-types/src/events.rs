// Original TS source: types/generated/events_mono/claude_code/v1/...
// Environment metadata and telemetry event types

use serde::{Deserialize, Serialize};

/// GitHub Actions metadata
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct GitHubActionsMetadata {
    pub actor_id: Option<String>,
    pub repository_id: Option<String>,
    pub repository_owner_id: Option<String>,
}

/// Environment and runtime metadata
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct EnvironmentMetadata {
    pub platform: Option<String>,
    pub node_version: Option<String>,
    pub terminal: Option<String>,
    pub package_managers: Option<String>,
    pub runtimes: Option<String>,
    pub is_running_with_bun: Option<bool>,
    pub is_ci: Option<bool>,
    pub is_claubbit: Option<bool>,
    pub is_github_action: Option<bool>,
    pub is_claude_code_action: Option<bool>,
    pub is_claude_ai_auth: Option<bool>,
    pub version: Option<String>,
    pub github_event_name: Option<String>,
    pub github_actions_runner_environment: Option<String>,
    pub github_actions_runner_os: Option<String>,
    pub github_action_ref: Option<String>,
    pub wsl_version: Option<String>,
    pub github_actions_metadata: Option<GitHubActionsMetadata>,
    pub arch: Option<String>,
    pub is_claude_code_remote: Option<bool>,
    pub remote_environment_type: Option<String>,
    pub claude_code_container_id: Option<String>,
    pub claude_code_remote_session_id: Option<String>,
    pub tags: Option<Vec<String>>,
    pub deployment_environment: Option<String>,
    pub is_conductor: Option<bool>,
    pub version_base: Option<String>,
    pub coworker_type: Option<String>,
    pub build_time: Option<String>,
    pub is_local_agent_mode: Option<bool>,
    pub linux_distro_id: Option<String>,
    pub linux_distro_version: Option<String>,
    pub linux_kernel: Option<String>,
    pub vcs: Option<String>,
    pub platform_raw: Option<String>,
}
