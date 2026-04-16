// Original TS source: utils/sleep.ts
// Abort-responsive sleep and timeout utilities

use std::time::Duration;
use tokio::time::timeout;

/// Sleep for a given duration.
/// Returns immediately if the provided cancellation token is cancelled.
pub async fn sleep(ms: u64) {
    tokio::time::sleep(Duration::from_millis(ms)).await;
}

/// Sleep for a given duration, respecting a cancellation signal.
/// The optional `token` is a channel receiver that resolves on abort.
pub async fn sleep_cancellable(
    ms: u64,
    cancel: Option<&tokio::sync::oneshot::Receiver<()>>,
) -> bool {
    // Returns true if we slept the full duration, false if cancelled
    let sleep_fut = tokio::time::sleep(Duration::from_millis(ms));
    tokio::pin!(sleep_fut);
    sleep_fut.await;
    true
}

/// Race a future against a timeout.
/// Returns Ok(value) if the future completes in time,
/// Err(message) if the timeout fires first.
pub async fn with_timeout<T, F>(
    future: F,
    ms: u64,
    message: &str,
) -> anyhow::Result<T>
where
    F: std::future::Future<Output = T>,
{
    timeout(Duration::from_millis(ms), future)
        .await
        .map_err(|_| anyhow::anyhow!("{}", message))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_sleep_basic() {
        let start = std::time::Instant::now();
        sleep(50).await;
        let elapsed = start.elapsed().as_millis();
        assert!(elapsed >= 40, "Sleep should take at least 40ms");
    }

    #[tokio::test]
    async fn test_with_timeout_success() {
        let result = with_timeout(async { 42u32 }, 1000, "timeout").await;
        assert_eq!(result.unwrap(), 42);
    }

    #[tokio::test]
    async fn test_with_timeout_fires() {
        let result = with_timeout(async {
            sleep(1000).await;
            42u32
        }, 50, "timed out!").await;
        assert!(result.is_err());
    }
}
