// Original TS source: utils/uuid.ts
// UUID utilities

use once_cell::sync::Lazy;
use uuid::Uuid;
use regex::Regex;
use claude_types::ids::AgentId;

static UUID_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
        .expect("valid UUID regex")
});

/// Validate a UUID string. Returns None if invalid.
pub fn validate_uuid(maybe_uuid: &str) -> Option<Uuid> {
    if !UUID_REGEX.is_match(&maybe_uuid.to_lowercase()) {
        return None;
    }
    Uuid::parse_str(maybe_uuid).ok()
}

/// Generate a new agent ID with optional label.
/// Format: a{label-}{16 hex chars}
/// Example: aa3f2c1b4d5e6f7a8 or acompact-a3f2c1b4d5e6f7a8
pub fn create_agent_id(label: Option<&str>) -> AgentId {
    let suffix = format!("{:016x}", rand_u64());
    let id = if let Some(label) = label {
        format!("a{}-{}", label, suffix)
    } else {
        format!("a{}", suffix)
    };
    AgentId(id)
}

fn rand_u64() -> u64 {
    // Use uuid v4 for entropy
    let uuid = Uuid::new_v4();
    let bytes = uuid.as_bytes();
    u64::from_le_bytes(bytes[..8].try_into().unwrap_or([0; 8]))
}

/// Generate a new UUID v4.
pub fn generate_uuid() -> Uuid {
    Uuid::new_v4()
}

/// Generate a UUID string.
pub fn generate_uuid_string() -> String {
    Uuid::new_v4().to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_validate_uuid_valid() {
        assert!(validate_uuid("550e8400-e29b-41d4-a716-446655440000").is_some());
    }

    #[test]
    fn test_validate_uuid_invalid() {
        assert!(validate_uuid("not-a-uuid").is_none());
        assert!(validate_uuid("").is_none());
    }

    #[test]
    fn test_create_agent_id() {
        let id = create_agent_id(None);
        assert!(id.0.starts_with('a'));
        assert_eq!(id.0.len(), 17); // 'a' + 16 hex chars

        let id_with_label = create_agent_id(Some("compact"));
        assert!(id_with_label.0.starts_with("acompact-"));
        assert_eq!(id_with_label.0.len(), 1 + 7 + 1 + 16); // 'a' + 'compact' + '-' + 16
    }
}
