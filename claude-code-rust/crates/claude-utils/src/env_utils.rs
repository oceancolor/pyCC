// Original TS source: utils/envUtils.ts
// Environment variable utilities and config path helpers

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use once_cell::sync::Lazy;
use std::sync::Mutex;

/// Get the Claude config home directory.
/// Respects CLAUDE_CONFIG_DIR env var, defaults to ~/.claude
pub fn get_claude_config_home_dir() -> PathBuf {
    if let Ok(dir) = std::env::var("CLAUDE_CONFIG_DIR") {
        PathBuf::from(dir)
    } else {
        let home = dirs_home_dir().unwrap_or_else(|| PathBuf::from("/tmp"));
        home.join(".claude")
    }
}

fn dirs_home_dir() -> Option<PathBuf> {
    // Use HOME env var on Unix, USERPROFILE on Windows
    #[cfg(unix)]
    return std::env::var("HOME").ok().map(PathBuf::from);
    #[cfg(windows)]
    return std::env::var("USERPROFILE").ok().map(PathBuf::from);
    #[allow(unreachable_code)]
    None
}

/// Get the teams directory.
pub fn get_teams_dir() -> PathBuf {
    get_claude_config_home_dir().join("teams")
}

/// Check if a NODE_OPTIONS-style string contains a specific flag.
pub fn has_node_option(flag: &str) -> bool {
    std::env::var("NODE_OPTIONS")
        .map(|opts| opts.split_whitespace().any(|o| o == flag))
        .unwrap_or(false)
}

/// Check if an environment variable is truthy (1, true, yes, on).
pub fn is_env_truthy(env_var: Option<&str>) -> bool {
    match env_var {
        None | Some("") => false,
        Some(v) => matches!(v.to_lowercase().trim(), "1" | "true" | "yes" | "on"),
    }
}

/// Check if an environment variable is defined-falsy (0, false, no, off).
pub fn is_env_defined_falsy(env_var: Option<&str>) -> bool {
    match env_var {
        None => false,
        Some("") => false,
        Some(v) => matches!(v.to_lowercase().trim(), "0" | "false" | "no" | "off"),
    }
}

/// Check if running in bare mode (--bare flag or CLAUDE_CODE_SIMPLE env var).
pub fn is_bare_mode() -> bool {
    is_env_truthy(std::env::var("CLAUDE_CODE_SIMPLE").ok().as_deref())
        || std::env::args().any(|a| a == "--bare")
}

/// Parse array of KEY=VALUE env var strings into a HashMap.
pub fn parse_env_vars(raw_env_args: &[String]) -> Result<HashMap<String, String>, String> {
    let mut parsed = HashMap::new();
    for env_str in raw_env_args {
        if let Some(eq_pos) = env_str.find('=') {
            let key = &env_str[..eq_pos];
            let value = &env_str[eq_pos + 1..];
            if key.is_empty() {
                return Err(format!(
                    "Invalid environment variable format: {}, expected KEY=VALUE",
                    env_str
                ));
            }
            parsed.insert(key.to_string(), value.to_string());
        } else {
            return Err(format!(
                "Invalid environment variable format: {}, expected KEY=VALUE",
                env_str
            ));
        }
    }
    Ok(parsed)
}

/// Get the AWS region with fallback to default.
pub fn get_aws_region() -> String {
    std::env::var("AWS_REGION")
        .or_else(|_| std::env::var("AWS_DEFAULT_REGION"))
        .unwrap_or_else(|_| "us-east-1".to_string())
}

/// Get the default Vertex AI region.
pub fn get_default_vertex_region() -> String {
    std::env::var("CLOUD_ML_REGION").unwrap_or_else(|_| "us-east5".to_string())
}

// @[MODEL LAUNCH]: Add a Vertex region override env var for the new model.
const VERTEX_REGION_OVERRIDES: &[(&str, &str)] = &[
    ("claude-haiku-4-5", "VERTEX_REGION_CLAUDE_HAIKU_4_5"),
    ("claude-3-5-haiku", "VERTEX_REGION_CLAUDE_3_5_HAIKU"),
    ("claude-3-5-sonnet", "VERTEX_REGION_CLAUDE_3_5_SONNET"),
    ("claude-3-7-sonnet", "VERTEX_REGION_CLAUDE_3_7_SONNET"),
    ("claude-opus-4-1", "VERTEX_REGION_CLAUDE_4_1_OPUS"),
    ("claude-opus-4", "VERTEX_REGION_CLAUDE_4_0_OPUS"),
    ("claude-sonnet-4-6", "VERTEX_REGION_CLAUDE_4_6_SONNET"),
    ("claude-sonnet-4-5", "VERTEX_REGION_CLAUDE_4_5_SONNET"),
    ("claude-sonnet-4", "VERTEX_REGION_CLAUDE_4_0_SONNET"),
];

/// Get the Vertex AI region for a specific model.
pub fn get_vertex_region_for_model(model: Option<&str>) -> String {
    if let Some(model) = model {
        for (prefix, env_var) in VERTEX_REGION_OVERRIDES {
            if model.starts_with(prefix) {
                return std::env::var(env_var).unwrap_or_else(|_| get_default_vertex_region());
            }
        }
    }
    get_default_vertex_region()
}

/// Check if bash commands should maintain project working directory.
pub fn should_maintain_project_working_dir() -> bool {
    is_env_truthy(
        std::env::var("CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR").ok().as_deref(),
    )
}

/// Check if running on Homespace (ant-internal cloud environment).
pub fn is_running_on_homespace() -> bool {
    std::env::var("USER_TYPE").ok().as_deref() == Some("ant")
        && is_env_truthy(std::env::var("COO_RUNNING_ON_HOMESPACE").ok().as_deref())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_env_truthy() {
        assert!(is_env_truthy(Some("1")));
        assert!(is_env_truthy(Some("true")));
        assert!(is_env_truthy(Some("yes")));
        assert!(is_env_truthy(Some("on")));
        assert!(!is_env_truthy(Some("0")));
        assert!(!is_env_truthy(None));
    }

    #[test]
    fn test_parse_env_vars() {
        let args = vec!["KEY1=value1".to_string(), "KEY2=value=with=equals".to_string()];
        let result = parse_env_vars(&args).unwrap();
        assert_eq!(result["KEY1"], "value1");
        assert_eq!(result["KEY2"], "value=with=equals");
    }
}
