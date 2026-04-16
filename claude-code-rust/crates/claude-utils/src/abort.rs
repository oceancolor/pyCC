// 原始 TS: utils/abortController.ts
//! Abort signal / cancellation token utilities.
//!
//! Rust equivalent uses tokio CancellationToken from the `tokio-util` crate.
//! The WeakRef memory-safety pattern from JS is handled naturally by Rust's
//! ownership model.

use std::sync::Arc;
use tokio_util::sync::CancellationToken;

/// A cancellation token that can be shared across tasks.
/// Equivalent to AbortController in TypeScript.
#[derive(Clone, Debug)]
pub struct AbortController {
    token: CancellationToken,
}

impl AbortController {
    /// Create a new AbortController.
    pub fn new() -> Self {
        Self {
            token: CancellationToken::new(),
        }
    }

    /// Get the signal (read-only view of cancellation state).
    pub fn signal(&self) -> AbortSignal {
        AbortSignal {
            token: self.token.clone(),
        }
    }

    /// Abort / cancel this controller.
    pub fn abort(&self) {
        self.token.cancel();
    }

    /// Whether this controller has been aborted.
    pub fn is_aborted(&self) -> bool {
        self.token.is_cancelled()
    }
}

impl Default for AbortController {
    fn default() -> Self {
        Self::new()
    }
}

/// Read-only view of an AbortController's cancellation state.
/// Equivalent to AbortSignal in TypeScript.
#[derive(Clone, Debug)]
pub struct AbortSignal {
    token: CancellationToken,
}

impl AbortSignal {
    /// Whether the signal has been aborted.
    pub fn is_aborted(&self) -> bool {
        self.token.is_cancelled()
    }

    /// Wait until this signal is aborted.
    pub async fn cancelled(&self) {
        self.token.cancelled().await;
    }

    /// Get the underlying CancellationToken for use with tokio::select!
    pub fn cancellation_token(&self) -> &CancellationToken {
        &self.token
    }
}

/// Create a child AbortController that aborts when its parent aborts.
/// Aborting the child does NOT affect the parent.
///
/// Memory-safe by construction in Rust — no WeakRef needed.
pub fn create_child_abort_controller(parent: &AbortController) -> AbortController {
    // Fast path: parent already aborted
    if parent.is_aborted() {
        let child = AbortController::new();
        child.abort();
        return child;
    }

    let child_token = parent.token.child_token();
    AbortController {
        token: child_token,
    }
}

/// A shared, reference-counted AbortController.
/// Useful when multiple tasks need to share the same controller.
pub type SharedAbortController = Arc<AbortController>;

/// Create a new shared AbortController.
pub fn create_shared_abort_controller() -> SharedAbortController {
    Arc::new(AbortController::new())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_abort_controller_basic() {
        let ctrl = AbortController::new();
        assert!(!ctrl.is_aborted());
        assert!(!ctrl.signal().is_aborted());

        ctrl.abort();
        assert!(ctrl.is_aborted());
        assert!(ctrl.signal().is_aborted());
    }

    #[test]
    fn test_child_abort_controller() {
        let parent = AbortController::new();
        let child = create_child_abort_controller(&parent);
        assert!(!child.is_aborted());

        parent.abort();
        assert!(child.is_aborted());
    }

    #[test]
    fn test_child_controller_independent() {
        let parent = AbortController::new();
        let child = create_child_abort_controller(&parent);
        child.abort();
        // Child abort should not affect parent
        assert!(!parent.is_aborted());
    }

    #[test]
    fn test_already_aborted_parent() {
        let parent = AbortController::new();
        parent.abort();
        let child = create_child_abort_controller(&parent);
        assert!(child.is_aborted());
    }
}
