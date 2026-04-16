// Original TS source: constants/figures.ts
// Terminal UI glyphs and indicators

// Note: On Windows/Linux, use alternate bullet symbols
#[cfg(target_os = "macos")]
pub const BLACK_CIRCLE: &str = "⏺";
#[cfg(not(target_os = "macos"))]
pub const BLACK_CIRCLE: &str = "●";

pub const BULLET_OPERATOR: &str = "∙";
pub const TEARDROP_ASTERISK: &str = "✻";
pub const UP_ARROW: &str = "\u{2191}";          // ↑
pub const DOWN_ARROW: &str = "\u{2193}";         // ↓
pub const LIGHTNING_BOLT: &str = "\u{21af}";     // ↯ fast mode indicator
pub const EFFORT_LOW: &str = "\u{25cb}";         // ○
pub const EFFORT_MEDIUM: &str = "\u{25d0}";      // ◐
pub const EFFORT_HIGH: &str = "\u{25cf}";        // ●
pub const EFFORT_MAX: &str = "\u{25c9}";         // ◉

// Media/trigger status indicators
pub const PLAY_ICON: &str = "\u{25b6}";          // ▶
pub const PAUSE_ICON: &str = "\u{23f8}";         // ⏸

// MCP subscription indicators
pub const REFRESH_ARROW: &str = "\u{21bb}";      // ↻
pub const CHANNEL_ARROW: &str = "\u{2190}";      // ←
pub const INJECTED_ARROW: &str = "\u{2192}";     // →
pub const FORK_GLYPH: &str = "\u{2442}";         // ⑂

// Review status indicators
pub const DIAMOND_OPEN: &str = "\u{25c7}";       // ◇
pub const DIAMOND_FILLED: &str = "\u{25c6}";     // ◆
pub const REFERENCE_MARK: &str = "\u{203b}";     // ※

// Issue flag indicator
pub const FLAG_ICON: &str = "\u{2691}";          // ⚑

// Blockquote indicators
pub const BLOCKQUOTE_BAR: &str = "\u{258e}";     // ▎
pub const HEAVY_HORIZONTAL: &str = "\u{2501}";   // ━

// Bridge status indicators
pub const BRIDGE_SPINNER_FRAMES: &[&str] = &[
    "\u{00b7}|\u{00b7}",
    "\u{00b7}/\u{00b7}",
    "\u{00b7}\u{2014}\u{00b7}",
    "\u{00b7}\\\u{00b7}",
];
pub const BRIDGE_READY_INDICATOR: &str = "\u{00b7}\u{2714}\u{fe0e}\u{00b7}";
pub const BRIDGE_FAILED_INDICATOR: &str = "\u{00d7}";
