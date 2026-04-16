// Original TS source: services/notifier.ts
// Terminal/OS notification service

use anyhow::Result;

/// Notification options
#[derive(Debug, Clone)]
pub struct NotificationOptions {
    pub message: String,
    pub title: Option<String>,
    pub notification_type: String,
}

pub const DEFAULT_TITLE: &str = "Claude Code";

/// Notification channels
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum NotificationChannel {
    Terminal,
    OsNative,
    Custom(String),
}

/// Send a notification to the configured channel.
/// TODO: Implement full notification system with platform-specific backends.
pub async fn send_notification(opts: &NotificationOptions) -> Result<()> {
    let title = opts.title.as_deref().unwrap_or(DEFAULT_TITLE);
    let message = &opts.message;

    // Try system notification first
    if let Err(_) = try_system_notification(title, message).await {
        // Fall back to terminal bell
        eprint!("\x07"); // Terminal bell
        eprintln!("[{title}] {message}");
    }

    Ok(())
}

async fn try_system_notification(title: &str, message: &str) -> Result<()> {
    #[cfg(target_os = "macos")]
    {
        let script = format!(
            "display notification \"{}\" with title \"{}\"",
            message.replace('"', "\\\""),
            title.replace('"', "\\\"")
        );
        let output = tokio::process::Command::new("osascript")
            .arg("-e")
            .arg(&script)
            .output()
            .await?;
        if !output.status.success() {
            anyhow::bail!("osascript failed");
        }
        return Ok(());
    }

    #[cfg(target_os = "linux")]
    {
        let output = tokio::process::Command::new("notify-send")
            .arg(title)
            .arg(message)
            .output()
            .await?;
        if !output.status.success() {
            anyhow::bail!("notify-send failed");
        }
        return Ok(());
    }

    #[cfg(target_os = "windows")]
    {
        // TODO: Use Windows Toast notifications
        anyhow::bail!("Windows notifications not yet implemented");
    }

    #[allow(unreachable_code)]
    anyhow::bail!("No notification system available")
}

/// Check if a notification command is configured and run it.
pub async fn run_notification_command(
    command: &str,
    message: &str,
) -> Result<()> {
    let output = tokio::process::Command::new("bash")
        .arg("-c")
        .arg(&format!("{} {}", command, shell_escape(message)))
        .output()
        .await?;

    if !output.status.success() {
        anyhow::bail!(
            "Notification command failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
    }

    Ok(())
}

fn shell_escape(s: &str) -> String {
    format!("'{}'", s.replace('\'', "'\\''"))
}
