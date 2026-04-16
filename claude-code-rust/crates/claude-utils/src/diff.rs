// Original TS source: utils/diff.ts
// Diff utilities for computing text patches

use std::collections::VecDeque;

/// A diff hunk representing a change in a file
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DiffHunk {
    pub old_start: u64,
    pub old_lines: u64,
    pub new_start: u64,
    pub new_lines: u64,
    pub lines: Vec<String>,
}

pub const CONTEXT_LINES: usize = 3;

/// Adjust hunk line numbers by an offset.
/// Used when the patch was computed on a slice of the file.
pub fn adjust_hunk_line_numbers(hunks: &mut [DiffHunk], offset: i64) {
    if offset == 0 {
        return;
    }
    for hunk in hunks {
        hunk.old_start = (hunk.old_start as i64 + offset) as u64;
        hunk.new_start = (hunk.new_start as i64 + offset) as u64;
    }
}

/// Compute a unified diff patch between old and new content.
pub fn compute_patch(old_content: &str, new_content: &str, file_name: &str) -> Vec<DiffHunk> {
    // Simple implementation: line-by-line diff
    let old_lines: Vec<&str> = old_content.lines().collect();
    let new_lines: Vec<&str> = new_content.lines().collect();

    if old_lines == new_lines {
        return vec![];
    }

    // TODO: Implement full Myers diff algorithm or use a crate like `similar`
    // For now, produce a simple "replace all" hunk when content differs
    vec![DiffHunk {
        old_start: 1,
        old_lines: old_lines.len() as u64,
        new_start: 1,
        new_lines: new_lines.len() as u64,
        lines: old_lines.iter().map(|l| format!("-{}", l))
            .chain(new_lines.iter().map(|l| format!("+{}", l)))
            .collect(),
    }]
}

/// Count lines added and removed in a set of hunks.
pub fn count_lines_changed(hunks: &[DiffHunk], new_file_content: Option<&str>) -> (usize, usize) {
    if hunks.is_empty() {
        if let Some(content) = new_file_content {
            let additions = content.lines().count();
            return (additions, 0);
        }
        return (0, 0);
    }

    let mut additions = 0;
    let mut removals = 0;
    for hunk in hunks {
        for line in &hunk.lines {
            if line.starts_with('+') {
                additions += 1;
            } else if line.starts_with('-') {
                removals += 1;
            }
        }
    }
    (additions, removals)
}

/// Format hunks as a human-readable unified diff patch.
pub fn format_patch(hunks: &[DiffHunk]) -> String {
    let mut result = String::new();
    for hunk in hunks {
        result.push_str(&format!(
            "@@ -{},{} +{},{} @@\n",
            hunk.old_start, hunk.old_lines, hunk.new_start, hunk.new_lines
        ));
        for line in &hunk.lines {
            result.push_str(line);
            result.push('\n');
        }
    }
    result
}
