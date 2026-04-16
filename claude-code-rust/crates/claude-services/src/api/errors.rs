// Original TS source: services/api/errors.ts
// API error types

use thiserror::Error;

#[derive(Debug, Error)]
pub enum ApiError {
    #[error("HTTP error {status}: {message}")]
    Http { status: u16, message: String },

    #[error("Rate limit exceeded. Retry after {retry_after_secs}s")]
    RateLimit { retry_after_secs: Option<u64> },

    #[error("Authentication failed: {message}")]
    Unauthorized { message: String },

    #[error("Request cancelled")]
    Cancelled,

    #[error("Network error: {0}")]
    Network(#[from] reqwest::Error),

    #[error("Parse error: {0}")]
    Parse(#[from] serde_json::Error),

    #[error("Unknown error: {message}")]
    Unknown { message: String },
}

impl ApiError {
    pub fn is_retryable(&self) -> bool {
        matches!(self, ApiError::Http { status, .. } if *status >= 500 || *status == 429)
            || matches!(self, ApiError::RateLimit { .. })
            || matches!(self, ApiError::Network(_))
    }
}
