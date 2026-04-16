// Original TS source: services/api/client.ts
// Anthropic API client

use std::collections::HashMap;
use serde::{Deserialize, Serialize};
use anyhow::Result;
use reqwest::Client;

/// API provider type
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ApiProvider {
    Anthropic,
    AwsBedrock,
    Vertex,
    Foundry,
}

/// Configuration for the Anthropic client
#[derive(Debug, Clone)]
pub struct ClientConfig {
    pub api_key: Option<String>,
    pub base_url: String,
    pub max_retries: u32,
    pub timeout_ms: u64,
    pub provider: ApiProvider,
    pub model: Option<String>,
    pub headers: HashMap<String, String>,
}

impl Default for ClientConfig {
    fn default() -> Self {
        Self {
            api_key: std::env::var("ANTHROPIC_API_KEY").ok(),
            base_url: "https://api.anthropic.com".to_string(),
            max_retries: 3,
            timeout_ms: 60_000,
            provider: ApiProvider::Anthropic,
            model: None,
            headers: HashMap::new(),
        }
    }
}

/// Anthropic API client
#[derive(Clone)]
pub struct AnthropicClient {
    pub config: ClientConfig,
    http_client: Client,
}

impl AnthropicClient {
    /// Create a new client with the given configuration
    pub fn new(config: ClientConfig) -> Self {
        let http_client = Client::builder()
            .timeout(std::time::Duration::from_millis(config.timeout_ms))
            .build()
            .expect("Failed to build HTTP client");

        Self { config, http_client }
    }

    /// Create a client from environment variables
    pub fn from_env() -> Self {
        Self::new(ClientConfig::default())
    }

    /// Get the base URL for the current provider
    pub fn base_url(&self) -> &str {
        &self.config.base_url
    }

    /// Build request headers
    pub fn build_headers(&self, extra_headers: Option<&HashMap<String, String>>) -> HashMap<String, String> {
        let mut headers = HashMap::new();

        // Base headers
        if let Some(api_key) = &self.config.api_key {
            headers.insert("x-api-key".to_string(), api_key.clone());
        }
        headers.insert("anthropic-version".to_string(), "2023-06-01".to_string());
        headers.insert("content-type".to_string(), "application/json".to_string());

        // Beta headers
        let betas: Vec<&str> = vec![
            claude_constants::CLAUDE_CODE_20250219_BETA_HEADER,
        ];
        if !betas.is_empty() {
            headers.insert(
                "anthropic-beta".to_string(),
                betas.join(","),
            );
        }

        // Custom headers from config
        for (k, v) in &self.config.headers {
            headers.insert(k.clone(), v.clone());
        }

        // Extra per-request headers
        if let Some(extra) = extra_headers {
            for (k, v) in extra {
                headers.insert(k.clone(), v.clone());
            }
        }

        headers
    }

    /// Send a messages API request
    pub async fn create_message(
        &self,
        request: &serde_json::Value,
    ) -> Result<serde_json::Value> {
        let url = format!("{}/v1/messages", self.config.base_url);
        let headers = self.build_headers(None);

        let mut req = self.http_client.post(&url).json(request);
        for (key, value) in &headers {
            req = req.header(key, value);
        }

        let response = req.send().await?;
        let status = response.status();
        let body: serde_json::Value = response.json().await?;

        if !status.is_success() {
            anyhow::bail!("API error {}: {:?}", status, body);
        }

        Ok(body)
    }

    /// Count tokens for a request
    pub async fn count_tokens(
        &self,
        request: &serde_json::Value,
    ) -> Result<u64> {
        let url = format!("{}/v1/messages/count_tokens", self.config.base_url);
        let headers = self.build_headers(None);

        let mut req = self.http_client.post(&url).json(request);
        for (key, value) in &headers {
            req = req.header(key, value);
        }

        let response = req.send().await?;
        let body: serde_json::Value = response.json().await?;

        body["input_tokens"].as_u64()
            .ok_or_else(|| anyhow::anyhow!("Missing input_tokens in count_tokens response"))
    }
}
