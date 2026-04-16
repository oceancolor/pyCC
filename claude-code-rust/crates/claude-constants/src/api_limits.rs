// Original TS source: constants/apiLimits.ts
// Anthropic API Limits

// =============================================================================
// IMAGE LIMITS
// =============================================================================

/// Maximum base64-encoded image size (API enforced) - 5 MB
pub const API_IMAGE_MAX_BASE64_SIZE: usize = 5 * 1024 * 1024;

/// Target raw image size to stay under base64 limit after encoding - 3.75 MB
pub const IMAGE_TARGET_RAW_SIZE: usize = API_IMAGE_MAX_BASE64_SIZE * 3 / 4;

/// Client-side maximum image width
pub const IMAGE_MAX_WIDTH: u32 = 2000;

/// Client-side maximum image height
pub const IMAGE_MAX_HEIGHT: u32 = 2000;

// =============================================================================
// PDF LIMITS
// =============================================================================

/// Maximum raw PDF file size - 20 MB
pub const PDF_TARGET_RAW_SIZE: usize = 20 * 1024 * 1024;

/// Maximum number of pages in a PDF accepted by the API
pub const API_PDF_MAX_PAGES: u32 = 100;

/// Size threshold above which PDFs are extracted into page images - 3 MB
pub const PDF_EXTRACT_SIZE_THRESHOLD: usize = 3 * 1024 * 1024;

/// Maximum PDF file size for the page extraction path - 100 MB
pub const PDF_MAX_EXTRACT_SIZE: usize = 100 * 1024 * 1024;

/// Max pages the Read tool will extract in a single call
pub const PDF_MAX_PAGES_PER_READ: u32 = 20;

/// PDFs with more pages than this get reference treatment on @ mention
pub const PDF_AT_MENTION_INLINE_THRESHOLD: u32 = 10;

// =============================================================================
// MEDIA LIMITS
// =============================================================================

/// Maximum number of media items (images + PDFs) allowed per API request
pub const API_MAX_MEDIA_PER_REQUEST: u32 = 100;
