// Original TS source: commands/cost/
// Cost tracking and display command

use std::sync::Mutex;
use once_cell::sync::Lazy;

/// Cost tracker state
#[derive(Debug, Clone, Default)]
pub struct CostTracker {
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub cache_read_tokens: u64,
    pub cache_creation_tokens: u64,
    pub total_cost_usd: f64,
}

static COST_TRACKER: Lazy<Mutex<CostTracker>> = Lazy::new(|| {
    Mutex::new(CostTracker::default())
});

pub struct CostCommand;

impl CostCommand {
    pub const NAME: &'static str = "cost";
    pub const DESCRIPTION: &'static str = "Show token usage and costs";

    pub fn run() {
        let tracker = COST_TRACKER.lock().unwrap_or_else(|e| e.into_inner());
        println!("{}", format_total_cost(&tracker));
    }
}

/// Format the total cost as a human-readable string.
pub fn format_total_cost(tracker: &CostTracker) -> String {
    if tracker.input_tokens == 0 && tracker.output_tokens == 0 {
        return "No tokens used in this session.".to_string();
    }

    let total_tokens = tracker.input_tokens + tracker.output_tokens;
    let mut lines = vec![
        format!("Total tokens used: {:>10}", format_tokens(total_tokens)),
        format!("  Input tokens:    {:>10}", format_tokens(tracker.input_tokens)),
        format!("  Output tokens:   {:>10}", format_tokens(tracker.output_tokens)),
    ];

    if tracker.cache_read_tokens > 0 || tracker.cache_creation_tokens > 0 {
        lines.push(format!("  Cache read:      {:>10}", format_tokens(tracker.cache_read_tokens)));
        lines.push(format!("  Cache creation:  {:>10}", format_tokens(tracker.cache_creation_tokens)));
    }

    if tracker.total_cost_usd > 0.0 {
        lines.push(format!("Estimated cost: ${:.4}", tracker.total_cost_usd));
    }

    lines.join("\n")
}

/// Add token usage from a response.
pub fn track_usage(
    input_tokens: u64,
    output_tokens: u64,
    cache_read: u64,
    cache_creation: u64,
    cost_usd: f64,
) {
    let mut tracker = COST_TRACKER.lock().unwrap_or_else(|e| e.into_inner());
    tracker.input_tokens += input_tokens;
    tracker.output_tokens += output_tokens;
    tracker.cache_read_tokens += cache_read;
    tracker.cache_creation_tokens += cache_creation;
    tracker.total_cost_usd += cost_usd;
}

/// Reset the cost tracker.
pub fn reset_cost_tracker() {
    let mut tracker = COST_TRACKER.lock().unwrap_or_else(|e| e.into_inner());
    *tracker = CostTracker::default();
}

fn format_tokens(n: u64) -> String {
    if n < 1_000 {
        n.to_string()
    } else if n < 1_000_000 {
        format!("{:.1}K", n as f64 / 1_000.0)
    } else {
        format!("{:.2}M", n as f64 / 1_000_000.0)
    }
}
