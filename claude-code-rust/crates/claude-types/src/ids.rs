// Original TS source: types/ids.ts
// Branded ID types for sessions and agents

use std::fmt;

/// A session ID uniquely identifies a Claude Code session.
#[derive(Debug, Clone, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
#[serde(transparent)]
pub struct SessionId(pub String);

/// An agent ID uniquely identifies a subagent within a session.
#[derive(Debug, Clone, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
#[serde(transparent)]
pub struct AgentId(pub String);

impl SessionId {
    pub fn new(id: impl Into<String>) -> Self {
        Self(id.into())
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl AgentId {
    pub fn new(id: impl Into<String>) -> Self {
        Self(id.into())
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl fmt::Display for SessionId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl fmt::Display for AgentId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl From<String> for SessionId {
    fn from(s: String) -> Self {
        Self(s)
    }
}

impl From<String> for AgentId {
    fn from(s: String) -> Self {
        Self(s)
    }
}

// Pattern: `a` + optional `<label>-` + 16 hex chars
static AGENT_ID_PATTERN: once_cell::sync::Lazy<regex::Regex> = once_cell::sync::Lazy::new(|| {
    regex::Regex::new(r"^a(?:.+-)?[0-9a-f]{16}$").expect("valid regex")
});

/// Validate and return an AgentId from a string.
/// Returns None if the string doesn't match the expected pattern.
pub fn to_agent_id(s: &str) -> Option<AgentId> {
    if AGENT_ID_PATTERN.is_match(s) {
        Some(AgentId(s.to_string()))
    } else {
        None
    }
}

/// Cast a raw string to SessionId.
pub fn as_session_id(id: impl Into<String>) -> SessionId {
    SessionId(id.into())
}

/// Cast a raw string to AgentId.
pub fn as_agent_id(id: impl Into<String>) -> AgentId {
    AgentId(id.into())
}
