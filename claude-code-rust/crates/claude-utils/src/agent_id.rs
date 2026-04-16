// Original TS source: utils/agentId.ts
// Agent ID formatting, parsing, and request ID utilities

/// Parsed components of an agent ID
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AgentIdParts {
    pub agent_name: String,
    pub team_name: String,
}

/// Parsed components of a request ID
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RequestIdParts {
    pub request_type: String,
    pub timestamp: u64,
    pub agent_id: String,
}

/// Format an agent ID as `agentName@teamName`.
pub fn format_agent_id(agent_name: &str, team_name: &str) -> String {
    format!("{}@{}", agent_name, team_name)
}

/// Parse an agent ID into its components.
/// Returns None if the ID doesn't contain the @ separator.
pub fn parse_agent_id(agent_id: &str) -> Option<AgentIdParts> {
    let at_index = agent_id.find('@')?;
    Some(AgentIdParts {
        agent_name: agent_id[..at_index].to_string(),
        team_name: agent_id[at_index + 1..].to_string(),
    })
}

/// Generate a request ID in format `{requestType}-{timestamp}@{agentId}`.
pub fn generate_request_id(request_type: &str, agent_id: &str) -> String {
    let timestamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64;
    format!("{}-{}@{}", request_type, timestamp, agent_id)
}

/// Parse a request ID into its components.
/// Returns None if the request ID doesn't match the expected format.
pub fn parse_request_id(request_id: &str) -> Option<RequestIdParts> {
    let at_index = request_id.find('@')?;
    let prefix = &request_id[..at_index];
    let agent_id = request_id[at_index + 1..].to_string();

    let last_dash_index = prefix.rfind('-')?;
    let request_type = prefix[..last_dash_index].to_string();
    let timestamp_str = &prefix[last_dash_index + 1..];
    let timestamp = timestamp_str.parse::<u64>().ok()?;

    Some(RequestIdParts { request_type, timestamp, agent_id })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_format_agent_id() {
        assert_eq!(format_agent_id("team-lead", "my-project"), "team-lead@my-project");
    }

    #[test]
    fn test_parse_agent_id() {
        let parsed = parse_agent_id("researcher@my-project").unwrap();
        assert_eq!(parsed.agent_name, "researcher");
        assert_eq!(parsed.team_name, "my-project");
    }

    #[test]
    fn test_parse_agent_id_no_at() {
        assert!(parse_agent_id("no-at-sign").is_none());
    }

    #[test]
    fn test_parse_request_id() {
        let parsed = parse_request_id("shutdown-1702500000000@researcher@my-project").unwrap();
        assert_eq!(parsed.request_type, "shutdown");
        assert_eq!(parsed.timestamp, 1702500000000);
        assert_eq!(parsed.agent_id, "researcher@my-project");
    }
}
