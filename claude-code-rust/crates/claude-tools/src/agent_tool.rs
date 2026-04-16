// Original TS source: tools/AgentTool/
// Agent tool stub - spawns subagents

pub const AGENT_TOOL_NAME: &str = "Task";
pub const LEGACY_AGENT_TOOL_NAME: &str = "Agent";

use crate::tool_base::{Tool, ToolInputSchema, ToolResult, ToolUseContext};
use anyhow::Result;
use async_trait::async_trait;
use std::collections::HashMap;
use serde::{Deserialize, Serialize};
use serde_json::Value;

/// Input for AgentTool
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentInput {
    pub description: String,
    pub prompt: String,
}

/// The Agent/Task tool that spawns subagents
pub struct AgentTool;

#[async_trait]
impl Tool for AgentTool {
    fn name(&self) -> &str {
        AGENT_TOOL_NAME
    }

    fn description(&self) -> &str {
        "Launch a new agent that has access to the same tools and receives the same system prompt as the main agent. \
        Use this to delegate tasks that can be completed independently, especially multi-step tasks that would \
        benefit from parallel execution."
    }

    fn input_schema(&self) -> ToolInputSchema {
        let mut properties = HashMap::new();
        properties.insert("description".to_string(), serde_json::json!({
            "type": "string",
            "description": "A short (3-5 word) description of the task"
        }));
        properties.insert("prompt".to_string(), serde_json::json!({
            "type": "string",
            "description": "The detailed prompt for the agent"
        }));

        ToolInputSchema {
            schema_type: "object".to_string(),
            properties,
            required: vec!["description".to_string(), "prompt".to_string()],
        }
    }

    async fn execute(&self, input: Value, _context: &ToolUseContext) -> Result<ToolResult> {
        let agent_input: AgentInput = serde_json::from_value(input)?;

        // TODO: Implement full subagent spawning
        // This requires:
        // - Creating a new session/agent context
        // - Running the agent loop with the given prompt
        // - Collecting and returning the result
        Ok(ToolResult::text(format!(
            "TODO: Agent spawning not yet implemented. Task: {}",
            agent_input.description
        )))
    }
}

// ============================================================================
// Sleep Tool
// ============================================================================

pub const SLEEP_TOOL_NAME: &str = "Sleep";

/// Input for SleepTool
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SleepInput {
    pub duration_ms: u64,
}

/// The Sleep tool
pub struct SleepTool;

#[async_trait]
impl Tool for SleepTool {
    fn name(&self) -> &str {
        SLEEP_TOOL_NAME
    }

    fn description(&self) -> &str {
        "Wait for a specified duration. Use when you have nothing to do or are waiting for something."
    }

    fn input_schema(&self) -> ToolInputSchema {
        let mut properties = HashMap::new();
        properties.insert("duration_ms".to_string(), serde_json::json!({
            "type": "number",
            "description": "Duration to sleep in milliseconds"
        }));

        ToolInputSchema {
            schema_type: "object".to_string(),
            properties,
            required: vec!["duration_ms".to_string()],
        }
    }

    async fn execute(&self, input: Value, _context: &ToolUseContext) -> Result<ToolResult> {
        let sleep_input: SleepInput = serde_json::from_value(input)?;
        tokio::time::sleep(std::time::Duration::from_millis(sleep_input.duration_ms)).await;
        Ok(ToolResult::text(format!("Slept for {}ms", sleep_input.duration_ms)))
    }
}
