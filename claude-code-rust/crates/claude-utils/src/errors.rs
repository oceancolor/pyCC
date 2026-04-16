// Original TS source: utils/errors.ts
// Error types and utilities

use thiserror::Error;

// ============================================================================
// Error Types
// ============================================================================

#[derive(Debug, Error)]
pub enum ClaudeError {
    #[error("Malformed command: {0}")]
    MalformedCommand(String),

    #[error("Aborted: {0}")]
    Abort(String),

    #[error("Config parse error at {file_path}: {message}")]
    ConfigParse {
        message: String,
        file_path: String,
    },

    #[error("Shell error (code {code}): {stderr}")]
    Shell {
        stdout: String,
        stderr: String,
        code: i32,
        interrupted: bool,
    },
}

#[derive(Debug, Error)]
#[error("Aborted")]
pub struct AbortError(pub Option<String>);

impl AbortError {
    pub fn new(msg: impl Into<String>) -> Self {
        Self(Some(msg.into()))
    }

    pub fn empty() -> Self {
        Self(None)
    }
}

/// Check if an error is an abort error.
pub fn is_abort_error(e: &anyhow::Error) -> bool {
    e.downcast_ref::<AbortError>().is_some()
}

/// Extract a human-readable message from any error.
pub fn error_message(e: &dyn std::fmt::Debug) -> String {
    format!("{:?}", e)
}

/// Check if an IO error means the path is inaccessible.
pub fn is_fs_inaccessible(e: &std::io::Error) -> bool {
    matches!(
        e.kind(),
        std::io::ErrorKind::NotFound
            | std::io::ErrorKind::PermissionDenied
            | std::io::ErrorKind::Other  // ENOTDIR, ELOOP, etc.
    )
}

/// Check if an error has an exact message string.
pub fn has_exact_error_message(e: &anyhow::Error, msg: &str) -> bool {
    e.to_string() == msg
}

/// Get a truncated error stack trace (max N frames).
pub fn short_error_stack(e: &anyhow::Error, max_frames: usize) -> String {
    let full = format!("{:#}", e);
    let lines: Vec<&str> = full.lines().collect();
    if lines.len() <= max_frames + 1 {
        return full;
    }
    lines[..max_frames + 1].join("\n")
}

// ============================================================================
// Reqwest/HTTP error classification
// ============================================================================

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum HttpErrorKind {
    Auth,       // 401/403
    Timeout,    // connection timeout
    Network,    // connection refused / not found
    Http,       // other HTTP error
    Other,      // not an HTTP error
}

pub struct ClassifiedError {
    pub kind: HttpErrorKind,
    pub status: Option<u16>,
    pub message: String,
}

pub fn classify_request_error(e: &reqwest::Error) -> ClassifiedError {
    let message = e.to_string();
    let status = e.status().map(|s| s.as_u16());

    if let Some(status_code) = status {
        if status_code == 401 || status_code == 403 {
            return ClassifiedError { kind: HttpErrorKind::Auth, status, message };
        }
    }

    if e.is_timeout() {
        return ClassifiedError { kind: HttpErrorKind::Timeout, status, message };
    }

    if e.is_connect() {
        return ClassifiedError { kind: HttpErrorKind::Network, status, message };
    }

    if e.is_status() {
        return ClassifiedError { kind: HttpErrorKind::Http, status, message };
    }

    ClassifiedError { kind: HttpErrorKind::Other, status: None, message }
}
